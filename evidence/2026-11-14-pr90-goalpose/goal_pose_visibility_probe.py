#!/usr/bin/env python3
"""Reproduce Alex's #90 item 1: is a UI-style /goal_pose goal visible to status/cancel?

Runs three things in one node so the ordering is unambiguous:

  1. subscribes to the *public* action status names the UI reads;
  2. publishes one PoseStamped on /goal_pose, exactly as the UI map does;
  3. after the goal would have been accepted, calls cancel_goal with a zero goal id
     (what the UI's Stop/Cancel sends) and reports what came back.

Odometry is sampled before, between and after, so "the robot drives" and "the cancel changed
nothing" are observations rather than assumptions.
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from action_msgs.srv import CancelGoal


def qos():
    return QoSProfile(depth=20, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Probe(Node):
    def __init__(self):
        super().__init__("goal_pose_visibility_probe")
        self.status_msgs = []          # (topic, wall_ns, goals)
        self.odom = []                 # (wall_ns, x, y)
        self.pub_goal = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 20)
        for topic in ("/navigate_to_pose/_action/status",
                      "/navigate_to_pose_real/_action/status",
                      "/navigate_through_poses/_action/status"):
            self.create_subscription(
                __import__("action_msgs.msg", fromlist=["GoalStatusArray"]).GoalStatusArray,
                topic, lambda msg, t=topic: self._on_status(t, msg), qos())
        self.cancel = self.create_client(CancelGoal, "/navigate_to_pose/_action/cancel_goal")

    def _on_status(self, topic, msg):
        self.status_msgs.append((topic, time.time_ns(), len(msg.status_list)))

    def _on_odom(self, msg):
        p = msg.pose.pose.position
        self.odom.append((time.time_ns(), p.x, p.y))

    def spin_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.2)

    def summary_status(self):
        if not self.status_msgs:
            return "no status message at all"
        out = {}
        for topic, _, n in self.status_msgs:
            out.setdefault(topic, []).append(n)
        return "; ".join(f"{t}: {v}" for t, v in out.items())


def main():
    rclpy.init()
    node = Probe()
    node.spin_for(2.0)
    print(f"[before] odom samples={len(node.odom)} last={node.odom[-1][1:] if node.odom else None}")
    print(f"[before] status: {node.summary_status()}")

    goal = PoseStamped()
    goal.header.frame_id = "map"
    goal.header.stamp = node.get_clock().now().to_msg()
    goal.pose.position.x = 2.0
    goal.pose.orientation.w = 1.0
    node.pub_goal.publish(goal)
    print("[publish] one PoseStamped on /goal_pose at x=2.0 (what the UI map sends)")

    node.spin_for(6.0)
    moved = (node.odom[-1][1] - node.odom[0][1]) if len(node.odom) > 1 else float("nan")
    print(f"[after 6 s] status: {node.summary_status()}")
    print(f"[after 6 s] odom travel: {moved:.3f} m over {len(node.odom)} samples")

    x_before_cancel = node.odom[-1][1] if node.odom else float("nan")
    if node.cancel.wait_for_service(timeout_sec=5.0):
        req = CancelGoal.Request()          # empty: zero goal id, cancels all
        future = node.cancel.call_async(req)
        rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
        res = future.result()
        if res is None:
            print("[cancel] no reply within 10 s")
        else:
            print(f"[cancel] return_code={res.return_code} cancelled_goals={len(res.goals_canceling)}")
    else:
        print("[cancel] service /navigate_to_pose/_action/cancel_goal unavailable")

    node.spin_for(6.0)
    x_after_cancel = node.odom[-1][1] if node.odom else float("nan")
    print(f"[after cancel] status: {node.summary_status()}")
    print(f"[after cancel] odom travel since cancel: {x_after_cancel - x_before_cancel:.3f} m")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
