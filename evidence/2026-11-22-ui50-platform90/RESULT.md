# Results — UI#50 × platform#90 operator path, 22 Nov 2026

Builds: platform `3aa17d2`, UI `21e95b9`. Served bundle `main.4566cb72.js`
(sha256 `d071b2ea…f1933`, identical to `web/build`, nothing in `web/src` newer than the build).

Every number below is from one session on the VM, one stack, one clock domain. Browser timings are
the browser's own clock; ROS-side timings are the guest's wall clock. Sim clock is slow at startup
(RTF well under 1), which shows up in the readiness numbers and is called out there.

## 1. The complete command path carries a UI command

Produced by holding the on-screen stick north for 3 s (an operator gesture; mouse events at the
stick's own centre, after dismissing the first-run overlay).

| hop | msgs | nonzero | max \|v\| |
|---|---|---|---|
| `/ui/cmd_vel` (TwistStamped, from the UI) | 62 | 61 | 0.1875 |
| `cmd_vel_joy` (relay output) | 239 | 235 | 0.1875 |
| `cmd_vel_mux` (twist_mux) | 155 | 127 | 0.1875 |
| `cmd_vel_gated` (safety gate) | 181 | 127 | 0.1875 |
| `cmd_vel_smoothed` (velocity_smoother) | 225 | 62 | 0.1875 |
| `/cmd_vel` (collision_monitor, final) | 197 | 53 | 0.1875 |
| `/odom` travel | — | — | 0.1168 m |

So the UI's own command reaches the base through every stage, and the value is preserved end to end.

## 2. Stop pressed while the robot is driving

Stop pressed at +13.2 s of a hold, robot moving at 0.1667 m/s; stick kept deflected for 2.5 s after the
press, then released.

| hop | last nonzero, relative to the lock landing |
|---|---|
| `/ui/cmd_vel` | **−86 ms** |
| `cmd_vel_joy` | −82 ms |
| `cmd_vel_mux` | −75 ms |
| `cmd_vel_gated` | −70 ms |
| `cmd_vel_smoothed` | −19 ms |
| `/cmd_vel` | **−12 ms** |

The whole chain is at zero **before** the lock sample arrives: the UI stops publishing on the press, and
the mux and smoother timeouts finish the tail. Travel for the whole run was 0.0633 m, of which the part
after the lock is nil — no nonzero command was issued after it.

## 3. Resume

- **Two-step by design:** `Resume` opens a "Release the software stop?" dialog; the release only fires
  from **`Confirm resume`**. My first three attempts pressed only the first button and produced no
  service call at all — a harness error, not a UI defect. Worth knowing for any script that drives this.
- **Press → drivable: 1606 ms** (first Resume + confirm, measured to the point the UI cleared the
  stop state and re-enabled the stick).
- **Resume starts no motion:** after Resume with the stick untouched, `/ui/cmd_vel` 0 messages,
  `/odom` 0.0000 m over 45 s, `stop_state` back to `2 RUNNING`.
- **Drive while stopped is refused with a reason:** with the lock engaged the stick is replaced by
  `manual drive disabled — Stopped (software)` and no message reaches `/ui/cmd_vel`.

## 4. Readiness on a clean boot — the one number that needs a caveat

Probe polls `/safety/stop_lock_release` every 2 s from a clean boot and **never sends a goal**:

```
 7.8s  service present
 7.8s  refused: clock not ready (current time: 0.00, required: 1.0)
 9.8s  refused: clock not ready (current time: 0.10, required: 1.0)
11.8s  refused: clock not ready (current time: 0.87, required: 1.0)
13.9s  refused: navigate_to_pose: action-status discovery grace period not yet elapsed
                 (goal-authority ledger read idle); navigate_through_poses: same
15.9s  RELEASED
```

**15.9 s is not a 15.9 s robot figure.** It decomposes into two unrelated things:

1. **≈12 s is the simulated clock crawling to 1.0 s of sim time** at startup on a GPU-less VM with
   Gazebo under software GL. The gate requires 1.0 s of clock before it will consider a release; on
   hardware sim time is wall time, so this term disappears.
2. **≈2 s is the ledger discovery grace** — the part that carries to the robot, and the part that
   matches D-13's 2 s bound.

So: the platform behaves as designed here, but this run **cannot** evidence D-13's "Resume available
within 2 s on a clean boot"; it only shows the ledger grace is ~2 s once the clock exists. That number
has to be taken on the robot, or in sim with a faster start (RTF near 1).

## 5. Operator-path facts that cost time and belong in the bench checklist

- The first-run wizard renders a **fixed full-screen overlay above every control**; until it is
  dismissed (Skip / Get started) nothing underneath is clickable, and nothing reports why. Any UI
  automation must dismiss it first.
- Resume is two-step (see §3) — a single press looks exactly like a dead control.
- `/safety/stop_lock` is latched, so the first sample after connecting can be the state from before
  the run. Judge transitions, not first reads.

## Not covered here

- The goal path (`/goal_pose` → forwarder → proxy) was verified on earlier heads and is not re-measured
  in this session.
- Anything on the robot: this is sim only, and per the 19 Nov ruling the bench robot runs a build with
  no gate.

## 6. Fault handling — rosbridge lost while driving

Killed `rosbridge_websocket` while the stick was held down at 0.19 m/s, kept holding through the
outage, then released.

**During the outage** the UI does not keep publishing — it has no transport to publish on, and it says
so rather than pretending:

```
manual drive:  "rosbridge disconnected"
banner:        "rosbridge is disconnected, so the lock state is unknown."
controls:      Resume disabled — "Resume needs a rosbridge connection."
               "Navigation goals are disabled: rosbridge disconnected."
               "Docking disabled: rosbridge disconnected"
console:       "Robot offline"
```

That is the fail-closed shape required of an operator UI: an unknown lock state is treated as stopped,
not as permissive, and every control names the reason.

**After rosbridge was restored** (note: relaunching the whole UI stack did *not* bring the socket back —
port 9090 stayed closed; starting `rosbridge_websocket` on its own did), the page reloaded to:

```
console:  "Robot connected"
banner:   "Stopped (software) — The platform stop lock is engaged.
           No manual drive, program or mission can run."
Resume:   available, and required
```

So a dropped connection neither leaves the robot drivable nor replays the command that was in flight:
on reconnect the UI re-reads the latched lock and hands control back to the operator only through an
explicit Resume.

Not measured here: the platform-side zeroing during the outage. `velocity_smoother`'s
`velocity_timeout: 0.3` is the mechanism, evidenced separately; this run is about the UI's behaviour.

Environment note for anyone repeating it: killing rosbridge and restarting the *whole* UI launch leaves
port 9090 closed while flask still serves 5050, which looks like "the UI never reconnects". Restart
`rosbridge_websocket` alone and the reconnect path behaves as above.

## 7. Defect found on the merged head: a cancel reports ABORTED

Measured after the merge, on `3aa17d2`, to check whether the review item had been fixed. It had not
been — what landed was the bounded wait for the public cancel to arrive, not the terminal-code mapping.

```
release: released
goal on /goal_pose   -> public=2 EXECUTING, real=2 EXECUTING
cancel (zero id)     -> return_code=0, cancelled_goals=1
  t+2s               -> public=5, real=5
FINAL public=5 (ABORTED)  real=5 (ABORTED)
odom travel during the probe: 0.4734 m      (the cancel did stop the robot)
```

The cancel is accepted and motion stops, so this is not a safety defect — it is a reporting one. A UI
that distinguishes "cancelled" from "failed" shows the operator's own cancel as a failure.

Cause, in `navigate_to_pose_goal_proxy_node.py` on `main`: only `STATUS_CANCELED` is special-cased;
`ABORTED` reaches the final `else: abort()`. The same shape is in
`navigate_through_poses_goal_proxy_node.py`, so both public actions are affected.

Filed as `openAMRobot/openamr-platform-sw#189` with reproduction, the two-line fix (map "cancel
requested" plus any non-success result to `canceled()`) and the test that is missing: a public cancel
whose real server ends ABORTED. Existing tests cover only the CANCELED case, which is why CI is green
with this in.

## 8. A goal on the public action is refused while Stop is engaged

This is the assumption mission control rests on. `waypoint_nav.py` executes missions with Nav2's
`BasicNavigator`, which sends `NavigateToPose` goals **straight at the public action** — the one the
proxy fronts — not through `/goal_pose`.

```
engage: already engaged
sent on the PUBLIC action while Stop engaged -> accepted=False
```

So the locked state is enforced for direct action clients as well, not only for the operator's
`/goal_pose` path: a mission cannot be queued behind a Stop. That was the substantive risk in the
mission path; what remains unmeasured is multi-step sequencing and Stop mid-mission, which need
waypoints loaded from a map.
