#!/bin/bash
# Nav-only Gazebo run of Kunal's #90 head (goal_pose reproduction, Alex's item 1).
# Same environment recipe as gate-a/boot_stack.sh: Xvfb + software GL (the VM has no GPU, and
# Gazebo segfaults in OgreNext without it), and Cyclone with a raised participant index.
set -o pipefail

echo "=== 0. leftovers ==="
for pat in "gz sim" "gz-sim" "parameter_bridge" "ros2 launch" safety_stop_gate twist_mux collision_monitor velocity_smoother "nav2_" controller_server planner_server bt_navigator behavior_server smoother_server amcl map_server lifecycle_manager goal_pose_relay; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 4
# cdds* is Cyclone's per-domain participant table: if it survives a crash, every node after it
# fails with "Failed to find a free participant index for domain 0".
rm -f /dev/shm/cdds* /dev/shm/fastrtps* 2>/dev/null

echo "=== 1. Xvfb ==="
pgrep -f "Xvfb :99" >/dev/null || (nohup Xvfb :99 -screen 0 1600x1200x24 -nolisten tcp >/dev/null 2>&1 &)
sleep 2

echo "=== 2. env ==="
source /opt/ros/jazzy/setup.bash
source "$HOME/openamrobot-interfaces/ros2/install/setup.bash"
source "$HOME/pr90/ros2/install/setup.bash"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>256</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export DISPLAY=:99

echo "=== 3. launch (nav-only: use_docking=false) ==="
exec ros2 launch openamrobot_bringup bringup.launch.py sim:=true use_docking:=false gui:=false
