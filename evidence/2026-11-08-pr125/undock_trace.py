#!/usr/bin/env python3
"""Active undock trace (#125 review): does UndockRobot motion reach the base through the chain?

Same instrumentation as dock_trace, for the undock half the reviewer asked for. Records every hop,
then reports counts/non-zero/max per hop, odom travel and the action result.

Usage: python3 undock_trace.py [seconds]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav2_msgs.action import UndockRobot
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter

HOPS = ["/cmd_vel_dock", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]
STATUS = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED",
          5: "CANCELED", 6: "ABORTED"}


class Trace(Node):
    def __init__(self):
        super().__init__("undock_trace")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.counts = {t: 0 for t in HOPS}
        self.nonzero = {t: 0 for t in HOPS}
        self.maxv = {t: 0.0 for t in HOPS}
        self.first = {}
        self.odom = []
        self.t0 = time.monotonic()
        for t in HOPS:
            self.create_subscription(Twist, t, self.mk(t), 100)
        self.create_subscription(Odometry, "/odom", self.on_odom, 100)

    def mk(self, topic):
        def cb(m):
            self.counts[topic] += 1
            v = abs(float(m.linear.x))
            if v > 1e-6:
                self.nonzero[topic] += 1
                self.maxv[topic] = max(self.maxv[topic], v)
                self.first.setdefault(topic, round(time.monotonic() - self.t0, 2))
        return cb

    def on_odom(self, m):
        self.odom.append((time.monotonic() - self.t0, m.pose.pose.position.x, float(m.twist.twist.linear.x)))

    def spin_for(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    rclpy.init()
    n = Trace()
    ac = ActionClient(n, UndockRobot, "undock_robot")
    if not ac.wait_for_server(timeout_sec=10.0):
        print(json.dumps({"error": "undock_robot server unavailable"}))
        return

    goal = UndockRobot.Goal()
    goal.dock_type = "simple_charging_dock"
    goal.max_undocking_time = 30.0

    fut = ac.send_goal_async(goal)
    end = time.monotonic() + 10.0
    while not fut.done() and time.monotonic() < end:
        rclpy.spin_once(n, timeout_sec=0.05)
    handle = fut.result() if fut.done() else None
    accepted = bool(handle and handle.accepted)
    print("goal accepted:", accepted)

    n.spin_for(secs)

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
                      "error_msg": str(getattr(rf.result().result, "error_msg", ""))[:120]}

    xs = [o[1] for o in n.odom]
    print(json.dumps({
        "goal_accepted": accepted,
        "window_s": secs,
        "hop_counts": n.counts,
        "hop_nonzero": n.nonzero,
        "hop_max_linear": {k: round(v, 3) for k, v in n.maxv.items()},
        "first_nonzero_s": n.first,
        "odom_travel_m": round(max(xs) - min(xs), 4) if xs else None,
        "result": result,
    }, indent=2))
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
