#!/usr/bin/env python3
"""Does a cancel the operator requests still end ABORTED on the merged head?

Follows one goal id: acceptance, EXECUTING, a zero-id cancel on the public action, then the terminal
code that goal reaches. Prints the cancel reply too, because return_code/rejected_goals are separate
facts from the goal's terminal status.
"""

import time

import rclpy
from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger

TERMINAL = {3: "CANCELED", 4: "SUCCEEDED", 5: "ABORTED"}


def latched():
    return QoSProfile(depth=50, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Probe(Node):
    def __init__(self):
        super().__init__("cancel_terminal_probe")
        self.by_id = {}
        self.order = []
        self.create_subscription(GoalStatusArray, "/navigate_to_pose/_action/status", self.on_status, latched())
        self.create_subscription(GoalStatusArray, "/navigate_to_pose_real/_action/status", self.on_real, latched())
        self.create_subscription(Odometry, "/odom", self.on_odom, 20)
        self.pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.release = self.create_client(Trigger, "/safety/stop_lock_release")
        self.cancel = self.create_client(CancelGoal, "/navigate_to_pose/_action/cancel_goal")
        self.travel = {"x0": None, "x1": None}

    def on_status(self, msg):
        for g in msg.status_list:
            k = bytes(g.goal_info.goal_id.uuid).hex()[:8]
            if k not in self.by_id:
                self.order.append(k)
            self.by_id.setdefault("pub", {})[k] = g.status

    def on_real(self, msg):
        for g in msg.status_list:
            k = bytes(g.goal_info.goal_id.uuid).hex()[:8]
            self.by_id.setdefault("real", {})[k] = g.status

    def on_odom(self, msg):
        x = msg.pose.pose.position.x
        self.travel["x0"] = x if self.travel["x0"] is None else self.travel["x0"]
        self.travel["x1"] = x

    def spin(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)


def call(client, req, node):
    if not client.wait_for_service(timeout_sec=10.0):
        return None
    fut = client.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=15.0)
    return fut.result()


def main():
    rclpy.init()
    p = Probe()
    p.spin(3)

    for i in range(4):
        res = call(p.release, Trigger.Request(), p)
        if res and res.success:
            print(f"release: {res.message}")
            break
        print(f"release attempt {i+1} refused: {getattr(res, 'message', None)}")
        p.spin(6)
    p.spin(2)

    goal = PoseStamped()
    goal.header.frame_id = "map"
    goal.header.stamp = p.get_clock().now().to_msg()
    goal.pose.position.x = 1.5
    goal.pose.orientation.w = 1.0
    p.pub.publish(goal)
    p.spin(4)

    mine = None
    for k in reversed(p.order):
        if p.by_id.get("pub", {}).get(k) in (1, 2):
            mine = k
            break
    print(f"goal id: {mine} public={p.by_id.get('pub', {}).get(mine)} real={p.by_id.get('real', {}).get(mine)}")
    if mine is None:
        print("no executing goal to cancel; aborting probe")
        return

    p.spin(2)
    res = call(p.cancel, CancelGoal.Request(), p)
    if res is not None:
        print(f"cancel reply: return_code={res.return_code} cancelled_goals={len(res.goals_canceling)}")

    deadline = time.monotonic() + 25
    last = None
    while time.monotonic() < deadline:
        p.spin(1)
        code = p.by_id.get("pub", {}).get(mine)
        if code != last:
            print(f"  t+{25 - int(deadline - time.monotonic()):2d}s public={code} real={p.by_id.get('real', {}).get(mine)}")
            last = code
        if code in TERMINAL:
            break

    final = p.by_id.get("pub", {}).get(mine)
    real = p.by_id.get("real", {}).get(mine)
    print(f"FINAL public={final} ({TERMINAL.get(final, 'not terminal')}) real={real} ({TERMINAL.get(real, 'not terminal')})")
    if p.travel["x0"] is not None:
        print(f"odom travel during probe: {p.travel['x1'] - p.travel['x0']:.4f} m")
    p.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
