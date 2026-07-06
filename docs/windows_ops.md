# Windows operations guide (production box)

The engine, watchdog, and IB Gateway run on the owner's Windows machine. This doc covers the
OS-level plumbing slice 4.0 is responsible for documenting; the jobs themselves are built in
slices 4.5–4.7.

## Prerequisites

- **Python 3.12** (python.org installer, "Add to PATH" checked) and **uv**
  (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`). From the repo root: `uv sync`.
- **tzdata**: Python's `zoneinfo` has no IANA timezone database on Windows. The `tzdata` PyPI
  package must be a hard dependency before any session/calendar code ships (slice 4.1) —
  without it, `ZoneInfo("America/Chicago")` raises `ZoneInfoNotFoundError` on Windows and every
  session-window/entry-time computation is wrong or dead. All internal timestamps are UTC;
  exchange timezones are used only at the session-calendar edge.
- **IB Gateway** (stable channel, not latest) + IBKR paper login. Market-data subscriptions
  (US Securities Snapshot & Futures Value Bundle) must be active on the account — OWNER item.

## Clock sync (w32tm)

Bar alignment, event blackouts, and the MOC-approximate S2 entry all assume a sane clock.
Windows' default sync cadence is far too loose. As Administrator:

```bat
w32tm /config /manualpeerlist:"time.windows.com,0x9 pool.ntp.org,0x9" /syncfromflags:manual /update
net stop w32time && net start w32time
w32tm /resync /rediscover
```

Verify drift (target: well under 1 s offset):

```bat
w32tm /query /status
w32tm /stripchart /computer:pool.ntp.org /samples:5 /dataonly
```

Schedule `w32tm /resync` daily (see Task Scheduler below). If offset ever exceeds ~2 s,
treat it as an incident: halt new entries until resynced.

## IB Gateway auto-restart

- IB Gateway restarts itself daily (Configure → Settings → Lock and Exit → *Auto restart*).
  Set the restart time **inside IBKR's North-America server reset window (23:45–00:45 ET)
  and outside our entry session** (e.g. 00:00 ET), so the nightly Gateway restart and the
  broker-side reset produce one disconnect cycle, not two.
  The engine must treat the resulting disconnect as expected: reconnect,
  run full reconciliation vs journal (slice 4.5), resume.
- Auto-restart works ~6 days; the weekly full authentication (Sunday) still requires either
  2FA via IBKR Mobile or the "Seamless re-authentication" setting where available. Document
  the observed weekly behavior during the 4.5 paper soak.
- Consider IBC (github.com/IbcAlpha/IBC) for headless start/restart once manual operation
  is proven; do not add it before the chaos drills pass without it.
- Gateway API settings: enable ActiveX/Socket clients, bind to 127.0.0.1 only, note the port
  (paper default 4002), disable "Read-Only API" only when the OMS slice needs order entry.

## Task Scheduler jobs (registered in slices 4.5–4.7)

| Job | Schedule | Command (from repo root) | Notes |
|---|---|---|---|
| Clock resync | daily 06:00 local | `w32tm /resync` | run as SYSTEM, highest privileges |
| Engine start | at logon + daily after Gateway restart | `uv run python -m qt.engine` (4.5) | restart-on-failure: 3 retries, 1 min apart |
| Watchdog | at logon, restart every 5 min if dead | `uv run python -m qt.watchdog` (4.6) | separate process, never same job as engine |
| Nightly reconciliation | daily 22:30 local | `uv run python -m qt.recon` (4.6) | vs IBKR Flex report |
| Weekly tracking report | Mon 07:00 local | `uv run python -m qt.reports.weekly` (4.7) | paper-campaign bands |
| RTT re-baseline | monthly | `uv run python scripts/measure_rtt.py --note "production baseline"` | keep history |

Task Scheduler settings for every job: "Run whether user is logged on or not", "Run with
highest privileges" only where required (w32tm), stop-if-runs-longer-than disabled for the
engine, enable task history. Power settings: disable sleep/hibernate; set active hours; on a
laptop, require AC power.

## RTT baseline

Run from THIS machine (numbers from any other network are not the deployment baseline):

```bat
uv run python scripts/measure_rtt.py --note "production baseline"
```

Output lands in `data/baseline_rtt.json` (median, p95, jitter per endpoint). The checked-in
file from the build container is a smoke test only — overwrite it from production before 4.5.

## Kill switch / HALT semantics (operator view)

- `daily_loss_halt` trips → no new entries until next session; exits still work. No action.
- `kill_drawdown_hwm` trips → cancel-all, flatten, `HALT` flag file written, Telegram alert.
  The engine refuses to start while the flag exists. Re-arm is MANUAL: investigate, then
  delete the flag file. Never delete the flag as a reflex.
