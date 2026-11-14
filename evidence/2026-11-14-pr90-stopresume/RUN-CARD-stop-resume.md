# Run card — Gazebo Stop / Resume session on the fixed #90 head

Requested in Alex's 13 Nov review (item 5/6 flow): *"after the fix please run the Gazebo Stop and Resume
session on that head and post the record here."* This is the session to run once Kunal's
`/goal_pose` forwarder (item 1) is in.

## What it has to show

| Claim | Evidence |
|---|---|
| Stop works mid-motion | goal ends **CANCELED**, `/cmd_vel` reaches zero, robot stops moving |
| Stop is prompt | press → lock publish latency, and lock → zero on `/cmd_vel`, on **one** clock |
| Resume does not restart motion | after release, odom travel stays ~0 with no new goal (D-14) |
| Resume is a new goal | a second goal after release moves the robot again |

## Environment (the four things that break a clean boot here)

This VM has no GPU and a stale DDS domain table kills every node at startup, so the launch line alone
is not enough:

1. **Xvfb + software GL** — `Xvfb :99`, `DISPLAY=:99`, `LIBGL_ALWAYS_SOFTWARE=1`,
   `GALLIUM_DRIVER=llvmpipe`, `MESA_LOADER_DRIVER_OVERRIDE=llvmpipe`. Without it Gazebo segfaults in
   OgreNext (`Ogre::Hlms::createDatablock`).
2. **Cyclone participant index** — `MaxAutoParticipantIndex=256`, and clear `/dev/shm/cdds*` before the
   launch. The file is `cdds*`, not `cyclonedds_*`; cleaning the wrong pattern reproduces
   `Failed to find a free participant index for domain 0` for every node.
3. **Kill leftovers by split patterns** — `pkill -f "ros2 launch"` typed literally in an ssh command
   matches that command's own line and kills the session. Build the pattern from variables.
4. **Interfaces workspace first** — `source openamrobot-interfaces/.../install/setup.bash` before the
   platform workspace, or `safety_stop_gate_node` dies on `No module named 'openamr_nav_msgs'`.

Launcher used for the 14 Nov run: `run_pr90_navonly.sh` (nav-only profile, `use_docking:=false`).

## Sequence

```
# 1. stack up, then prove the graph is real before measuring anything
ros2 topic hz /odom                      # expect ~25 Hz
ros2 run tf2_ros tf2_echo odom base_link # expect a transform

# 2. release the lock — retry, the first call is refused during the grace period
ros2 service call /safety/stop_lock_release std_srvs/srv/Trigger "{}"
#   refused: 'action-status discovery grace period not yet elapsed'  -> wait ~10 s, call again

# 3. start a goal so there is real motion, then Stop mid-motion
ros2 topic pub --once /goal_pose geometry_msgs/msg/PoseStamped \
  "{header: {frame_id: map}, pose: {position: {x: 3.0}, orientation: {w: 1.0}}}"

# 4. engage Stop (or press the UI control — say which)
ros2 service call /safety/stop_lock_engage std_srvs/srv/Trigger "{}"

# 5. read the goal's terminal state, not just the chain
ros2 topic echo --once /navigate_to_pose/_action/status
ros2 action info /navigate_to_pose -t

# 6. Resume, and hold: no new goal for the window
ros2 service call /safety/stop_lock_release std_srvs/srv/Trigger "{}"
#   then: odom travel over the next 10 s must be ~0

# 7. only now send a second goal: it must move
```

## Recording

- `/cmd_vel`, `/odom`, `/safety/stop_lock`, `/safety/stop_state` and the action status with a shared
  `wall_ns` clock — `gate-a/cmd_recorder.py` already does this. Start it **before** the press with a
  long duration and kill it afterwards; a recorder window that ends early is the commonest wasted run.
- If the press is in the UI, timestamp it in the browser (CDP) so press→lock is on one clock. Do not
  compare a number from this session with one from another session — transport latency here moves by
  hundreds of ms with load.
- Record which control was pressed: the status-bar Stop and the manual-panel Stop are different
  elements with the same label.

## Posting

Numbers, not adjectives: press→lock ms, lock→zero ms, travel before/after lock, goal terminal state,
odom travel during the no-goal window, and the build (head SHA + `openamrobot_docking` build time).
Say plainly that this is flight-level sim evidence for a base with no E-stop chain, and that it is not
hardware.

## If it fails

A refusal on release is the contract working, not a bug: quote the `/safety/stop_state` reason rather
than calling it a stuck gate. An unqueryable graph or a missing control node is `EXIT_ERROR`, and
proves nothing — report it as unmeasured.
