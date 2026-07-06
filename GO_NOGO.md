# GO_NOGO.md — live-arming checklist (BUILD_PLAN §4.7)

Every box is an OWNER decision. Nothing below is checked by code, and nothing
in this repo will arm live trading while any box is empty. Going live starts
at **$1–2K, never $20K** (STATUS LEDGER, G5).

## Gates (mirror of the STATUS LEDGER — sign there too)

- [ ] G0 — Scaffold green (slice 4.0)
- [ ] G1 — Data curated & QC clean (4.1): 2y hourly+daily MES & M2K in
      curated/, QC reports zero criticals, funding + VIX artifacts produced
- [ ] G2 — Backtester passes the known-answer suite (KA-1/2/3, and KA-4 green
      after 4.4 — the test currently SKIPS until curated data exists)
- [ ] G3 — Strategy memos complete with tail metrics and both S2 fill modes;
      deploy/park verdicts recorded in research/*.md
- [ ] G4 — Chaos drills a–d pass against the real Gateway; 10-business-day
      paper soak with zero unexplained-state halts
- [ ] G5 — Paper campaign: ≥4 CONSECUTIVE weekly reports inside all bands
      (research/campaign_state.json says eligible_for_go_nogo: true)

## Campaign evidence (attach or link)

- [ ] Weekly reports for the qualifying weeks (research/campaign/weekly_*.txt)
- [ ] Cost-model recalibration reviewed; instruments.yaml updated by hand if
      warranted (diff reviewed, tests green)
- [ ] Nightly reconciliation clean for the qualifying weeks

## Operational readiness

- [ ] Kill-switch drill rehearsed ON ARM DAY: watchdog kill executes
      cancel-all + flatten + HALT; engine refuses restart; owner clears flag
- [ ] Dead-man drill: frozen engine alerts in < 60s
- [ ] Telegram alerts verified end-to-end (QT_TELEGRAM_* set outside repo)
- [ ] IB Gateway auto-restart + weekly re-auth behavior observed and documented
- [ ] Clock sync verified on the production box (w32tm, docs/windows_ops.md)

## External (owner-only, §6)

- [ ] Kazakhstan tax/reporting consultation done BEFORE any live arming
- [ ] Live risk.yaml reviewed line by line (mode flip is an owner edit +
      restart, and requires G5 signed)
- [ ] data/calendar/events.csv populated for the coming month
- [ ] Starting live capital confirmed: $1–2K

## Decision

- [ ] **GO** — arm live at $1–2K on: ____________ (date, signature)
- [ ] **NO-GO / EXTEND** — reason and what evidence reopens it:

Signature/date:
