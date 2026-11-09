# D-16 wall contact + odom/physics divergence, 9 Nov 2026

Build: platform-sw `origin/main` = 4926f406d65dee1a55cf078fa45e4f34d7e33b02, built in a separate
worktree (`~/p105_main/ros2`, all 7 packages). World `walled_world`, wall_1 at x=+5.0, 0.2 m thick
(inner face 4.900). base_link collision box 0.780 m long.

Workaround, disclosed: at this head the stop gate cannot be released (no /dock_robot server —
#123/#124), so safety_stop_gate_node, velocity_smoother and nav2_collision_monitor were stopped and
/cmd_vel was commanded directly. This measures Gazebo contact, not the arbitration chain.

## Result

| | physics (gz pose/info) | odometry |
|---|---|---|
| start | 0.0006 | 0.0000 |
| after 40 s at 0.20 m/s | 3.1726 | 3.1720 |
| after a further 95 s commanding into the wall | 4.5101 (frozen, two reads 6 s apart) | 11.2074 |

4.51014 + 0.390 = 4.90014 against a face at 4.90000: front face on the wall to 0.14 mm, stable.
The base does not pass through. Odometry accumulated 6.697 m of travel the base never made —
wheel slip while pinned. Same class as openamrobot-upperbody-sw#49.

## Withdrawn claim

An earlier report of pass-through on `a23bca14` was odometry-based (odom x=5.125 inside the wall
span). Withdrawn as a physics claim; it stands only as an odometry observation.

## Scripts

- `d16_boot_main.sh` — fresh boot of main, headless; prints world and model list.
- `d16_physics.sh` — stops the arbitration, records physics pose before/after.
- `d16_drive.py` — publishes a fixed Twist, records /odom and /cmd_vel. Prints NO contact verdict;
  odom alone is not one.
- `motion_truth.py` — prints physics x next to odom x and their gap. Run this before believing any
  motion number in this sim.

## Real-time factor, and a correction to an earlier caveat

I first wrote that the run "moved at ~0.08 m/s rather than the commanded 0.20", implying a control
anomaly. It is not one. `rtf_probe.py` on the same stack: **RTF 0.384** (sim 3.840 s per 9.997 s wall,
load average 24.7). At 0.20 m/s commanded that is **0.0768 m of ground per wall second**, against the
0.0793 m/s measured (3.172 m in 40 s). The shortfall was the simulator running 2.6x slower than real
time, not slip or a velocity ceiling.

So the wall runs are consistent throughout: 135 s of wall-clock driving is ~52 s of sim, ~10 m of
commanded travel, of which the base made 4.51 m and then stopped at the wall while the wheels kept
turning. The contact conclusion is unchanged — it is if anything better supported, because the
approach phase matches the commanded speed once RTF is accounted for.

## Not established

Behaviour under the arbitration chain (cannot move at this head), speeds above 0.20 m/s, angled or
corner contacts, the other three walls, hardware. Effective speed was ~0.08 m/s, not the commanded
0.20, so this is not a speed-matched contact test.
