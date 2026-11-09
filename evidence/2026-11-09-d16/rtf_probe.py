#!/usr/bin/env python3
"""Measure the Gazebo real-time factor: sim seconds per wall second.

Matters because a drive of N wall seconds covers N*RTF*speed metres, so a shortfall
against the commanded speed is usually the simulator, not the controller.

Usage: rtf_probe.py [seconds]
"""
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock

SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0


class Probe(Node):
    def __init__(self):
        super().__init__("rtf_probe")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.first = None
        self.last = None
        self.n = 0
        self.create_subscription(Clock, "/clock", self.cb, qos)

    def cb(self, m):
        t = m.clock.sec + m.clock.nanosec * 1e-9
        now = time.time()
        if self.first is None:
            self.first = (t, now)
        self.last = (t, now)
        self.n += 1


def main():
    rclpy.init()
    p = Probe()
    end = time.time() + SECS
    while time.time() < end:
        rclpy.spin_once(p, timeout_sec=0.1)
    if p.first is None or p.n < 5:
        print(f"no /clock traffic ({p.n} msgs) — is the stack up?")
        return 1
    sim_dt = p.last[0] - p.first[0]
    wall_dt = p.last[1] - p.first[1]
    rtf = sim_dt / wall_dt if wall_dt else float("nan")
    print(f"samples {p.n}  sim {sim_dt:.3f}s  wall {wall_dt:.3f}s  RTF {rtf:.3f}  ({1/rtf:.1f}x slower than real time)")
    print(f"at 0.20 m/s commanded, one wall-clock second covers {0.20 * rtf:.4f} m of ground")
    p.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
