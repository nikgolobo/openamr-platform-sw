# #90 item 1 — /goal_pose goal invisible to the public status/cancel pair

Reproduction requested by Alex (13 Nov review, item 1) and chased by Kunal (14 Nov).

Head: `skunal3318:issue35-stop-gate` @ `d29dfc0`. Nav-only profile
(`openamrobot_bringup bringup.launch.py sim:=true use_docking:=false gui:=false`), Gazebo running,
both lifecycle managers active.

## Result

| Step | Observation |
|---|---|
| before | no status message on any action-status topic |
| `ros2 topic pub --once /goal_pose ... x=2.0` | goal appears on `/navigate_to_pose_real/_action/status` |
| `ros2 topic echo --once /navigate_to_pose/_action/status` | **no message at all** on the public name |
| `ros2 service call /navigate_to_pose/_action/cancel_goal "{}"` | `return_code=0`, `cancelled_goals=0` |
| after cancel | robot travelled 0.310 m further (0.272 m before the cancel) |

Two independent runs: 0.272 → 0.310 m and 0.444 → 0.465 m, both with `cancelled_goals=0`.
The robot drives; the public status/cancel pair has no handle on the goal.

## Workarounds in this run (not a clean-boot result)

- **Xvfb + software GL** (`LIBGL_ALWAYS_SOFTWARE=1`, `llvmpipe`, `DISPLAY=:99`): the VM has no GPU and
  Gazebo segfaults in OgreNext (`Ogre::Hlms::createDatablock`) without it.
- **`MaxAutoParticipantIndex=256` and cleared `/dev/shm/cdds*`**: a stale Cyclone participant table
  makes every node abort with `Failed to find a free participant index for domain 0`. Note the file
  is `cdds*`, not `cyclonedds_*` — cleaning the wrong pattern leaves the failure in place.
- **Lock release needed a retry**: the first `stop_lock_release` was refused with
  `action-status discovery grace period not yet elapsed` — the D-13 ledger on a fresh boot.
- Docking was off for the whole run.

## Files

- `goal_pose_visibility_probe.py` — one node: subscribes to the public and `_real` status topics,
  publishes one PoseStamped on `/goal_pose`, calls cancel with a zero goal id, samples `/odom`.
- `run_pr90_navonly.sh` — the launcher (cleanup, Xvfb, DDS env, launch).
- `bringup_navonly.log` — the bring-up this result was measured on.
