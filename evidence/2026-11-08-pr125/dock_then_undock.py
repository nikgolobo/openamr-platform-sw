#!/usr/bin/env python3
"""Dock then undock, assuming the lock is already released and the four action statuses are populated.

Run unblock_release.py immediately before this in the SAME invocation: any release attempt that is
refused leaves the gate locked, and the locked gate cancels dock goals on every tick, which looks
like a docking failure but is #124's condition (a) doing its job.

Usage: python3 dock_then_undock.py [dock_timeout] [undock_timeout]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav2_msgs.action import DockRobot, UndockRobot
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter

HOPS = ["/cmd_vel_dock", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]
STATUS = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED",
          5: "CANCELED", 6: "ABORTED"}


class Seq(Node):
    def __init__(self):
        super().__init__("dock_then_undock")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.phase = "idle"
        self.stats = {}
        self.odom = []
        for t in HOPS:
            self.create_subscription(Twist, t, self.mk(t), 100)
        self.create_subscription(Odometry, "/odom", self.on_odom, 100)

    def mk(self, topic):
        def cb(m):
            s = self.stats.setdefault(self.phase, {}).setdefault(
                topic, {"msgs": 0, "nonzero": 0, "max": 0.0})
            s["msgs"] += 1
            v = abs(float(m.linear.x))
            if v > 1e-6:
                s["nonzero"] += 1
                s["max"] = max(s["max"], v)
        return cb

    def on_odom(self, m):
        self.odom.append((time.monotonic(), m.pose.pose.position.x))

    def spin_for(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)

    def run(self, name, typ, goal, phase, timeout):
        self.phase = phase
        ac = ActionClient(self, typ, name)
        if not ac.wait_for_server(timeout_sec=10.0):
            return {"error": "unavailable"}
        fut = ac.send_goal_async(goal)
        end = time.monotonic() + 10.0
        while not fut.done() and time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)
        h = fut.result() if fut.done() else None
        if h is None or not h.accepted:
            return {"accepted": False}
        rf = h.get_result_async()
        end = time.monotonic() + timeout
        while not rf.done() and time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)
        if not rf.done():
            return {"accepted": True, "result": "timeout"}
        st = int(rf.result().status)
        return {"accepted": True, "status": st, "status_name": STATUS.get(st, "?"),
                "error_msg": str(getattr(rf.result().result, "error_msg", ""))[:120]}


def main():
    dt = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
    ut = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
    rclpy.init()
    n = Seq()
    n.spin_for(1.5)

    dock = DockRobot.Goal()
    dock.use_dock_id = False
    dock.dock_type = "simple_charging_dock"
    dock.dock_pose.header.frame_id = "map"
    dock.dock_pose.header.stamp = n.get_clock().now().to_msg()
    dock.dock_pose.pose.position.x = 4.899
    dock.dock_pose.pose.orientation.z = 1.0
    dock.dock_pose.pose.orientation.w = 0.0
    dock.navigate_to_staging_pose = False
    dock.max_staging_time = 30.0
    dock_res = n.run("dock_robot", DockRobot, dock, "dock", dt)
    print("dock:", json.dumps(dock_res))

    undock_res = None
    if dock_res.get("status") == 4:
        ud = UndockRobot.Goal()
        ud.dock_type = "simple_charging_dock"
        ud.max_undocking_time = 30.0
        undock_res = n.run("undock_robot", UndockRobot, ud, "undock", ut)
        print("undock:", json.dumps(undock_res))
    else:
        print("undock: NOT ATTEMPTED (dock did not reach SUCCEEDED)")

    xs = [o[1] for o in n.odom]
    print(json.dumps({
        "dock": dock_res, "undock": undock_res,
        "odom_x_start": round(xs[0], 3) if xs else None,
        "odom_x_end": round(xs[-1], 3) if xs else None,
        "phases": n.stats}, indent=2))
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
