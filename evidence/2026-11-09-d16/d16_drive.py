#!/usr/bin/env python3
"""Drive the base into the wall at a fixed speed and record odom.

D-16 evidence: does the base stop at the wall, or pass through it? Odom is what
the stack believes; the Gazebo world pose (read separately) is ground truth.

Usage: d16_drive.py <cmd_topic> [speed] [seconds] [out.json]
"""
import json
import math
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

TOPIC = sys.argv[1] if len(sys.argv) > 1 else "/cmd_vel_joy"
SPEED = float(sys.argv[2]) if len(sys.argv) > 2 else 0.20
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0
OUT = sys.argv[4] if len(sys.argv) > 4 else "/tmp/d16_drive.json"

WALL_INNER_FACE = 4.90  # wall_1 spans x 4.90..5.10, origin x=+5, 0.2 m thick


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Driver(Node):
    def __init__(self):
        super().__init__("d16_driver")
        self.samples = []
        self.pub = self.create_publisher(Twist, TOPIC, 10)
        qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(Odometry, "/odom", self.on_odom, qos)
        self.create_subscription(Odometry, "/ground_truth/odom", self.on_gt, qos)
        self.cmd_log = []
        self.create_subscription(Twist, "/cmd_vel", self.on_cmd, qos)
        self.gt = None

    def on_cmd(self, m):
        self.cmd_log.append((time.time(), m.linear.x))

    def on_odom(self, m):
        p = m.pose.pose.position
        self.samples.append({
            "t": time.time(),
            "x": p.x, "y": p.y,
            "yaw_deg": math.degrees(yaw_of(m.pose.pose.orientation)),
            "twist_x": m.twist.twist.linear.x,
        })

    def on_gt(self, m):
        p = m.pose.pose.position
        self.gt = {"x": p.x, "y": p.y}


def main():
    rclpy.init()
    n = Driver()
    tw = Twist()
    tw.linear.x = SPEED

    # settle
    end = time.time() + 2.0
    while time.time() < end:
        rclpy.spin_once(n, timeout_sec=0.05)

    start = n.samples[-1] if n.samples else {"x": 0.0, "y": 0.0, "t": time.time()}
    print(f"start odom x={start['x']:.4f} y={start['y']:.4f}  topic={TOPIC} speed={SPEED}")

    t_end = time.time() + SECS
    last_pub = 0.0
    while time.time() < t_end:
        now = time.time()
        if now - last_pub > 0.05:          # 20 Hz, like a held stick
            n.pub.publish(tw)
            last_pub = now
        rclpy.spin_once(n, timeout_sec=0.02)

    # stop commanding, keep listening to see if it coasts or is still moving
    stop = n.samples[-1] if n.samples else start
    zero = Twist()
    for _ in range(10):
        n.pub.publish(zero)
        rclpy.spin_once(n, timeout_sec=0.02)

    coast_end = time.time() + 3.0
    while time.time() < coast_end:
        rclpy.spin_once(n, timeout_sec=0.05)

    final = n.samples[-1] if n.samples else stop
    max_x = max((s["x"] for s in n.samples), default=float("nan"))
    moved = final["x"] - start["x"]
    coast = final["x"] - stop["x"]

    print(f"stop  odom x={stop['x']:.4f}  final odom x={final['x']:.4f}  (max x={max_x:.4f})")
    print(f"travel total {moved:+.4f} m   after zero command {coast:+.4f} m")
    print(f"wall inner face x={WALL_INNER_FACE:.2f}; odom final - face = {final['x'] - WALL_INNER_FACE:+.4f} m")
    print("odom-only: NOT a contact verdict — odometry integrates wheel slip while the base is pinned "
          "(upperbody-sw#49). Read gz pose/info in the same run and compare, per d16_physics.sh.")
    if n.gt:
        print(f"ground-truth odom topic present: x={n.gt['x']:.4f}  (face delta {n.gt['x'] - WALL_INNER_FACE:+.4f})")

    json.dump({"topic": TOPIC, "speed": SPEED, "samples": n.samples,
               "cmd_log": n.cmd_log,
               "start_x": start["x"], "stop_x": stop["x"], "final_x": final["x"],
               "max_x": max_x, "wall_inner_face": WALL_INNER_FACE,
               "ground_truth": n.gt}, open(OUT, "w"), indent=1)
    if n.cmd_log:
        vals = [v for _, v in n.cmd_log]
        nz = [t for t, v in n.cmd_log if abs(v) > 1e-6]
        print(f"/cmd_vel: {len(vals)} msgs, min {min(vals):+.3f} max {max(vals):+.3f}, "
              f"nonzero {len(nz)}, last nonzero at t={nz[-1] - n.cmd_log[0][0]:.2f}s" if nz
              else f"/cmd_vel: {len(vals)} msgs, all zero")
    print(f"samples: {len(n.samples)} -> {OUT}")
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
