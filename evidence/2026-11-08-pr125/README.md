# PR #125 acceptance evidence — 2026-11-08

Exact head: `defa291` (fix/123-start-docking-server, base main).
Build under test: platform-sw `25f40022` + interfaces `cb83b22` + this launch patch
(the twist_mux arbitration layer exists only on the issue35-stop-gate branch, so the
routing evidence was necessarily collected on that build).

| file | what it is |
|---|---|
| `dock_routing_evidence.txt` | the numbers: endpoints, the five-hop trace, Stop-during-dock, colcon test result |
| `dock_trace.py` | active DockRobot trace (counts/non-zero/max per hop, odom travel, action result) |
| `dock_stop_test.py` | dock goal + `/safety/stop_lock_engage` mid-motion, reports per-hop zeros and the action status |
| `undock_trace.py` | instrumentation for UndockRobot — **not run successfully**: an accepted-but-aborted undock emits no velocity |
| `dock_undock_sequence.py`, `dock_then_undock.py`, `run_125_undock.sh` | the three attempts to reach a docked state; see the PR comment for why each stopped |
| `run_125_acceptance.sh` | places the robot, releases the lock, runs the dock and captures `/cmd_vel` publishers mid-motion |

Reproduce: source ROS 2 Jazzy + the two workspaces, then run `run_125_acceptance.sh`.
