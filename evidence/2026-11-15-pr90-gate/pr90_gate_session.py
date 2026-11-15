#!/usr/bin/env python3
"""#90 gate session: goal authority + stop path, one clock, one run.

Covers Alex's 14 Nov gate rows that can be driven in one live session:
  1 UI goal (same /goal_pose the UI publishes) -> public status lists it, robot drives
  2 UI cancel (zero-id cancel on the public action) -> it is returned and the robot stops
  3 Stop during a goal -> goal ends terminal, /cmd_vel zero, travel after the lock recorded
  4 Goal while Stop is active -> rejected, no goal on the public status, no nonzero /cmd_vel
  5 Resume with no new goal -> no motion
  6 New goal after Resume -> motion again

Rows 7 (Nav2 restart) and 8 (gate restart) are separate process-level steps and are not in here.

Every action is timestamped on this machine's clock; status is read on the PUBLIC action name,
which is the thing the fix is about.
"""

import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry
from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from std_srvs.srv import Trigger


def transient():
    return QoSProfile(depth=50, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Session(Node):
    def __init__(self):
        super().__init__("pr90_gate_session")
        self.status = []      # (wall, [uuid...], [status codes])
        self.cmd = []         # (wall, linear.x)
        self.odom = []        # (wall, x)
        self.stop_state = None
        self.pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.create_subscription(GoalStatusArray, "/navigate_to_pose/_action/status",
                                 self._on_status, transient())
        self.create_subscription(Twist, "/cmd_vel", lambda m: self.cmd.append((time.time(), m.linear.x)), 30)
        self.create_subscription(Odometry, "/odom", lambda m: self.odom.append((time.time(), m.pose.pose.position.x)), 30)
        self.create_subscription(__import__("openamr_nav_msgs.msg", fromlist=["StopState"]).StopState,
                                 "/safety/stop_state", self._on_state, transient())
        self.cancel = self.create_client(CancelGoal, "/navigate_to_pose/_action/cancel_goal")
        self.release = self.create_client(Trigger, "/safety/stop_lock_release")
        self.engage = self.create_client(Trigger, "/safety/stop_lock_engage")

    def _on_status(self, msg):
        ids = [bytes(g.goal_info.goal_id.uuid).hex()[:8] for g in msg.status_list]
        codes = [g.status for g in msg.status_list]
        self.status.append((time.time(), ids, codes))

    def _on_state(self, msg):
        self.stop_state = msg.state

    def spin(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)

    def call(self, client, label, wait=8.0):
        if not client.wait_for_service(timeout_sec=wait):
            return f"{label}: service unavailable"
        fut = client.call_async(Trigger.Request() if client.srv_type is Trigger else client.srv_type.Request())
        rclpy.spin_until_future_complete(self, fut, timeout_sec=wait)
        return fut.result()

    def goal_ids_since(self, t0):
        """Last status snapshot after t0 — the array is a live list, not an event log, so unioning
        snapshots double-counts goals that persist across many messages."""
        latest = None
        for wall, ids, codes in self.status:
            if wall >= t0:
                latest = (ids, codes)
        return latest if latest else ([], [])

    def travel_since(self, t0):
        xs = [x for wall, x in self.odom if wall >= t0]
        return (max(xs) - min(xs)) if len(xs) > 1 else 0.0

    def max_cmd_since(self, t0):
        vs = [abs(v) for wall, v in self.cmd if wall >= t0]
        return max(vs) if vs else 0.0

    def wait_for_state(self, want, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.stop_state == want:
                return True
        return False

    def last_nonzero_after(self, t0):
        ts = [w for w, v in self.cmd if w >= t0 and abs(v) > 1e-3]
        return max(ts) if ts else None

    def send_goal(self, x=3.0):
        p = PoseStamped()
        p.header.frame_id = "map"
        p.header.stamp = self.get_clock().now().to_msg()
        p.pose.position.x = x
        p.pose.orientation.w = 1.0
        self.pub.publish(p)
        return time.time()


def main():
    rclpy.init()
    s = Session()
    s.spin(2.0)
    out = []

    # lock must be released before anything can move; first call is refused in the grace period
    released = False
    for attempt in range(6):
        r = s.call(s.release, "release")
        ok = getattr(r, "success", False)
        out.append(f"release attempt {attempt + 1}: {getattr(r, 'message', r)}")
        if ok:
            released = True
            break
        s.spin(6.0)
    if not released:
        print("\n".join(out)); print("FAIL: could not release the lock; nothing below is measurable")
        return

    # The forwarder caches stop_state and starts LOCKED: wait for RUNNING before the first pose,
    # otherwise goal 1 is rejected for a stale-state reason and the run measures nothing.
    if not s.wait_for_state(2, 25.0):
        print("FAIL: stop_state never reached RUNNING (got %s)" % s.stop_state)
        return
    out.append(f"stop_state=RUNNING after release (state={s.stop_state})")

    # 1 - goal is visible on the public action and the robot drives
    t0 = s.send_goal(3.0)
    s.spin(6.0)
    ids, codes = s.goal_ids_since(t0)
    out.append(f"[1] UI-equivalent goal on /goal_pose -> public status ids={ids} codes={codes} "
               f"travel={s.travel_since(t0):.3f} m max|v|={s.max_cmd_since(t0):.3f} m/s")

    # 2 - cancel through the public action stops it
    t1 = time.time()
    if s.cancel.wait_for_service(timeout_sec=8.0):
        fut = s.cancel.call_async(CancelGoal.Request())
        rclpy.spin_until_future_complete(s, fut, timeout_sec=10.0)
        res = fut.result()
        out.append(f"[2] cancel -> return_code={res.return_code} cancelled={len(res.goals_canceling)}")
    else:
        out.append("[2] cancel service unavailable")
    s.spin(5.0)
    ids2, codes2 = s.goal_ids_since(t1)
    out.append(f"[2] after cancel: codes={codes2} travel={s.travel_since(t1):.3f} m "
               f"max|v|={s.max_cmd_since(t1):.3f} m/s")

    # 3 - Stop during a goal
    t2 = s.send_goal(4.0)
    s.spin(3.0)
    moving = s.max_cmd_since(t2)
    r = s.call(s.engage, "engage")
    t_lock = time.time()
    out.append(f"[3] engage -> {getattr(r, 'success', None)} {getattr(r, 'message', '')} "
               f"(was moving at up to {moving:.3f} m/s)")
    s.spin(6.0)
    ids3, codes3 = s.goal_ids_since(t2)
    # Two different questions: does anything still move once the lock has settled, and how long
    # did the last command take to die (commands already in flight at the instant of the lock are
    # not evidence of a failure to stop).
    last_nz = s.last_nonzero_after(t_lock)
    delta = (last_nz - t_lock) * 1000.0 if last_nz else float("nan")
    settle = t_lock + 0.5
    out.append(f"[3] after stop: codes={codes3} lock->last_nonzero={delta:.0f} ms "
               f"travel_after_lock={s.travel_since(t_lock):.3f} m "
               f"max|v|_settled={s.max_cmd_since(settle):.3f} m/s")

    # 4 - goal while stopped must be rejected
    t3 = s.send_goal(2.0)
    s.spin(4.0)
    ids4, codes4 = s.goal_ids_since(t3)
    out.append(f"[4] goal while stopped: new ids={ids4} max|v|={s.max_cmd_since(t3):.3f} m/s "
               f"(stop_state={s.stop_state})")

    # 5 - Resume with no new goal: no motion
    r = s.call(s.release, "release2")
    t4 = time.time()
    s.spin(6.0)
    out.append(f"[5] resume -> {getattr(r, 'success', None)}; travel_since_release="
               f"{s.travel_since(t4):.3f} m max|v|={s.max_cmd_since(t4):.3f} m/s")

    # 6 - new goal after Resume moves again
    t5 = s.send_goal(3.5)
    s.spin(6.0)
    ids6, codes6 = s.goal_ids_since(t5)
    ids6 = list(dict.fromkeys(ids6))
    out.append(f"[6] new goal after resume: ids={ids6} travel={s.travel_since(t5):.3f} m "
               f"max|v|={s.max_cmd_since(t5):.3f} m/s")

    print("\n".join(out))
    s.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
