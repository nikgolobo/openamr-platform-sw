# Gate A traces — 7 Nov 2026

Raw files behind the S7a / S6 / S6-latency / wall results posted to platform-sw #35 and ui #56.

**Build under test:** platform-sw `25f40022` + interfaces `cb83b22` (from `skunal3318` `feat/stop-state-msg`), ui `b50dee4` served bundle `main.6d3b3171.js`.
**Caveat on the driving runs:** the stop lock could not be released on the unpatched launch, so the docking server was started by hand and one send+cancel goal was issued per action before each run. Every driving trace below carries that workaround; the wall run used `collision_monitor` deactivated instead (it is not a Gate A scenario).

| file | what it is |
|---|---|
| `s7a_trace_20261107_1122.jsonl` | S7a run 1: `/ui/cmd_vel`, the four hops, `/odom`, `/clock`, one record per message |
| `s7a_trace_run2_1122.jsonl` | S7a run 2 |
| `s7a_trace_run3_1123.jsonl` | S7a run 3 |
| `s7b_1202.jsonl` | reconnect case: rosbridge killed mid-motion, restored, joystick still held |
| `s6_run4.jsonl` | S6: manual-panel Stop while driving, Hold, Recovery |
| `s6_statusbar.jsonl` | S6: status-bar Stop, same three parts |
| `s6_latency.json` | per-press frame timings from the browser's own websocket (press, engage request/reply, four cancels, lock publish) |
| `preflight_s7a_1111.json` | preflight record, `PASS: true` |
| `probe_outputs.json` | release-refusal probe, goal-populates-status probe, isolated velocity_smoother test, wall run summary |
| `wall_cm_off_1116.jsonl` | wall run with `collision_monitor` deactivated (odometry 2.544 → 5.125 m) |

Scripts: `s7a_trace.py`, `s6_recorder.py`, `s6_ui_stop.js`, `s6_latency.js`, `s7b_reconnect.js`.

## Numbers these files produce

- **S7a**, travel after the last `/ui/cmd_vel`: 0.1041 / 0.1087 / 0.1051 m (limit 0.15). Smoother zero 320–329 ms, `/cmd_vel` zero 340–348 ms.
- **S7a reconnect**: travel 0.0359 m after the last `/cmd_vel_joy`; 0 `/cmd_vel_joy` messages after reconnect with the stick still held.
- **S6 manual panel**: press→lock 0.313 s (two clocks, VM−Mac offset −2.325 s ± 0.028 measured over five multiplexed SSH round trips), lock→`/cmd_vel` zero 5.1 ms, travel 0.0063 m; Hold 0.0000 m/s; Recovery 0.0000 m/s then 0.124 m/s after neutral.
- **S6 status bar**: press→lock 2.425 s in that run; in the later single-clock measurement the lock publish arrived 66 ms (manual) and 259 ms (status bar) after the press, same handler, seconds apart — transport variance, not the control.
- **Wall**: odometry 2.544 → 5.125 m; `wall_1` spans 4.9–5.1 and a colliding 0.78 m base stops near 4.5.

## Reproduce

Source ROS 2 Jazzy plus the two workspaces, then:

```bash
python3 s7a_trace.py out.jsonl 4 15          # S7a: drive, cut, record
node s6_ui_stop.js                            # S6 (STOP_TARGET=statusbar for the other control)
node s6_latency.js                            # press→lock on one clock, from websocket frames
```

`SHA256SUMS` covers every `.jsonl` and `.json` in this directory.
