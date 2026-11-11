#!/usr/bin/env bash
# Source-build fallback check for opennav_docking (platform-sw#125, review 11 Nov 18:37).
#
# The review finding: when apt cannot supply opennav_docking, the workflow falls back to a source
# build, but that branch continued into `colcon build` even though required Nav2 dependency
# `package.sh` files were absent — a doomed build presented as an attempt. This script does the
# dependency check FIRST and stops with a named list instead of pressing on.
#
# Exit codes:
#   0   source build succeeded and the harness ran
#   30  dependency incomplete — named, not attempted
#   40  build failed
#   50  build ok, harness failed
#
# Run on the sim VM: bash ~/source_fallback_check.sh 2>&1 | tee ~/source_fallback.log
set -uo pipefail

WS="${WS:-$HOME/p105_main/ros2}"
# Where dependency CMake configs may legitimately come from. Overridable so the incomplete-dependency
# case can be exercised without uninstalling anything.
DEPS_BASES="${DEPS_BASES:-}"
PKGS="${PKGS:-opennav_docking}"
NAV2_WS="${NAV2_WS:-$HOME/p105_main/nav2_ws}"
SIM_PROFILE="${SIM_PROFILE:-openamrobot_docking.launch.py}"

set +u   # ROS and colcon setup scripts are not `set -u` safe; they read unset vars and abort the caller
source /opt/ros/jazzy/setup.bash 2>/dev/null || { echo "ERROR: no /opt/ros/jazzy"; exit 40; }
[[ -f "$NAV2_WS/install/setup.bash" ]] && source "$NAV2_WS/install/setup.bash"
[[ -f "$WS/install/setup.bash" ]] && source "$WS/install/setup.bash"
set -u

echo "== env =="
echo "ROS_DISTRO=${ROS_DISTRO:-?}  WS=$WS  NAV2_WS=$NAV2_WS"
echo "sim profile: $SIM_PROFILE"
echo

# The dependency set comes from the package's own manifest, not from a hand-kept list: a hardcoded
# list drifts, and a wrong entry reports a component missing that never existed (nav2_ros_common on
# jazzy was exactly that mistake).
PKG_XML="${PKG_XML:-}"
if [[ -z "$PKG_XML" ]]; then
  PKG_XML=$(find "$WS/src" -maxdepth 5 -path '*opennav_docking/package.xml' 2>/dev/null | head -1)
fi

if [[ -n "$PKG_XML" && -f "$PKG_XML" ]]; then
  mapfile -t DEPS < <(grep -oE "<(depend|build_depend|exec_depend|build_export_depend)>[a-z0-9_]+" "$PKG_XML" \
    | sed 's/.*>//' | sort -u)
  echo "dependencies from $PKG_XML"
else
  DEPS=(nav2_msgs nav2_util nav2_graceful_controller rclcpp rclcpp_action rclcpp_lifecycle
        geometry_msgs nav_msgs sensor_msgs tf2_ros pluginlib yaml_cpp_vendor)
  echo "dependencies from built-in fallback list (no package.xml found)"
fi

if [[ -z "$DEPS_BASES" ]]; then
  BASES=("$NAV2_WS/install" "$WS/install" /opt/ros/jazzy)
else
  IFS=: read -r -a BASES <<< "$DEPS_BASES"
fi

echo "== dependency check (before any build) =="
echo "   searching: ${BASES[*]}"
missing=()
for dep in "${DEPS[@]}"; do
  found=0
  for base in ${BASES[@]+"${BASES[@]}"}; do
    [[ -d "$base" ]] || continue
    # A CMake package is complete only if its config file exists; package.sh alone is the ament
    # environment hook and is what the review found present-but-useless on its own.
    if compgen -G "$base/share/$dep/cmake/*Config.cmake" >/dev/null 2>&1; then
      found=1
      break
    fi
  done
  # A sibling package in the same source tree is satisfied by the build itself, not by an installed
  # config: opennav_docking_core lives beside opennav_docking and is built with it.
  if [[ $found -eq 0 ]] && grep -rqs "<name>$dep</name>" "$WS/src" --include=package.xml; then
    echo "  ok      $dep (source, built with this workspace)"
    continue
  fi
  if [[ $found -eq 1 ]]; then
    echo "  ok      $dep"
  else
    echo "  MISSING $dep"
    missing+=("$dep")
  fi
done

if ((${#missing[@]})); then
  echo
  echo "STOP: ${#missing[@]} dependency(ies) have no CMake config: ${missing[*]}"
  echo "      Not attempting the build. This is the finding the review asked to make explicit:"
  echo "      an incomplete dependency set must be reported, not converted into a failed build."
  exit 30
fi

if [[ "${1:-}" == "--deps-only" ]]; then
  echo
  echo "DEPS-ONLY: dependency set complete, stopping before the build as requested"
  exit 0
fi

echo
echo "== source build =="
cd "$WS" || exit 40
colcon build --packages-up-to $PKGS --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -25
build_rc=${PIPESTATUS[0]}
if [[ $build_rc -ne 0 ]]; then
  echo "BUILD FAILED (rc=$build_rc) — dependencies were complete, so this is a source defect"
  exit 40
fi
set +u
source "$WS/install/setup.bash"
set -u

echo
echo "== harness on the sim profile (source-built package) =="
HARNESS_TIMEOUT_S=150 bash "$WS/src/openamrobot_docking/test/docking_action_servers.sh" \
  openamrobot_docking "$SIM_PROFILE" 1 \
  --control-node detected_dock_pose_publisher \
  -- use_sim_time:=false launch_trigger:=false
rc=$?
echo
case $rc in
  0)  echo "RESULT: PASS — source-built package brings both action servers up" ;;
  10) echo "RESULT: MISMATCH — graph healthy, counts differ (expected one per action)" ;;
  20) echo "RESULT: ERROR — infrastructure, proves nothing either way" ;;
  *)  echo "RESULT: unexpected exit $rc" ;;
esac
exit $(( rc == 0 ? 0 : 50 ))
