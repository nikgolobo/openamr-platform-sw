#!/usr/bin/env python3
"""Dock then undock, driven the way the robot actually moves.

The earlier attempt teleported the model in Gazebo: odometry stayed at the origin, the docking
controller's pose diverged, it detected collisions and aborted, and undock then correctly refused
("Robot is not in the dock"). This drives to the dock through the command path so odom stays
consistent, docks, and only then undocks — recording every hop for both phases.

Usage: python3 dock_undock_sequence.py [drive_s]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist, TwistStamped
from nav2_msgs.action import DockRobot, UndockRobot
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock
from std_srvs.srv import Trigger

HOPS = ["/cmd_vel_dock", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]
STATUS = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED",
          5: "CANCELED", 6: "ABORTED", 7: "ABORTED"}


class Seq(Node):
    def __init__(self):
        super().__init__("dock_undock_sequence")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.sim = None
        self.phase = "idle"
        self.stats = {}
        self.odom = []
        self.create_subscription(Clock, "/clock", lambda m: setattr(
            self, "sim", m.clock.sec + m.clock.nanosec / 1e9), 50)
        for t in HOPS:
            self.create_subscription(Twist, t, self.mk(t), 100)
        self.create_subscription(Odometry, "/odom", self.on_odom, 100)
        self.pub = self.create_publisher(TwistStamped, "/ui/cmd_vel", 20)
        self.init_pub = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)

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
        self.odom.append((time.monotonic(), m.pose.pose.position.x, float(m.twist.twist.linear.x)))

    def spin_for(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)

    def drive(self, seconds, speed=0.15):
        self.phase = "drive"
        end = time.monotonic() + seconds
        nxt = time.monotonic()
        while time.monotonic() < end:
            m = TwistStamped()
            if self.sim:
                m.header.stamp.sec = int(self.sim)
                m.header.stamp.nanosec = int((self.sim % 1) * 1e9)
            m.twist.linear.x = speed
            self.pub.publish(m)
            nxt += 0.1
            while time.monotonic() < nxt:
                rclpy.spin_once(self, timeout_sec=0.005)
        for _ in range(20):
            self.pub.publish(TwistStamped())
            rclpy.spin_once(self, timeout_sec=0.02)

    def call(self, name):
        c = self.create_client(Trigger, name)
        if not c.wait_for_service(timeout_sec=5.0):
            return "unavailable"
        f = c.call_async(Trigger.Request())
        while not f.done():
            rclpy.spin_once(self, timeout_sec=0.05)
        return f"{f.result().success} {f.result().message!r}"

    def run_action(self, name, action_type, goal, phase, timeout):
        self.phase = phase
        ac = ActionClient(self, action_type, name)
        if not ac.wait_for_server(timeout_sec=10.0):
            return {"error": "server unavailable"}
        fut = ac.send_goal_async(goal)
        end = time.monotonic() + 10.0
        while not fut.done() and time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)
        handle = fut.result() if fut.done() else None
        if handle is None or not handle.accepted:
            return {"accepted": False}
        rf = handle.get_result_async()
        end = time.monotonic() + timeout
        while not rf.done() and time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.05)
        if not rf.done():
            return {"accepted": True, "result": "timeout"}
        st = int(rf.result().status)
        return {"accepted": True, "status": st, "status_name": STATUS.get(st, "?"),
                "error_code": int(getattr(rf.result().result, "error_code", -1)),
                "error_msg": str(getattr(rf.result().result, "error_msg", ""))[:100]}


def main():
    drive_s = float(sys.argv[1]) if len(sys.argv) > 1 else 18.0
    rclpy.init()
    n = Seq()
    n.spin_for(2.0)
    # AMCL needs a map->odom transform or the docking server cannot resolve a map-frame dock pose.
    for _ in range(5):
        m = PoseWithCovarianceStamped()
        m.header.frame_id = "map"
        m.header.stamp = n.get_clock().now().to_msg()
        m.pose.pose.orientation.w = 1.0
        n.init_pub.publish(m)
        n.spin_for(0.4)
    print("initial pose published at map origin")
    n.spin_for(3.0)
    print("release:", n.call("/safety/stop_lock_release"))

    n.drive(drive_s)
    x_after_drive = n.odom[-1][1] if n.odom else None
    print("odom x after drive: %.3f" % x_after_drive if x_after_drive is not None else "no odom")

    dock = DockRobot.Goal()
    dock.use_dock_id = False
    dock.dock_type = "simple_charging_dock"
    dock.dock_pose.header.frame_id = "map"
    dock.dock_pose.header.stamp = n.get_clock().now().to_msg()
    dock.dock_pose.pose.position.x = 4.899
    dock.dock_pose.pose.orientation.z = 1.0
    dock.dock_pose.pose.orientation.w = 0.0
    dock.navigate_to_staging_pose = False
    dock.max_staging_time = 25.0
    dock_res = n.run_action("dock_robot", DockRobot, dock, "dock", 60.0)
    print("dock:", json.dumps(dock_res))

    undock_res = None
    if dock_res.get("status") == 4:
        ud = UndockRobot.Goal()
        ud.dock_type = "simple_charging_dock"
        ud.max_undocking_time = 30.0
        undock_res = n.run_action("undock_robot", UndockRobot, ud, "undock", 45.0)
        print("undock:", json.dumps(undock_res))
    else:
        print("undock: not attempted (dock did not succeed)")

    summary = {
        "drive_s": drive_s,
        "odom_x_after_drive": round(x_after_drive, 3) if x_after_drive is not None else None,
        "odom_x_final": round(n.odom[-1][1], 3) if n.odom else None,
        "dock": dock_res,
        "undock": undock_res,
        "phases": n.stats,
    }
    print(json.dumps(summary, indent=2))
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
