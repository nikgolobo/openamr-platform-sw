# UI#50 + platform#90 — operator path verification, 22 Nov 2026

Assignment (Alex, #bench 22 Nov): verify Stop/Resume, `/safety/stop_lock`, readiness states and the
complete command path on the UI/platform pair, before the 17:00 CET release-scope decision.

## Builds under test

| Repo | Ref | SHA | How it ran |
|---|---|---|---|
| openamr-platform-sw | PR #90 `issue35-stop-gate` | `3aa17d2` | `bringup.launch.py sim:=true use_docking:=false gui:=false` |
| openamrobot-ui | PR #50 `ui/gate-a-command-path` | `21e95b9` | `openamr_ui_bringup ui.launch.py`, Flask :5050 + rosbridge :9090 |

Served bundle identity (the check that the browser ran today's code, not a stale asset):

```
web/build index  -> main.4566cb72.js
served index     -> main.4566cb72.js
sha256 served    -> d071b2ea141c7ac380b33b691bb43a40254eb14e10e123f9197e9475544f1933
sha256 web/build -> d071b2ea141c7ac380b33b691bb43a40254eb14e10e123f9197e9475544f1933
files in web/src newer than the build: 0
```

## Environment (carried in every result below)

VM without a GPU: Gazebo runs under `Xvfb :99` with software GL (`LIBGL_ALWAYS_SOFTWARE=1`,
`GALLIUM_DRIVER=llvmpipe`), CycloneDDS with `MaxAutoParticipantIndex=256` and `/dev/shm/cdds*` cleared
before launch. None of this changes the command path under test; it is recorded because it changes
timing.

## Method

- **`ui_path_verify.py`** (guest) subscribes every hop at once and reports, per hop, message count,
  nonzero count, max |linear.x| and time of first message, plus `/safety/stop_lock` and
  `/safety/stop_state`. A hop that carries messages but never a nonzero is distinguished from a hop
  that carries nothing.
- **`ui50_pair_verify.js`** (Mac, puppeteer over CDP) drives the real operator UI: Resume presses,
  joystick drag, Stop press, an attempted drag while stopped, Resume again. Timestamps are the
  browser's own clock; screenshots at each step.
- **`release_ready_probe.py`** (guest) polls `/safety/stop_lock_release` every 2 s from a clean boot
  and **never sends a goal** — the D-13 clean-boot condition.

## Results

*(filled in as the runs complete — see RESULT.md)*
