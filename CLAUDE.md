# CLAUDE.md — session rules for this repo

Authoritative spec: **BUILD_PLAN.md** (repo root). Read it before doing anything. This file
only encodes the working agreement; the plan defines the work.

## Hard rules

1. **One slice per session.** Work only on the slice marked current in BUILD_PLAN.md's status
   ledger. Do not start the next slice, even if trivial.
2. **Never edit owner-only artifacts:** the STATUS LEDGER in BUILD_PLAN.md, `config/risk.yaml`,
   and `data/calendar/events.csv` are human-edited only. Gate sign-offs are owner decisions.
3. **Locked decisions (BUILD_PLAN.md §1) are not up for relitigation.** Python 3.12, venue
   order, instrument set, Panama adjustment, sizing rules — build to them.
4. **Conflict protocol (§7):** if reality (API behavior, data quirk, environment limit)
   contradicts the spec — stop, document the conflict in the session output, propose a
   resolution, and wait for the owner. Never silently work around it.
5. **Owner items (§6) are surfaced, never worked around.** No fake credentials, no stub
   Telegram tokens, no fabricated data to unblock yourself.
6. **Strategy acceptance is never automatic.** Memos present evidence; the owner records the
   deploy/park verdict.

## Engineering standards

- Python 3.12, uv-managed. `uv run pytest && uv run mypy && uv run ruff check .` must be green
  before every commit. mypy is strict; don't weaken it to make code fit.
- Small commits, descriptive messages, one logical change each.
- Money-path invariants are enforced structurally (types, schemas, state machines), not by
  convention. Example: stop widening must be impossible in the OMS API, not merely avoided.
- All configs load through `qt.config.loader` (fail-fast pydantic validation, unknown keys
  fatal). Never read YAML ad hoc on the money path.
- All internal timestamps UTC. Exchange timezones only at the session-calendar edge.
- Costs: single implementation in `src/qt/costs/model.py` (slice 4.2+), imported by both
  backtester and live executor. Never fork it.
- Every backtest run appends to the experiment log (slice 4.3+). No opt-out — deflated Sharpe
  needs the TRUE trial count.

## Layout

- `src/qt/` — library code (typed, `py.typed`). `scripts/` — operational entry points.
- `config/` — the four validated config files (risk, instruments, strategies, data).
- `tests/` — pytest; known-answer suite lives in `tests/known_answer/` (slice 4.2+).
- `data/` — raw/, curated/, calendar/; bulk market data stays out of git (see .gitignore).
- `docs/` — operational docs. `research/` — memos and validation artifacts (slice 4.3+).
