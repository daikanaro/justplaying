# BUILD_PLAN.md — QuantTrader Phase 4 specification

Authoritative build spec. Produced from a research/design phase (Phases 0–3) conducted with Claude (chat).
Claude Code executes slices 4.0 → 4.7 in order, one at a time. CLAUDE.md rules apply to every session.

## STATUS LEDGER (owner-edited only)
- [ ] G0 — Scaffold green (slice 4.0)
- [ ] G1 — Data curated & QC clean (4.1)
- [ ] G2 — Backtester passes known-answer suite (4.2–4.3)
- [ ] G3 — Strategy validation memos written & accepted (4.4)
- [ ] G4 — Paper soak + chaos drills clean (4.5–4.6)
- [ ] G5 — Paper campaign + go/no-go signed (4.7)  → only then live, starting at $1–2K, never $20K.

Current slice: **4.2**  <!-- advanced at owner's direction 2026-07-06 ("skip the actions needed from me and continue"); G0/G1 unsigned; 4.1 owner-gated items open: IBKR download, funding/VIX egress -->

---

## 1. LOCKED DECISIONS (do not relitigate in Claude Code sessions)

**Venue order.** IBKR paper first (this plan). Binance testnet second (separate plan later; only the
funding-history downloader is built now).

**Language.** Python 3.12 on the entire money path. Rationale (settled in design phase): strategy cadence is
hourly/daily bars; network RTT from Kazakhstan to broker/exchange is ~150–300ms with ±30ms jitter; language-level
savings from C++ would be ~1–3ms — unmeasurable — while beginner-C++ correctness risk on execution code is real.
Compiled performance comes from Rust/C++-cored libraries (polars, numpy, numba). Optional later: PyO3 Rust module
for a proven hot loop; C++ only as off-money-path education.

**Instruments** (verify tick values against IBKR contract details at first connect):
| Symbol | Contract | $/point | Tick | Tick $ | Notes |
|---|---|---|---|---|---|
| MES | Micro E-mini S&P 500 | 5 | 0.25 | 1.25 | primary trend; MR only when ATR gate open |
| M2K | Micro E-mini Russell 2000 | 5 | 0.10 | 0.50 | smallest notional → sizing resolution; primary MR |
| MNQ | Micro E-mini Nasdaq-100 | 2 | 0.25 | 0.50 | NOT whitelisted in v1; earned later |

**Cost model constants** (config-driven; recalibrate from real paper fills in 4.7):
- Commission all-in ≈ $0.80/side/contract (IBKR fixed $0.25 + exchange/NFA ≈ $0.55). Config key per symbol.
- Slippage baseline: 1 tick/side for market orders in regular hours; 2 ticks/side overnight (ETH) or fast tape.
- Stress runs: ×2 and ×3 slippage are mandatory in validation.
- Round-trip hurdle to keep in mind: ≈ $4.10 on MES (≈3.3 ticks).

