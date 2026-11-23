#!/usr/bin/env python3
"""Does the public action refuse a goal while Stop is engaged?

This is the assumption mission control rests on: waypoint_nav sends NavigateToPose goals straight at
the public action, so if the proxy does not refuse while locked, a mission would be queued behind a
Stop instead of being rejected.
"""

import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger


class Probe(Node):
    def __init__(self):
        super().__init__("public_goal_while_locked")
        self.client = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self.engage = self.create_client(Trigger, "/safety/stop_lock_engage")
        self.release = self.create_client(Trigger, "/safety/stop_lock_release")


def call(node, cli, req):
    if not cli.wait_for_service(timeout_sec=15.0):
        return None
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=20.0)
    return fut.result()


def main():
    rclpy.init()
    p = Probe()

    print("engage:", getattr(call(p, p.engage, Trigger.Request()), "message", None))
    time.sleep(2)

    if not p.client.wait_for_server(timeout_sec=20.0):
        print("no action server on /navigate_to_pose")
        return

    goal = NavigateToPose.Goal()
    goal.pose = PoseStamped()
    goal.pose.header.frame_id = "map"
    goal.pose.header.stamp = p.get_clock().now().to_msg()
    goal.pose.pose.position.x = 1.0
    goal.pose.pose.orientation.w = 1.0

    send = p.client.send_goal_async(goal)
    rclpy.spin_until_future_complete(p, send, timeout_sec=20.0)
    handle = send.result()

    accepted = bool(handle and handle.accepted)
    print(f"sent on the PUBLIC action while Stop engaged -> accepted={accepted}")
    if accepted:
        print("  goal id:", bytes(handle.goal_id.uuid).hex()[:8])
        p.client._cancel_goal_async(handle) if hasattr(p.client, "_cancel_goal_async") else None
        handle.cancel_goal_async()

    time.sleep(2)
    print("release:", getattr(call(p, p.release, Trigger.Request()), "message", None))
    p.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
