# #90 gate row — goal authority and stop path, 15 Nov 2026

Head: `e5f8d6aa` (Kunal's `goal_pose_forwarder_node` + full-chain test). Nav-only profile
(`bringup.launch.py sim:=true use_docking:=false gui:=false`), Gazebo running, both lifecycle
managers active, exactly one forwarder and one proxy on the graph.

## Results

| Row | Result |
|---|---|
| 1 UI goal (same `/goal_pose` the UI publishes) | **pass** — goal on the public status (`EXECUTING`), travel 0.283 m, max \|v\| 0.200 |
| 2 UI cancel (zero-id cancel on the public action) | **pass** — `cancelled=1`, goal terminal, command zeroes |
| 3 Stop during a goal | **FAIL (status)** — public status stuck at `6 CANCELING`, real server `5 ABORTED`; never terminal |
| 4 Goal while Stop engaged | **pass** — rejected, no goal on the public status, no nonzero `/cmd_vel` |
| 5 Resume, no new goal | **pass** — travel 0.000 m over 6 s (D-14) |
| 6 New goal after Resume | **pass** — travel 0.345 m, max \|v\| 0.200 |

## The row-3 defect

```
/navigate_to_pose/_action/status        status: 6  CANCELING
/navigate_to_pose_real/_action/status   status: 5  ABORTED
[goal_pose_forwarder]: navigate_to_pose goal reached terminal status 6
```

6 is CANCELING, not terminal (terminal: 3 CANCELED, 4 SUCCEEDED, 5 ABORTED). Treatment of 6 as
terminal stops tracking before the goal resolves, so the public status never advances. Reproduced
twice: Stop mid-goal, and an unreachable pose aborted by the planner (real 5, public 6).

Motion is safe — `/cmd_vel` reached zero 44 ms after the lock, settled `max|v|` 0.000 — so this is a
reporting defect, not a stopping one. A UI reading the public name shows the goal cancelling forever,
and a cancel in that state returns `cancelled_goals=0`.

## Environment trap worth keeping

A first attempt had **two forwarders and two proxies**: `ros2 launch` is a supervisor, so an earlier
stack's children survived it and the second launch joined them. The forwarder then logged
`Ignoring unexpected goal response. There may be more than one action server for 'navigate_to_pose'`
and **one pose became two goals** — a silent duplicate rather than an error. `clean_graph.sh` empties
the graph (killing `ros2 launch` is not enough); verify single instances before measuring.

Other workarounds, stated plainly: Xvfb + software GL (no GPU on this VM, Gazebo segfaults in
OgreNext otherwise), `MaxAutoParticipantIndex=256` and `/dev/shm/cdds*` cleared, release retried once
after the grace period.

## Not yet run

The UI-driven pass (rows 1-2 through the actual UI with browser-timestamped presses), Nav2 restart,
gate restart. All must be on the final head.
