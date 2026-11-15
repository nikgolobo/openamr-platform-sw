#!/bin/bash
# Nav-only Gazebo run of Kunal's #90 head, with a teardown that actually empties the graph.
#
# Two things bite here and both produce silently wrong evidence:
#   * `ros2 launch` is a supervisor: killing it leaves the node processes running, so a second
#     launch joins a graph that already has proxies and forwarders in it. Measured on 15 Nov: two
#     goal_pose_forwarders and two goal_pose_proxies, which makes the forwarder log "more than one
#     action server" and turns one pose into two goals.
#   * the VM has no GPU and no usable default DDS domain table: Gazebo segfaults in OgreNext and
#     every node aborts on "Failed to find a free participant index" without the env below.
set -o pipefail

echo "=== 0. teardown ==="
for pat in "gz sim" "gz-sim" "parameter_bridge" "ros2 launch" safety_stop_gate twist_mux \
           collision_monitor velocity_smoother "nav2_" controller_server planner_server \
           bt_navigator behavior_server smoother_server amcl map_server lifecycle_manager \
           goal_pose_forwarder goal_proxy rosbridge_websocket navigation_status_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 5
for i in $(seq 1 15); do
  left=$(pgrep -fc "goal_pose_forwarder|goal_proxy|gz sim" 2>/dev/null)
  [ "${left:-0}" = "0" ] && break
  sleep 2
done
echo "leftovers after teardown: forwarders/proxies/gz = $(pgrep -fc 'goal_pose_forwarder|goal_proxy|gz sim' 2>/dev/null)"
# cdds* is Cyclone's per-domain participant table; if it survives a crash every node aborts.
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
