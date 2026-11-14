# Run card — Gazebo Stop / Resume + goal authority session on the fixed #90 head

Owner decision of 14 Nov (Alex) assigns this row to me, on the **exact final head** of #90:

> Gazebo session: UI goal, UI cancel, Stop during goal, goal while stopped, Resume, new goal after
> Resume, Nav2 restart, gate restart — evidence: SHA, launch command, goal IDs, status, `/cmd_vel` and
> odometry record.

Eight scenarios, one session, one clock. Nothing below is a pass unless it names the head it ran on.

## Preconditions

- Head = the one with Kunal's forwarder (item 1). Record the SHA before starting, and the
  `openamrobot_docking` / `openamrobot_nav2` build line.
- Nav-only profile: `bringup.launch.py sim:=true use_docking:=false gui:=false`.
- UI running against the sim (`start_ui.sh`), browser session up.
- Environment traps on this VM — all four bite on a clean boot:
  1. `Xvfb :99`, `DISPLAY=:99`, `LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`,
     `MESA_LOADER_DRIVER_OVERRIDE=llvmpipe` — otherwise Gazebo segfaults in OgreNext.
  2. `MaxAutoParticipantIndex=256` and clear `/dev/shm/cdds*` (not `cyclonedds_*`) before launch.
  3. Kill leftovers with patterns built from variables — a literal `pkill -f "ros2 launch"` in the ssh
     command kills that command's own session.
  4. Source the interfaces workspace before the platform one, or the gate dies on `openamr_nav_msgs`.
- Recorder started **before** the first action, long duration: `/cmd_vel`, `/odom`,
  `/safety/stop_lock`, `/safety/stop_state`, and both action status topics, one `wall_ns` clock.

## Scenarios

Record per row: what was done, goal ID, status transitions, max |v| on `/cmd_vel`, odom travel,
elapsed time. The UI press must be timestamped in the browser so press→lock is on one clock.

| # | Scenario | What must be true |
|---|---|---|
| 1 | **UI goal** — 2D Goal Pose in the map | goal accepted; **public** `/navigate_to_pose/_action/status` lists it (this is the fix: on `d29dfc0` it was absent); robot drives (odom travel > 0) |
| 2 | **UI cancel** — cancel the same goal from the UI | `cancel_goal` returns the goal in `goals_canceling`; status goes terminal (CANCELED); `/cmd_vel` reaches zero; odom travel stops |
| 3 | **Stop during goal** — send a goal, press Stop mid-motion | goal ends CANCELED; `/cmd_vel` zero; lock publish timestamp recorded; travel after lock recorded |
| 4 | **Goal while stopped** — send a goal with Stop engaged | goal **rejected**, forwarder logs the rejection and does not retry; **no nonzero `/cmd_vel`** at any hop |
| 5 | **Resume** — release with no new goal | no motion; odom travel ~0 over the window (D-14: Resume never restarts motion) |
| 6 | **New goal after Resume** | robot moves again — proves arithmetic of 5 is not a dead stack |
| 7 | **Nav2 restart** — restart Nav2 mid-session | forwarder starts with no goal and sends nothing; a still-running goal stays cancellable through the gate |
| 8 | **Gate restart** — restart the gate node | starts **locked**; the UI shows it; release still works after the grace period; no motion without a new pose |

## Evidence to post

One line per scenario: `scenario | result | key number (goal id / status / travel / max |v|)`, then:

- head SHA and the exact launch command,
- the recorder file (committed to an evidence branch, not pasted),
- which Stop control was pressed (status-bar vs manual panel — same label, different element),
- anything that needed a workaround, named — a workaround quietly included in a result is how a
  scenario gets recorded as passing on a configuration nobody else has.

## Boundaries to state in the post

This is flight-level simulation evidence for a base with no E-stop chain. It is not hardware
acceptance: command-stop on a topic is not physical stopping distance, and the controller's own
timeout, link-loss behaviour and the hardwired E-stop are separate bench gates owned by Evans.

## If a scenario fails

Name the blocker with its evidence and leave the PR open — Alex's words for this merge. A refusal on
release is the contract working (quote `/safety/stop_state`), not a stuck gate. `EXIT_ERROR` from the
harness (unqueryable graph, missing control node) proves nothing and is reported as unmeasured.
