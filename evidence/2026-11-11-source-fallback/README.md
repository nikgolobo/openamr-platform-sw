# Source-build fallback check — 11 Nov 2026

Review question on openAMRobot/openamr-platform-sw#125 (11 Nov 18:37): when apt cannot supply
`opennav_docking`, the workflow falls back to a source build, but that branch continued into
`colcon build` with dependency `package.sh` files missing. Either make the source path
dependency-complete, or stop explicitly at the missing dependency.

## What was run

On the Lima sim VM (`lima-openamr-test`, jazzy, arm64), with `opennav_docking` source from
`ros-navigation/navigation2` (`jazzy`, sparse checkout `nav2_docking`) and the PR's
`openamrobot_docking` package. `source_fallback_check.sh` resolves every dependency declared in the
package's own `package.xml` to a **CMake config**, and only builds if all of them resolve.

### Case B — dependencies present (`source_fallback_pass.log`, exit 0)

- 15/15 declared dependencies resolved; `opennav_docking_core` counts as satisfied because it is a
  sibling source package built with the workspace.
- `colcon build --packages-up-to opennav_docking openamrobot_docking`: 7 packages, 1 min 0 s cold,
  2.09 s warm; `opennav_docking` itself 52.1 s cold, 0.30 s warm.
- Harness on the sim profile: `PASS — every action advertises 1 server(s) (control node visible)`,
  `/dock_robot: 1`, `/undock_robot: 1`, exit 0.

### Case A — dependencies absent (`source_fallback_absent.log`, exit 30)

`DEPS_BASES` pointed at a non-existent directory so every dependency read as missing. All 14 are
named and the run stops **before** `colcon build` (`STOP: ... Not attempting the build`). That is the
behaviour the review asked to make explicit: an incomplete dependency set is reported, not converted
into a doomed build.

## What this does and does not establish

- Establishes: the source path is dependency-complete **when its declared dependencies are
  installed**, and the check stops cleanly with a named list when they are not.
- Does **not** reproduce the CI failure condition itself (a container where nav2 arrives only as a
  partial source build). That host dependency gap is issue #57.
- The workspace's `openamrobot_docking` was replaced with the PR version for this run. The VM is a
  scratch box; nothing here is reported as real-profile or hardware evidence.

Two defects in the check itself were found and fixed while writing it: a duplicated `$dep` path
segment that reported installed packages as missing, and inherited `set -u` aborting the run when
sourcing ROS/colcon setup scripts, which read unset variables.
