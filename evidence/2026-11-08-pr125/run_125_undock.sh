#!/bin/bash
# #125 review item: active UNDOCK evidence. Place robot at the dock, dock it, then undock and
# capture /cmd_vel publishers while the undock motion is running.
set -o pipefail
source /opt/ros/jazzy/setup.bash
source ~/openamrobot-interfaces/ros2/install/setup.bash
source ~/openamr-platform-sw/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>256</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
export DISPLAY=:99

echo "=== 0. place robot in front of the dock ==="
timeout 20 gz service -s /world/walled_world/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean \
  --timeout 5000 --req 'name: "openamrobot", position: {x: 3.0, y: 0.0, z: 0.05}, orientation: {x: 0, y: 0, z: 0, w: 1}' 2>&1 | tail -1
sleep 3

echo "=== 1. release the lock ==="
cd ~/openamr-test/gate-a
timeout 90 python3 unblock_release.py 2>&1 | grep -E '"release_success"|"release_message"'

echo "=== 2. dock (so undock has something to undock from) ==="
timeout 90 python3 dock_trace.py 15 2>&1 | tail -22

echo "=== 3. undock, capturing publishers mid-motion ==="
nohup timeout 90 python3 undock_trace.py 20 > /tmp/undock.out 2>&1 &
UPID=$!
sleep 5
echo "--- /cmd_vel while undocking ---"
timeout 20 ros2 topic info /cmd_vel -v 2>/dev/null | grep -E "Publisher count|Node name" | head -4
echo "--- /cmd_vel_dock while undocking ---"
timeout 20 ros2 topic info /cmd_vel_dock -v 2>/dev/null | grep -E "Publisher count|Node name" | head -4
wait $UPID
echo "=== 4. undock result ==="
tail -35 /tmp/undock.out
echo DONE