**Data plan.**
- IBKR API supplies ~2 years of history for expired futures (hard limit: no data older than 2y past a
  contract's expiry). Pacing: ≤60 historical requests per 10 min; ≤6 requests per 2s for the same contract.
- Continuous series are built by us: roll table + **Panama (difference) back-adjustment** (preserves point
  differences → exact $ P&L; do NOT use ratio adjustment; do NOT compute long-horizon % returns on the
  adjusted series without the roll table).
- Roll rule: roll when next contract's 5-day volume exceeds front's; fallback 5 business days before expiry.
- Deep history (pre-2024, needed for era-split validation) comes from a paid vendor (owner decision pending:
  Databento or FirstRate). Until purchased, era splits older than the IBKR window run on free daily continuous
  series (Stooq) for daily-bar sanity ONLY and every such result is labeled PROVISIONAL.
- Auxiliary: VIX daily closes (CBOE public CSV); economic events calendar `data/calendar/events.csv`
  (owner-maintained: FOMC statement, CPI, NFP — datetime UTC, type).

**Sizing rules (both strategies).**
- contracts N = round( f · equity / (k_stop · ATR · $per_point) ), f from risk.yaml.
- If fractional N < 0.5 → trade 0. Never round 0 → 1.
- Volatility-target overlay: position daily $vol ≤ (0.20/√252)·equity; cap N accordingly.

**Regulatory note.** FINRA's pattern-day-trader rule ($25K minimum) was eliminated effective 2026-06-04;
futures were never subject to it. Equities are legally open but out of scope for v1.

---

## 2. RISK CONFIGURATION — initial `config/risk.yaml` (human-edited only)

```yaml
mode: paper                     # "live" requires owner edit + restart + G5 signed
per_trade_risk_default: 0.005   # fraction of equity risked to stop
per_trade_risk_max: 0.01
daily_loss_halt: -0.03          # new entries halted for the day
kill_drawdown_hwm: -0.35        # from high-water mark: cancel all, flatten, disable; manual re-arm
gross_notional_max_x_equity: 3.0
max_contracts: {MES: 2, M2K: 6, MNQ: 0}
instrument_whitelist: [MES, M2K]
price_collar_pct: 0.01          # reject orders priced >1% from last mark
mr_atr_gate_equity_pct: 0.025   # MR entry allowed only if k_stop*ATR*$pt <= 2.5% of equity
vix_max_for_mr: 35
event_blackout_min: 30          # no entries within ±30min of calendar events
rearm: manual
```

Watchdog semantics: `daily_loss_halt` blocks new entries (exits still allowed). `kill_drawdown_hwm` triggers
cancel-all + flatten (reduce-only) + write `HALT` flag file + Telegram alert; engine refuses to start while
flag exists; owner deletes flag to re-arm.

---

## 3. STRATEGY SPECIFICATIONS

Shared: strategies implement `Strategy.on_bar(ctx) -> dict[symbol, target_contracts]`. They never emit orders.
Indicators per specs below (hand-rolled, unit-tested against hand-computed fixtures).
Indicator definitions: EMA standard recursive; ATR = Wilder smoothing of true range; RSI = Wilder;
Donchian(N) = rolling max/min of prior N bars (exclusive of current bar).

### S1 — TREND_BREAKOUT
Two configs. TF-H is the deployment candidate; TF-D exists for research comparison (M2K only — MES daily
3×ATR risk ≈ 4–5% equity/trade, incompatible with risk.yaml).

- Signal (long): bar close > Donchian_high(N). Short: close < Donchian_low(N). Reversal allowed.
- Initial & trailing stop: k × ATR(m) from best close since entry; ratchets on favorable closes only;
  never widens (enforced structurally in OMS, not just strategy code).
- Exit: trail hit (native stop order resting at broker) or opposite signal.
- Entry timing: signal evaluated on bar close; order = next bar open (backtest fills likewise).
- TF-H: hourly bars, MES + M2K. Defaults N=55 bars, k=3, m=20. Entries only 13:30–21:00 UTC
  (approx. 08:30–16:00 ET liquid hours); exits/stops active 24h. 
- TF-D: daily bars, M2K only. Defaults N=55, k=3, m=20.
- Event filter: no new entries inside event blackout window.
- Long/short both sides; run the "equity-index short-side on/off" comparison as a tracked experiment
  (mechanism: index drift penalizes shorts — see validation memo template).
- Parameter grid for plateau maps: N ∈ {20, 40, 55, 80, 120}, k ∈ {2.5, 3, 4}. Accept parameter changes only
  if a broad neighborhood improves (plateau rule), never a single cell.

### S2 — MR_RSI2
- Daily bars. M2K primary; MES permitted only when ATR gate passes.
- Entry (long only in v1): RSI(2) < 10 AND close > SMA(200) AND ATR gate passes AND VIX < vix_max
  AND no calendar event next session. NO scale-ins (deliberately removed — tail multiplier).
- Fill modes: backtest MUST report both (a) same-close fill (flagged: lookahead-adjacent) and
  (b) next-open fill. The WORSE of the two governs all decisions. Live implementation computes the signal
  ~5 min before the close and submits MOC-approximate or at-close market order; slippage vs true close is logged.
- Exit: close > previous day's high, OR RSI(2) > 65, OR 5-bar time stop — whichever first (next-open execution).
- Hard stop: 2.5 × ATR(14) below entry, resting at broker, never widened. This is a model-falsification line.
- Every proposed change must not degrade left-tail metrics (ES95, worst day, max losing cluster) even if
  Sharpe improves. Era-split validation is mandatory: ≤2012 / 2013–2019 / 2020–present.

### S3 — CARRY_FUNDING (deferred to venue 2)
Only deliverable now: `src/qt/data/binance_funding.py` — public REST, BTCUSDT funding since 2020; outputs
(a) fraction of intervals pinned at exactly 0.01%, (b) rolling 30-day annualized funding, (c) longest negative
streak; plot all three. No keys, read-only, production public endpoint. If geo-blocked, record that fact.

### Validation battery (applies to S1 and S2 before any strategy is accepted)
Walk-forward analysis; parameter heatmaps with plateau assessment; deflated Sharpe using the TRUE trial count
from the experiment log; Monte Carlo trade-order reshuffle (10k paths) for drawdown distribution; slippage
stress ×1/×2/×3; era splits; both fill modes for S2. Output: a decision memo per strategy
(template in `research/memo_template.md`: mechanism claim, results, tail metrics, verdict deploy/park).
Strategy acceptance is an OWNER decision recorded in the memo — never automatic.

---

## 4. BACKTESTER REQUIREMENTS (slice 4.2)

Event-driven, single-threaded loop: MarketEvent → SignalEvent → OrderEvent → FillEvent.
- Fills: default next-bar-open. Market fill = open ± slippage ticks (session-aware). Stop fill = stop price
  ± slippage, and if bar gaps through the stop, fill at bar open beyond it (gap-through modeled, mandatory).
- Limit orders: filled only if price trades through the limit by ≥1 tick (conservative queue heuristic);
  partial fills supported.
- Latency mode: signal at T, fill at T+Δ (config), for sensitivity checks.
- Cost model in `src/qt/costs/model.py` — imported by BOTH backtester and live executor. Single implementation.
- Portfolio accounting to the cent; margin tracking vs config maintenance values; invariant checked every
  event: cash + Σ(position marks) == equity.
- Funding-accrual hook present but inert (venue 2).

### Known-answer suite (`tests/known_answer/`) — G2 gate
- KA-1 GBM no-edge: simulate GBM (no autocorrelation); run S1 and S2 logic; net-of-cost expectancy must be
  ≤ 0 within confidence bounds. Any measured edge on GBM = engine bug. (S1 must also show the first-passage
  signature: hit rate ≈ a/(a+b), payoff ≈ b/a.)
- KA-2 Deterministic fixture: 10 hand-built bars with hand-computed fills, costs, and P&L; engine must match
  to the cent.
- KA-3 MR governor grid: simulate P = F + u (F random walk with occasional jump-drift crash regimes;
  u AR(1)); run S2 across the 2×2×2 grid {trend filter, hard stop, time stop} on/off; assert governors are
  approximately mean-neutral but materially improve ES95/worst-day. With u ≡ 0, any edge = bug.
- KA-4 (runs after 4.4): 2022 MES daily walkthrough — the 55/3×ATR system must produce 3 short trades
  (late-Feb, late-Apr, late-Sep entries within ±3 bars), P&L signs (−, +, −), one winner ≈ 2× average loser.
  Deviation = investigate as engine-or-data bug before proceeding.

---

## 5. SLICES

### 4.0 Scaffold & baseline measurements
Tasks: repo init; uv project; ruff/mypy/pytest config; pydantic schemas for all four config files (load +
validate + fail-fast tests); `scripts/measure_rtt.py` (TCP connect-time samples ×100 to IBKR and Binance
endpoints → `data/baseline_rtt.json`); `docs/windows_ops.md` (Task Scheduler jobs, IB Gateway auto-restart
notes, clock sync via w32tm, tzdata requirement).
Acceptance: pytest/mypy/ruff green on skeleton; configs round-trip; RTT baseline file exists with stats
(median, p95, jitter).

### 4.1 Data layer
Tasks: IBKR historical downloader (ib_async; pacing-aware queue per §1 limits; includeExpired; resumable;
raw Parquet per contract); roll-table builder; Panama stitcher → curated continuous daily+hourly for MES, M2K;
QC module (session-calendar gap scan, duplicates, >12σ outliers, zero-volume runs → report; criticals block
promotion to curated/); VIX loader; events-calendar loader/validator; Binance funding downloader (S3 spec).
Acceptance: 2y hourly+daily continuous MES & M2K in curated/ with QC report zero criticals; stitcher unit
tests prove (a) point-differences preserved across rolls, (b) adjusted series has no unexplained roll-day jump;
funding script produces the three statistics + plot. OWNER ACTIONS surfaced: IBKR account/paper login ready,
market-data subscription active, vendor-data purchase decision.

### 4.2 Backtest engine
Per §4. Acceptance: KA-1, KA-2, KA-3 pass; property tests (hypothesis): accounting invariant under random
event sequences, fills always within bar range, no negative-time events.

### 4.3 Validation harness
Tasks: experiment log (SQLite; auto-append config hash, params, data span, metrics, timestamp on EVERY
backtest run — no opt-out); walk-forward runner; heatmap generator; deflated-Sharpe implementation
(unit-tested against a hand-computed case); MC reshuffle; slippage-stress runner; era-split reporter;
memo template.
Acceptance: end-to-end run on a dummy strategy produces all artifacts; experiment-log append-only test;
deflated Sharpe matches hand computation.

### 4.4 Strategies S1 + S2
Tasks: implement per §3 against the engine; run full validation battery; produce both decision memos;
KA-4 added to known-answer suite and passing.
Acceptance: KA-4 green; memos complete with tail metrics and both S2 fill modes; owner records deploy/park
verdicts in memos. (Plateau maps may motivate parameter changes — apply plateau rule, log everything.)

### 4.5 OMS + IBKR paper connection
Tasks: ib_async adapter; order state machine (states: PENDING_NEW, ACKED, PARTIAL, FILLED, CANCELLED,
REJECTED, UNKNOWN; hypothesis property tests over legal/illegal transition sequences); client-order-id
idempotency; target-position reconciler loop (diff targets vs broker, emit delta orders); startup/reconnect
full reconciliation vs journal (mismatch → HALT flag + alert); native stop management (create/ratchet;
widening structurally impossible); IB Gateway daily-restart handling.
Acceptance — chaos drills, all scripted and repeatable:
(a) kill Gateway mid-order → on restart, state reconciles with zero unexplained diffs;
(b) kill engine mid-session → restart reconciles journal == broker;
(c) duplicate submit attempt suppressed by idempotency;
(d) forced reject → no retry storm (bounded backoff), alert emitted.
Plus a 10-business-day paper soak with zero unexplained-state halts (each occurrence investigated & fixed).

### 4.6 Risk engine + monitoring
Tasks: pre-trade check library as the single choke point (size, collar, whitelist, per-symbol caps, gross
notional, per-trade risk); independent watchdog process (equity/HWM/daily P&L from journal+broker; enforces
daily halt and kill per §2 semantics); heartbeat files + dead-man alert; Telegram alerter (fills, rejects,
halts, disconnects, daily summary); nightly reconciliation vs IBKR Flex report; equity/drawdown tracker.
Acceptance: injected −3% day halts new entries; injected −35% DD executes full kill within one watchdog
cycle and engine refuses restart until flag cleared; frozen-process drill fires dead-man alert < 60s;
nightly report matches broker statement.

### 4.7 Paper campaign & go/no-go
Tasks: run S1 (and S2 if memo verdict = deploy) on paper ≥ 4–8 weeks; weekly tracking-error report
(scheduled): mean fill slippage vs modeled within ±1 tick; trade count vs backtest expectation ±20%;
realized portfolio vol within target band; cost per round trip within ±25%; recalibrate cost model from
real fills. Produce `GO_NOGO.md` checklist: all gates signed, tax consult done (owner), live risk.yaml
reviewed, kill-switch drill rehearsed on arm day, starting live capital $1–2K.
Acceptance: ≥4 consecutive weekly reports inside bands (out-of-band → diagnose, fix, restart clock);
GO_NOGO.md complete. G5 is signed by the owner or the campaign extends. 

---

## 6. OPEN ITEMS REQUIRING THE OWNER (Claude Code: surface these, never work around them)
- IBKR account approval status; paper login; market-data subscription (US Securities Snapshot & Futures
  Value Bundle) active — required for API data.
- Vendor deep-history purchase decision (Databento vs FirstRate) before 4.4 conclusions are finalized.
- Kazakhstan tax/reporting consultation — before any live arming.
- Telegram bot token for alerts (owner-provisioned, stored outside repo).
- Populate/verify `data/calendar/events.csv` each month.
- Gate sign-offs in the STATUS LEDGER.

## 7. HOW TO RUN THIS PLAN IN CLAUDE CODE
- Start each session: "Read CLAUDE.md and BUILD_PLAN.md. We are on slice 4.X. Propose your plan before coding."
- Use plan mode for anything architectural; one slice per session-thread; small commits.
- If a spec detail here conflicts with something discovered in reality (API behavior, data quirk):
  stop, document the conflict, propose a resolution, wait for the owner.
