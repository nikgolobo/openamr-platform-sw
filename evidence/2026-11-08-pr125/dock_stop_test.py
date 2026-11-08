#!/usr/bin/env python3
"""Stop during active dock motion (#125 review): does software Stop inhibit the dock?

Sends a real DockRobot goal, lets it drive, then engages /safety/stop_lock_engage mid-motion and
records what happens to the command chain and to the dock goal itself.

Usage: python3 dock_stop_test.py [stop_after_s] [tail_s]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav2_msgs.action import DockRobot
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

HOPS = ["/cmd_vel_dock", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]
STATUS = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED",
          5: "CANCELED", 6: "ABORTED"}


class Probe(Node):
    def __init__(self):
        super().__init__("dock_stop_test")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.log = []          # (t, topic, value)
        self.t0 = time.monotonic()
        self.locked = None
        self.odom = []
        for t in HOPS:
            self.create_subscription(Twist, t, self.mk(t), 100)
        self.create_subscription(Odometry, "/odom", self.on_odom, 100)
        self.create_subscription(Bool, "/safety/stop_lock", lambda m: setattr(self, "locked", bool(m.data)), 50)

    def mk(self, topic):
        def cb(m):
            self.log.append((time.monotonic() - self.t0, topic, float(m.linear.x)))
        return cb

    def on_odom(self, m):
        self.odom.append((time.monotonic() - self.t0, m.pose.pose.position.x, float(m.twist.twist.linear.x)))

    def spin_for(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)

    def engage(self):
        c = self.create_client(Trigger, "/safety/stop_lock_engage")
        if not c.wait_for_service(timeout_sec=5.0):
            return "unavailable"
        f = c.call_async(Trigger.Request())
        end = time.monotonic() + 5.0
        while not f.done() and time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)
        return f.result().success if f.done() else "timeout"


def main():
    stop_after = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    tail = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    rclpy.init()
    n = Probe()

    ac = ActionClient(n, DockRobot, "dock_robot")
    if not ac.wait_for_server(timeout_sec=10.0):
        print(json.dumps({"error": "server unavailable"}))
        return

    goal = DockRobot.Goal()
    goal.use_dock_id = False
    goal.dock_type = "simple_charging_dock"
    goal.dock_pose.header.frame_id = "map"
    goal.dock_pose.header.stamp = n.get_clock().now().to_msg()
    goal.dock_pose.pose.position.x = 4.899
    goal.dock_pose.pose.orientation.z = 1.0
    goal.dock_pose.pose.orientation.w = 0.0
    goal.navigate_to_staging_pose = False
    goal.max_staging_time = 20.0

    fut = ac.send_goal_async(goal)
    end = time.monotonic() + 10.0
    while not fut.done() and time.monotonic() < end:
        rclpy.spin_once(n, timeout_sec=0.05)
    handle = fut.result() if fut.done() else None
    accepted = bool(handle and handle.accepted)

    n.spin_for(stop_after)
    t_stop = time.monotonic() - n.t0
    ok = n.engage()
    n.spin_for(tail)

    def window(a, b, topic):
        rows = [v for (t, tp, v) in n.log if tp == topic and a <= t < b]
        return {"msgs": len(rows), "nonzero": sum(1 for v in rows if abs(v) > 1e-6),
                "max": round(max((abs(v) for v in rows), default=0.0), 3)}

    result = None
    if handle is not None:
        rf = handle.get_result_async()
        end = time.monotonic() + 5.0
        while not rf.done() and time.monotonic() < end:
            rclpy.spin_once(n, timeout_sec=0.05)
        if rf.done():
            st = int(rf.result().status)
            result = {"status": st, "status_name": STATUS.get(st, "?"),
                      "error_code": int(getattr(rf.result().result, "error_code", -1)),
                      "error_msg": str(getattr(rf.result().result, "error_msg", ""))[:100]}

    xs = [o[1] for o in n.odom]
    before = {t: window(0, t_stop, t) for t in HOPS}
    after = {t: window(t_stop, t_stop + tail, t) for t in HOPS}
    summary = {
        "goal_accepted": accepted,
        "engaged_ok": ok,
        "stop_at_s": round(t_stop, 2),
        "lock_after": n.locked,
        "before_stop": before,
        "after_stop": after,
        "odom_travel_m": round(max(xs) - min(xs), 4) if xs else None,
        "travel_after_stop_m": round(
            max((o[1] for o in n.odom if o[0] >= t_stop), default=0.0)
            - min((o[1] for o in n.odom if o[0] >= t_stop), default=0.0), 4),
        "dock_goal_result": result,
    }
    print(json.dumps(summary, indent=2))
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
