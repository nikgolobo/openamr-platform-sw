#!/usr/bin/env python3
"""S7a trace for platform-sw#35 — time-aligned rclpy capture across the whole stop path.

Answers Mohammad's list directly:
  * per-topic last value and timestamp (sim + wall), and whether input to the smoother truly
    went silent for longer than velocity_timeout (0.3 s);
  * cmd_vel_gated / cmd_vel_smoothed / final /cmd_vel / /odom / /clock on one clock;
  * publisher endpoints and lifecycle state for the nodes on the path, captured by the caller.

Method: drives the UI's own message type on /ui/cmd_vel (stamped from /clock, because the relay
rejects stamps older than 0.25 s), then stops publishing abruptly. Start of the failed window is
the last /ui/cmd_vel received.

Usage: python3 s7a_trace.py out.jsonl [hold_s] [tail_s]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock

SPEED = 0.20
PUB_HZ = 10.0

TRACKED = ["/ui/cmd_vel", "/cmd_vel_joy", "/cmd_vel_mux", "/cmd_vel_gated",
           "/cmd_vel_smoothed", "/cmd_vel", "/odom"]


class Trace(Node):
    def __init__(self, out):
        super().__init__("s7a_trace")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.out = out
        self.sim_ns = None
        self.last = {}
        self.counts = {}
        self.create_subscription(Clock, "/clock", self.on_clock, 100)
        for t in ["/cmd_vel_joy", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]:
            self.create_subscription(Twist, t, self.mk(t), 200)
        self.create_subscription(TwistStamped, "/ui/cmd_vel", self.mk_stamped("/ui/cmd_vel"), 200)
        self.create_subscription(Odometry, "/odom", self.on_odom, 200)
        self.pub = self.create_publisher(TwistStamped, "/ui/cmd_vel", 20)

    def on_clock(self, m):
        self.sim_ns = m.clock.sec * 1_000_000_000 + m.clock.nanosec

    def mk(self, topic):
        def cb(m):
            self.rec(topic, float(m.linear.x), float(m.angular.z))
        return cb

    def mk_stamped(self, topic):
        def cb(m):
            self.rec(topic, float(m.twist.linear.x), float(m.twist.angular.z))
        return cb

    def rec(self, topic, lin, ang, x=None):
        r = {"topic": topic, "lin": lin, "ang": ang, "sim_ns": self.sim_ns,
             "wall_ns": time.time_ns()}
        if x is not None:
            r["x"] = x
        self.out.write(json.dumps(r) + "\n")
        self.last[topic] = r
        self.counts[topic] = self.counts.get(topic, 0) + 1

    def on_odom(self, m):
        self.rec("/odom", float(m.twist.twist.linear.x), float(m.twist.twist.angular.z),
                 float(m.pose.pose.position.x))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/s7a_trace.jsonl"
    hold = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    tail = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0

    out = open(path, "w")
    rclpy.init()
    n = Trace(out)
    end = time.monotonic() + 2.0
    while time.monotonic() < end:
        rclpy.spin_once(n, timeout_sec=0.05)

    # drive
    t_end = time.monotonic() + hold
    nxt = time.monotonic()
    while time.monotonic() < t_end:
        m = TwistStamped()
        if n.sim_ns is not None:
            m.header.stamp.sec = n.sim_ns // 1_000_000_000
            m.header.stamp.nanosec = n.sim_ns % 1_000_000_000
        m.header.frame_id = "base_link"
        m.twist.linear.x = SPEED
        n.pub.publish(m)
        nxt += 1.0 / PUB_HZ
        while time.monotonic() < nxt:
            rclpy.spin_once(n, timeout_sec=0.005)

    t_cut = time.monotonic()
    # abrupt: no farewell zero, exactly like a dead link
    end = time.monotonic() + tail
    while time.monotonic() < end:
        rclpy.spin_once(n, timeout_sec=0.02)
    out.close()

    recs = [json.loads(l) for l in open(path)]
    last_ui = n.last.get("/ui/cmd_vel")
    ui_sim = last_ui["sim_ns"] if last_ui else None

    def after(topic):
        if ui_sim is None:
            return []
        return [r for r in recs if r["topic"] == topic and r["sim_ns"] and r["sim_ns"] >= ui_sim]

    summary = {"hold_s": hold, "tail_s": tail,
               "counts": n.counts,
               "last_ui": last_ui,
               "per_topic": {}}

    for t in TRACKED:
        rows = after(t)
        zeros = [r for r in rows if abs(r["lin"]) < 1e-6]
        nz = [r for r in rows if abs(r["lin"]) > 1e-6]
        entry = {
            "messages_after_last_ui": len(rows),
            "zeros_after": len(zeros),
            "nonzero_after": len(nz),
            "last_value": rows[-1]["lin"] if rows else n.last.get(t, {}).get("lin"),
            "last_sim_ns": rows[-1]["sim_ns"] if rows else n.last.get(t, {}).get("sim_ns"),
            "first_nonzero_after_ms": round((nz[0]["sim_ns"] - ui_sim) / 1e6, 1) if nz and ui_sim else None,
            "first_zero_after_ms": round((zeros[0]["sim_ns"] - ui_sim) / 1e6, 1) if zeros and ui_sim else None,
        }
        summary["per_topic"][t] = entry

    # does the smoother input go silent longer than velocity_timeout (0.3 s) before it zeroes?
    gated = after("/cmd_vel_gated")
    sm = after("/cmd_vel_smoothed")
    if gated and sm:
        last_gated_nz = [r for r in gated if abs(r["lin"]) > 1e-6]
        first_sm_zero = [r for r in sm if abs(r["lin"]) < 1e-6]
        if last_gated_nz and first_sm_zero:
            gap = (first_sm_zero[0]["sim_ns"] - last_gated_nz[-1]["sim_ns"]) / 1e9
            summary["gated_silent_to_smoother_zero_s"] = round(gap, 3)
            summary["smoother_zeroed_after_timeout"] = gap <= 0.35

    xs = [r["x"] for r in recs if r["topic"] == "/odom" and "x" in r]
    if ui_sim:
        post = [r for r in recs if r["topic"] == "/odom" and "x" in r and r["sim_ns"] >= ui_sim]
        if post:
            summary["travel_after_last_ui_m"] = round(max(p["x"] for p in post) - post[0]["x"], 4)
            moving = [p for p in post if abs(p["lin"]) > 1e-3]
            if moving:
                summary["odom_moving_for_s_after_last_ui"] = round((moving[-1]["sim_ns"] - ui_sim) / 1e9, 2)
    summary["x_range"] = [round(min(xs), 3), round(max(xs), 3)] if xs else None

    print(json.dumps(summary, indent=2))
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
