#!/usr/bin/env python3
"""Stop during a goal: does that goal reach a terminal state?

Alex's gate row 3 requires the goal to end terminal when Stop is pressed mid-motion. A goal left in
6 (CANCELING) is not terminal: the UI shows a spinner forever and a cancel call afterwards finds
nothing to cancel (return_code 0, goals_canceling 0).

Follows one goal id from acceptance through Stop to whatever end it reaches.
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from action_msgs.msg import GoalStatusArray
from std_srvs.srv import Trigger

NAMES = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELED", 4: "SUCCEEDED",
         5: "ABORTED", 6: "CANCELING"}


def transient():
    return QoSProfile(depth=80, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Probe(Node):
    def __init__(self):
        super().__init__("stop_terminal_probe")
        self.codes = {}
        self.pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.create_subscription(GoalStatusArray, "/navigate_to_pose/_action/status",
                                 self._on_status, transient())
        self.release = self.create_client(Trigger, "/safety/stop_lock_release")
        self.engage = self.create_client(Trigger, "/safety/stop_lock_engage")

    def _on_status(self, msg):
        for g in msg.status_list:
            gid = bytes(g.goal_info.goal_id.uuid).hex()[:8]
            lst = self.codes.setdefault(gid, [])
            if not lst or lst[-1] != g.status:
                lst.append(g.status)

    def spin(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)

    def call(self, client):
        if not client.wait_for_service(timeout_sec=8.0):
            return None
        fut = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, fut, timeout_sec=10.0)
        return fut.result()


def main():
    rclpy.init()
    p = Probe()
    p.spin(3.0)

    for _ in range(6):
        r = p.call(p.release)
        if r is not None and getattr(r, "success", False):
            print("released:", r.message)
            break
        print("release refused:", getattr(r, "message", "?"))
        p.spin(6.0)
    p.spin(3.0)

    known = set(p.codes)
    goal = PoseStamped()
    goal.header.frame_id = "map"
    goal.header.stamp = p.get_clock().now().to_msg()
    goal.pose.position.x = 2.0
    goal.pose.orientation.w = 1.0
    p.pub.publish(goal)

    gid = None
    for _ in range(40):
        p.spin(1.0)
        fresh = [g for g in p.codes if g not in known]
        if fresh:
            gid = fresh[0]
            break
    if not gid:
        print("no new goal appeared")
        return
    print("goal:", gid, "->", [NAMES.get(c, c) for c in p.codes[gid]])

    p.spin(2.0)
    r = p.call(p.engage)
    print("engage:", getattr(r, "success", None), getattr(r, "message", ""))

    for _ in range(25):
        p.spin(1.0)
        codes = p.codes.get(gid, [])
        if codes and codes[-1] in (3, 4, 5):
            break
    seq = [NAMES.get(c, c) for c in p.codes.get(gid, [])]
    print("sequence after Stop:", seq)
    print("terminal:", seq[-1] if seq else "none", "| reached terminal:", bool(seq) and seq[-1] in ("CANCELED", "SUCCEEDED", "ABORTED"))
    p.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
