# 16 Nov — real-profile `EXPECT=0` run card

Purpose: show that on the v0.0.1 robot the real launch exposes **no** docking action servers, i.e.
D-19's "docking off" holds on the real profile. This evidences the *default*, not that the server
works.

## Command (validated on the VM against `docking_real.launch.py`, 14 Nov)

```bash
HARNESS_TIMEOUT_S=120 bash ros2/src/openamrobot_docking/test/docking_action_servers.sh \
  openamrobot_docking docking_real.launch.py 0 \
  --control-node detected_dock_pose_publisher \
  -- use_sim_time:=false launch_trigger:=false
```

Expected output and exit code **0**:

```
launch: ros2 launch openamrobot_docking docking_real.launch.py use_sim_time:=false launch_trigger:=false (expect 0 server(s) per action)
PASS: every action advertises 0 server(s) (control node /detected_dock_pose_publisher visible)
  /dock_robot: 0
  /undock_robot: 0
```

## Why this exact control node

With `launch_docking_server` off, `lifecycle_manager_docking` is **not started**, so it cannot serve
as the control node. Measured: with `--control-node lifecycle_manager_docking` the harness spends the
full timeout at `counts match but the control node is not visible` and exits **20** — a correct
refusal, but useless as evidence. `detected_dock_pose_publisher` starts regardless of docking, so it
separates "no servers" from "no graph".

## On the robot

- Needs the workspace built and `openamrobot_nav2` resolvable (the launch resolves
  `FindPackageShare('openamrobot_nav2')` at declaration time). Confirm with
  `ros2 pkg prefix openamrobot_nav2` before starting.
- Run it **before** anything powers motion. It launches its own stack; do not run it beside another
  bring-up.
- Record: the three lines above, `ros2 action info /dock_robot -t` and `/undock_robot -t`
  (`Action servers: 0` each), `ros2 pkg prefix openamrobot_nav2`, and the workspace commit +
  `openamrobot_docking` build time.
- If it exits 20, that is not a failure of the off-state — read the log for which half failed
  (graph unqueryable vs control node missing) and report it as unmeasured.

## Boundary

The VM run is launch-level evidence only: it shows the real profile's default starts no server. It is
not hardware, and it says nothing about the `/undock_robot` no-motion condition (D-19 condition 2),
which needs a docked state.
