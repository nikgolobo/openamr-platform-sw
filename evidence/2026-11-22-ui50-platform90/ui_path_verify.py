#!/usr/bin/env python3
"""Verify the complete operator command path, hop by hop, on one node and one clock.

    python3 ui_path_verify.py --window 25

Chain under test (platform-sw#90 + ui#50):
    /ui/cmd_vel (TwistStamped) -> relay -> cmd_vel_joy -> twist_mux -> cmd_vel_mux
      -> safety gate -> cmd_vel_gated -> velocity_smoother -> cmd_vel_smoothed
      -> collision_monitor -> /cmd_vel -> base

Prints, per hop: message count, first/last wall stamp, max |linear.x|, and whether the hop ever
carried a nonzero value. A hop that carries messages but never a nonzero is a different failure from
a hop that carries nothing, and that distinction is the point of the tool.

Also records /safety/stop_lock (latched) and /safety/stop_state, so a Stop press can be tied to the
moment the chain went to zero.
"""

import argparse
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool

HOPS = [
    ("/ui/cmd_vel", TwistStamped, "stamped"),
    ("/cmd_vel_joy", Twist, "plain"),
    ("/cmd_vel_mux", Twist, "plain"),
    ("/cmd_vel_gated", Twist, "plain"),
    ("/cmd_vel_smoothed", Twist, "plain"),
    ("/cmd_vel", Twist, "plain"),
]


def latched():
    return QoSProfile(depth=10, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Verifier(Node):
    def __init__(self):
        super().__init__("ui_path_verify")
        self.stats = {}
        self.odom = {"n": 0, "x0": None, "x1": None, "maxv": 0.0}
        self.lock = {"n": 0, "last": None, "t": None, "true_at": None}
        self.state = {"n": 0, "last": None, "reason": "", "t": None}

        for topic, msg_type, kind in HOPS:
            self._sub(topic, msg_type, kind)

        self.create_subscription(Odometry, "/odom", self._on_odom, 20)
        self.create_subscription(Bool, "/safety/stop_lock", self._on_lock, latched())

        try:
            from openamr_nav_msgs.msg import StopState
            self.create_subscription(StopState, "/safety/stop_state", self._on_state, latched())
        except Exception:
            self.get_logger().warning("openamr_nav_msgs unavailable: /safety/stop_state not recorded")

    def _sub(self, topic, msg_type, kind):
        self.stats[topic] = {"n": 0, "first": None, "last": None, "maxv": 0.0, "nonzero": 0, "last_nz": None}
        self.create_subscription(msg_type, topic, lambda m, t=topic, k=kind: self._on_cmd(t, k, m), 20)

    def _on_cmd(self, topic, kind, msg):
        s = self.stats[topic]
        tw = msg.twist if kind == "stamped" else msg
        v = abs(tw.linear.x)
        now = time.time()
        s["n"] += 1
        s["first"] = s["first"] or now
        s["last"] = now
        s["maxv"] = max(s["maxv"], v)
        if v > 1e-6:
            s["nonzero"] += 1
            s["last_nz"] = now

    def _on_odom(self, msg):
        self.odom["n"] += 1
        x = msg.pose.pose.position.x
        self.odom["x0"] = x if self.odom["x0"] is None else self.odom["x0"]
        self.odom["x1"] = x
        self.odom["maxv"] = max(self.odom["maxv"], abs(msg.twist.twist.linear.x))

    def _on_lock(self, msg):
        now = time.time()
        self.lock.update(n=self.lock["n"] + 1, last=bool(msg.data), t=now)
        if msg.data and self.lock["true_at"] is None:
            self.lock["true_at"] = now

    def _on_state(self, msg):
        self.state.update(n=self.state["n"] + 1, last=int(msg.state), reason=str(msg.reason), t=time.time())

    def report(self, t0):
        print(f"\n=== command path ({time.time()-t0:.1f}s window) ===")
        print(f"{'hop':22s} {'msgs':>6s} {'nonzero':>8s} {'max|v|':>8s}  first-after-start")
        for topic, _, _ in HOPS:
            s = self.stats[topic]
            first = f"{s['first']-t0:6.2f}s" if s["first"] else "   none"
            print(f"{topic:22s} {s['n']:6d} {s['nonzero']:8d} {s['maxv']:8.4f}  {first}")
        print(f"{'/odom':22s} {self.odom['n']:6d} {'':8s} {self.odom['maxv']:8.4f}")
        if self.odom["x0"] is not None:
            print(f"odom travel: {self.odom['x1'] - self.odom['x0']:.4f} m")
        lock_at = self.lock["true_at"]
        print(f"stop_lock: n={self.lock['n']} last={self.lock['last']} first_engaged={lock_at and round(lock_at - t0, 3)}s")
        if lock_at:
            print("lock -> last nonzero, per hop (negative = stopped before the lock landed):")
            for topic, _, _ in HOPS:
                lnz = self.stats[topic]["last_nz"]
                if lnz:
                    print(f"  {topic:22s} {(lnz - lock_at) * 1000:+7.0f} ms")
        print(f"stop_state: n={self.state['n']} last={self.state['last']} reason={self.state['reason']!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=float, default=25.0)
    args = ap.parse_args()

    rclpy.init()
    node = Verifier()
    t0 = time.time()
    try:
        while time.time() - t0 < args.window:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.report(t0)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
