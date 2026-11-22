#!/usr/bin/env python3
"""How long after a clean boot can the operator release the stop lock?

Polls /safety/stop_lock_release every 2 s and never sends a goal, which is exactly the D-13
condition: Resume must be available on a clean boot with no goal ever sent, within 2 s.
Prints one line per attempt with elapsed seconds from the first poll and the refusal reason.
"""

import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger


def main() -> None:
    rclpy.init()
    node = Node("release_ready_probe")
    cli = node.create_client(Trigger, "/safety/stop_lock_release")

    t0 = time.time()
    if not cli.wait_for_service(timeout_sec=150.0):
        print(f"{time.time()-t0:6.1f}s  service never appeared")
        rclpy.shutdown()
        return

    print(f"{time.time()-t0:6.1f}s  service present; polling")
    deadline = t0 + 180.0
    first_ok = None
    while time.time() < deadline:
        fut = cli.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(node, fut, timeout_sec=10.0)
        res = fut.result()
        el = time.time() - t0
        if res is None:
            print(f"{el:6.1f}s  no reply")
        elif res.success:
            print(f"{el:6.1f}s  RELEASED: {res.message}")
            first_ok = el
            break
        else:
            print(f"{el:6.1f}s  refused: {res.message[:140]}")
        time.sleep(2.0)

    if first_ok is None:
        print("never released within 180 s")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
