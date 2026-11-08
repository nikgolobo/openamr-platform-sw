#!/bin/bash
# Full #125 acceptance run: place the robot in front of the dock, release the lock, start a dock,
# capture /cmd_vel publishers WHILE docking, then press Stop mid-motion.
set -o pipefail
source /opt/ros/jazzy/setup.bash
source ~/openamrobot-interfaces/ros2/install/setup.bash
source ~/openamr-platform-sw/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>256</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
export DISPLAY=:99

echo "=== 0. place the robot 1.9 m in front of the dock ==="
timeout 20 gz service -s /world/walled_world/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean \
  --timeout 5000 --req 'name: "openamrobot", position: {x: 3.0, y: 0.0, z: 0.05}, orientation: {x: 0, y: 0, z: 0, w: 1}' 2>&1 | tail -1
sleep 3

echo "=== 1. release the stop lock ==="
timeout 90 python3 ~/openamr-test/gate-a/unblock_release.py 2>&1 | grep -E "release_success|release_message"

echo "=== 2. dock in the background, capture publishers mid-motion ==="
cd ~/openamr-test/gate-a
nohup timeout 90 python3 dock_stop_test.py 7 10 > /tmp/dock_stop.out 2>&1 &
DPID=$!
sleep 5
echo "--- /cmd_vel while docking ---"
timeout 20 ros2 topic info /cmd_vel -v 2>/dev/null | grep -E "Publisher count|Node name" | head -4
echo "--- /cmd_vel_dock publishers ---"
timeout 20 ros2 topic info /cmd_vel_dock -v 2>/dev/null | grep -E "Publisher count|Node name" | head -4
wait $DPID
echo "=== 3. result ==="
cat /tmp/dock_stop.out
echo DONE
