#!/bin/bash
# D-16 wall-contact evidence at CURRENT main head (#105 asks for native contact + ground truth).
# Boots main's sim, releases the gate (workaround, disclosed), drives 0.2 m/s at the wall,
# records odom and the gazebo world pose of the base.
# Patterns live in this file so they never appear in the invoking command line.
set -o pipefail
D=~/openamr-test
LOG=$D/logs
TREE=~/p105_main/ros2
mkdir -p "$LOG"

echo "=== 0. kill leftovers ==="
for pat in "gz sim" "gz-sim" "parameter_bridge" "ros2 launch" rosbridge_websocket safety_stop_gate twist_mux collision_monitor velocity_smoother "nav2_" controller_server planner_server bt_navigator behavior_server smoother_server amcl map_server lifecycle_manager; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 4
for i in $(seq 1 10); do
  [ "$(pgrep -fc 'gz sim' 2>/dev/null)" = "0" ] && break
  sleep 2
done
rm -f /dev/shm/cdds* /dev/shm/fastrtps* /dev/shm/sem.* 2>/dev/null
ros2 daemon stop >/dev/null 2>&1
pgrep -f "Xvfb :99" >/dev/null || (nohup Xvfb :99 -screen 0 1600x1200x24 -nolisten tcp >/dev/null 2>&1 &)
sleep 2

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>256</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe MESA_LOADER_DRIVER_OVERRIDE=llvmpipe DISPLAY=:99
source /opt/ros/jazzy/setup.bash
source ~/openamrobot-interfaces/ros2/install/setup.bash
source "$TREE/install/setup.bash"

echo "=== 1. launch main bringup ==="
cd "$TREE"
nohup ros2 launch openamrobot_bringup bringup.launch.py sim:=true > "$LOG/bringup_d16.log" 2>&1 &
for i in $(seq 1 30); do
  sleep 5
  grep -q "Aborting bringup" "$LOG/bringup_d16.log" && { echo "ABORTED"; break; }
  if [ "$(grep -c 'Managed nodes are active' "$LOG/bringup_d16.log")" -ge 2 ]; then echo "managers active after $((i*5))s"; break; fi
done
grep -E "Managed nodes are active|Aborting" "$LOG/bringup_d16.log" | tail -3
echo "gz sim: $(pgrep -fc 'gz sim')  cm: $(pgrep -fc collision_monitor)  gate: $(pgrep -fc safety_stop_gate)"

echo "=== 2. world and base names ==="
W=$(timeout 20 gz topic -l 2>/dev/null | sed -n 's|^/world/\([^/]*\)/.*|\1|p' | head -1)
echo "world: ${W:-UNKNOWN}"
timeout 20 gz model --list 2>/dev/null || echo "no gz model --list"
echo "DONE"
