#!/bin/bash
# D-16 wall contact, measured in the PHYSICS frame.
# upperbody-sw#49 (Alex, 9 Nov) established that odometry can report success while the base
# does not move in Gazebo; every number here is therefore world pose, odom is reported only to
# show the divergence.
# Patterns live in this file so they never appear in an invoking command line.
set -o pipefail
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>256</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
source /opt/ros/jazzy/setup.bash >/dev/null 2>&1
source ~/openamrobot-interfaces/ros2/install/setup.bash >/dev/null 2>&1
source ~/p105_main/ros2/install/setup.bash >/dev/null 2>&1
cd ~/openamr-test

world_pose() {
  timeout 25 gz topic -e -t /world/walled_world/pose/info -n 1 2>/dev/null \
    | awk '/name: "openamrobot"/{f=1} f&&/position/{p=1} p&&/x:/{print $2; exit}'
}
odom_x() {
  timeout 20 ros2 topic echo /odom --once --field pose.pose.position.x 2>/dev/null | head -1
}

echo "=== removing arbitration so velocity reaches the base (disclosed workaround) ==="
pkill -9 -f safety_stop_gate_node 2>/dev/null
pkill -9 -f velocity_smoother 2>/dev/null
pkill -9 -f nav2_collision_monitor 2>/dev/null
sleep 3

echo "physics x before: $(world_pose)"
echo "odom    x before: $(odom_x)"

timeout 120 python3 d16_drive.py /cmd_vel 0.20 40 /tmp/d16_physics.json 2>&1 | tail -8

echo "physics x after:  $(world_pose)"
echo "odom    x after:  $(odom_x)"
echo "wall_1 spans x 4.90..5.10 (inner face 4.90)"
echo "DONE"
