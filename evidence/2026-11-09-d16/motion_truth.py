#!/usr/bin/env python3
"""Report the physics truth for a Gazebo model next to what odometry believes.

Why this exists: in this sim odometry can report metres of travel while the base is
physically pinned (upperbody-sw#49). Any motion claim has to be made in the physics
frame, with odom quoted beside it and the divergence named.

Usage: motion_truth.py [model] [world]
Prints one line per read, plus the odom-vs-physics gap.
"""
import subprocess
import sys

import rclpy
from nav_msgs.msg import Odometry
from rclpy.qos import QoSProfile, ReliabilityPolicy

MODEL = sys.argv[1] if len(sys.argv) > 1 else "openamrobot"


def world_x(world):
    """Read the model's x from the physics engine, not from ROS."""
    out = subprocess.run(["gz", "topic", "-e", "-t", f"/world/{world}/pose/info", "-n", "1"],
                         capture_output=True, text=True, timeout=30).stdout
    block = out.split(f'name: "{MODEL}"', 1)
    if len(block) < 2:
        return None
    for line in block[1].splitlines():
        s = line.strip()
        if s.startswith("x:"):
            return float(s.split(":")[1])
    return None


def odom_x():
    rclpy.init()
    node = rclpy.create_node("motion_truth_probe")
    got = {}
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

    def cb(m):
        got["x"] = m.pose.pose.position.x

    node.create_subscription(Odometry, "/odom", cb, qos)
    end = node.get_clock().now().nanoseconds + 5_000_000_000
    while "x" not in got and node.get_clock().now().nanoseconds < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
    return got.get("x")


def main():
    world = None
    for cand in ("walled_world", "empty"):
        if world_x(cand) is not None:
            world = cand
            break
    if world is None:
        print("could not read a world pose for", MODEL)
        return 1

    w1 = world_x(world)
    o1 = odom_x()
    w2 = world_x(world)
    print(f"world={world} model={MODEL}")
    print(f"physics x: {w1:.4f} -> {w2:.4f}")
    print(f"odom    x: {o1 if o1 is None else round(o1, 4)}")
    if o1 is None:
        print("no /odom sample: cannot compute divergence")
    else:
        print(f"physics-odom gap: {w2 - o1:+.4f} m  (nonzero gap = the run is contaminated or odom has slipped)")
    print("Truth is the physics column. Odom is the stack's belief (upperbody-sw#49).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
