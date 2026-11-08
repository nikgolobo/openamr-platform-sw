#!/usr/bin/env python3
"""S6 recorder: everything the Stop/Hold/Recovery criteria need, on the VM clock.

Records /safety/stop_lock, /safety/stop_state, the command chain and odom with one wall_ns clock
so the lock rising edge, the first zero on each hop and the travelled distance line up without
depending on the Mac's clock.

Usage: python3 s6_recorder.py out.jsonl [seconds]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool

try:
    from openamr_nav_msgs.msg import StopState
except Exception:  # noqa: BLE001
    StopState = None

TOPICS = ["/cmd_vel_joy", "/cmd_vel_mux", "/cmd_vel_gated", "/cmd_vel_smoothed", "/cmd_vel"]


class Rec(Node):
    def __init__(self, out):
        super().__init__("s6_recorder")
        self.set_parameters([Parameter("use_sim_time", value=True)])
        self.out = out
        self.create_subscription(Bool, "/safety/stop_lock", self.on_lock, 100)
        if StopState is not None:
            self.create_subscription(StopState, "/safety/stop_state", self.on_state, 100)
        for t in TOPICS:
            self.create_subscription(Twist, t, self.mk(t), 200)
        self.create_subscription(Odometry, "/odom", self.on_odom, 200)

    def w(self, rec):
        rec["wall_ns"] = time.time_ns()
        self.out.write(json.dumps(rec) + "\n")

    def on_lock(self, m):
        self.w({"topic": "/safety/stop_lock", "locked": bool(m.data)})

    def on_state(self, m):
        try:
            self.w({"topic": "/safety/stop_state", "state": int(m.state),
                    "reason": getattr(m, "reason", "")})
        except Exception:  # noqa: BLE001
            pass

    def mk(self, t):
        def cb(m):
            self.w({"topic": t, "lin": float(m.linear.x)})
        return cb

    def on_odom(self, m):
        self.w({"topic": "/odom", "x": float(m.pose.pose.position.x),
                "v": float(m.twist.twist.linear.x)})


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/s6.jsonl"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
    out = open(path, "w")
    rclpy.init()
    n = Rec(out)
    end = time.monotonic() + secs
    while time.monotonic() < end:
        rclpy.spin_once(n, timeout_sec=0.05)
    out.close()
    print(f"recorded {secs}s to {path}")
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
