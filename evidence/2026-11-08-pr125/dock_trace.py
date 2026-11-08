#!/usr/bin/env python3
"""Active dock trace for the #125 review: does docking velocity enter the arbitration path?

Sends a real DockRobot goal (pose-based, no dock database) and records every hop for the duration.
The point is not a successful dock — it is that docking commands appear on cmd_vel_dock and reach
the base only through cmd_vel_mux -> cmd_vel_gated -> cmd_vel_smoothed -> collision_monitor -> /cmd_vel.

Usage: python3 dock_trace.py [seconds]
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

HOPS = ["/cmd_vel_dock", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]


class Trace(Node):
    def __init__(self):
        super().__init__("dock_trace")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.counts = {t: 0 for t in HOPS}
        self.nonzero = {t: 0 for t in HOPS}
        self.maxv = {t: 0.0 for t in HOPS}
        self.first_nonzero = {}
        self.odom = []
        for t in HOPS:
            self.create_subscription(Twist, t, self.mk(t), 100)
        self.create_subscription(Odometry, "/odom", self.on_odom, 100)
        self.t0 = time.monotonic()

    def mk(self, topic):
        def cb(m):
            self.counts[topic] += 1
            v = abs(float(m.linear.x))
            if v > 1e-6:
                self.nonzero[topic] += 1
                self.maxv[topic] = max(self.maxv[topic], v)
                self.first_nonzero.setdefault(topic, round(time.monotonic() - self.t0, 2))
        return cb

    def on_odom(self, m):
        self.odom.append((time.monotonic() - self.t0, m.pose.pose.position.x,
                          m.twist.twist.linear.x))

    def spin_for(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    rclpy.init()
    n = Trace()

    ac = ActionClient(n, DockRobot, "dock_robot")
    if not ac.wait_for_server(timeout_sec=10.0):
        print(json.dumps({"error": "dock_robot action server unavailable"}))
        return

    goal = DockRobot.Goal()
    goal.use_dock_id = False
    goal.dock_type = "simple_charging_dock"
    goal.dock_pose.header.frame_id = "map"
    goal.dock_pose.header.stamp = n.get_clock().now().to_msg()
    goal.dock_pose.pose.position.x = 4.899
    goal.dock_pose.pose.position.y = 0.0
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
    print("goal accepted:", accepted)

    n.spin_for(secs)

    result = None
    if handle is not None:
        rf = handle.get_result_async()
        end = time.monotonic() + 5.0
        while not rf.done() and time.monotonic() < end:
            rclpy.spin_once(n, timeout_sec=0.05)
        if rf.done():
            try:
                result = {"status": int(rf.result().status),
                          "error_code": int(getattr(rf.result().result, "error_code", -1)),
                          "error_msg": str(getattr(rf.result().result, "error_msg", ""))[:120],
                          "num_retries": int(getattr(rf.result().result, "num_retries", -1))}
            except Exception as e:  # noqa: BLE001
                result = {"status_error": str(e)[:80]}

    xs = [o[1] for o in n.odom]
    summary = {
        "goal_accepted": accepted,
        "window_s": secs,
        "hop_counts": n.counts,
        "hop_nonzero": n.nonzero,
        "hop_max_linear": {k: round(v, 3) for k, v in n.maxv.items()},
        "first_nonzero_s": n.first_nonzero,
        "odom_travel_m": round(max(xs) - min(xs), 4) if xs else None,
        "result": result,
    }
    print(json.dumps(summary, indent=2))
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
