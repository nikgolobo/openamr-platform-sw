#!/bin/bash
# Empty the ROS graph: `ros2 launch` is a supervisor, so its children survive it.
set -u
for p in goal_pose_forwarder_node navigate_to_pose_goal_proxy_node \
         navigate_through_poses_goal_proxy_node safety_stop_gate_node \
         controller_server planner_server bt_navigator behavior_server smoother_server \
         amcl map_server lifecycle_manager twist_mux collision_monitor velocity_smoother \
         parameter_bridge nav2_ robot_state_publisher joint_state_publisher map_saver; do
  pkill -9 -f "$p" 2>/dev/null
done
sleep 3
fp=$(pgrep -fc 'goal_pose_forwarder|goal_proxy' 2>/dev/null)
nv=$(pgrep -fc 'nav2_|bt_navigator|controller_server' 2>/dev/null)
gz=$(pgrep -fc 'gz sim' 2>/dev/null)
echo "remaining: forwarders/proxies=${fp:-0} nav2=${nv:-0} gz=${gz:-0}"
