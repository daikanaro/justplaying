# QuantTrader

Systematic futures trading, IBKR paper first. The authoritative build spec is
[BUILD_PLAN.md](BUILD_PLAN.md); session rules for Claude Code are in [CLAUDE.md](CLAUDE.md).

## Setup

```sh
uv sync
uv run pytest && uv run mypy && uv run ruff check .
```

## Layout

- `config/` — the four validated config files: `risk.yaml` (human-edited only),
  `instruments.yaml`, `strategies.yaml`, `data.yaml`. All load through `qt.config.loader`
  with fail-fast pydantic validation.
- `src/qt/` — library code (Python 3.12, mypy strict).
- `scripts/measure_rtt.py` — TCP connect-time baseline to broker/exchange endpoints →
  `data/baseline_rtt.json`. Run from the production machine for the real baseline.
- `docs/windows_ops.md` — production-box operations (Task Scheduler, IB Gateway restart,
  clock sync, tzdata).
- `data/calendar/events.csv` — owner-maintained economic events calendar (UTC).
