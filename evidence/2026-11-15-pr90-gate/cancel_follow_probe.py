#!/usr/bin/env python3
"""Cancel a goal while it is still executing, and follow that specific goal id to terminal.

Scoped deliberately: the status array keeps terminal goals for minutes, so watching "the last code"
reads someone else's history. This tracks one uuid.
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from std_srvs.srv import Trigger

NAMES = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELED", 4: "SUCCEEDED",
         5: "ABORTED", 6: "CANCELING"}


def transient():
    return QoSProfile(depth=80, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Probe(Node):
    def __init__(self):
        super().__init__("cancel_follow_probe")
        self.codes = {}
        self.pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.create_subscription(GoalStatusArray, "/navigate_to_pose/_action/status",
                                 self._on_status, transient())
        self.cancel = self.create_client(CancelGoal, "/navigate_to_pose/_action/cancel_goal")

    def _on_status(self, msg):
        for g in msg.status_list:
            gid = bytes(g.goal_info.goal_id.uuid).hex()[:8]
            codes = self.codes.setdefault(gid, [])
            if not codes or codes[-1] != g.status:
                codes.append(g.status)

    def spin(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)


def main():
    rclpy.init()
    p = Probe()
    p.spin(3.0)
    known = set(p.codes)

    goal = PoseStamped()
    goal.header.frame_id = "map"
    goal.header.stamp = p.get_clock().now().to_msg()
    goal.pose.position.x = 2.0            # far enough to still be driving when we cancel
    goal.pose.orientation.w = 1.0
    p.pub.publish(goal)

    new_id = None
    for _ in range(60):
        p.spin(1.0)
        fresh = [g for g in p.codes if g not in known]
        if fresh:
            new_id = fresh[0]
            break
    if not new_id:
        print("no new goal appeared on the public status")
        return
    print("new goal:", new_id, "codes so far:", [NAMES.get(c, c) for c in p.codes[new_id]])

    res = p.cancel.call_async(CancelGoal.Request()) if p.cancel.wait_for_service(timeout_sec=8.0) else None
    if res is None:
        print("cancel service unavailable")
        return
    rclpy.spin_until_future_complete(p, res, timeout_sec=10.0)
    out = res.result()
    print("cancel: return_code=%s goals_canceling=%s" % (out.return_code, len(out.goals_canceling)))

    for _ in range(20):
        p.spin(1.0)
        codes = p.codes.get(new_id, [])
        if codes and codes[-1] in (3, 4, 5):
            break
    print("final sequence:", [(NAMES.get(c, c)) for c in p.codes.get(new_id, [])])
    p.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
