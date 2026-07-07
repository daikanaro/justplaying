"""Append-only SQLite experiment log (slice 4.3).

Every backtest run appends one row: timestamp, config hash, strategy, params,
data span, metrics. Triggers abort any UPDATE or DELETE on the experiments
table, so code holding a raw connection cannot casually rewrite rows. (DDL is
not guarded — DROP TABLE or dropping the triggers still works; the triggers
raise the bar from "one careless statement" to "deliberate tampering", which
is the honest limit of in-database enforcement.) The TRUE trial count that
deflated Sharpe requires is a simple COUNT over this table.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    strategy TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    params_json TEXT NOT NULL,
    symbols TEXT NOT NULL,
    span_start TEXT NOT NULL,
    span_end TEXT NOT NULL,
    n_bars INTEGER NOT NULL,
    n_trades INTEGER NOT NULL,
    metrics_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS experiments_no_update
    BEFORE UPDATE ON experiments
    BEGIN SELECT RAISE(ABORT, 'experiment log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS experiments_no_delete
    BEFORE DELETE ON experiments
    BEGIN SELECT RAISE(ABORT, 'experiment log is append-only'); END;
"""


def config_hash(payload: dict[str, Any]) -> str:
    """Stable hash of an arbitrary JSON-able config/params payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: int
    ts_utc: str
    strategy: str
    config_hash: str
    params: dict[str, Any]
    symbols: list[str]
    span_start: str
    span_end: str
    n_bars: int
    n_trades: int
    metrics: dict[str, float]


class ExperimentLog:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ExperimentLog:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def append(
        self,
        strategy: str,
        params: dict[str, Any],
        symbols: list[str],
        span_start: datetime,
        span_end: datetime,
        n_bars: int,
        n_trades: int,
        metrics: dict[str, float],
    ) -> int:
        """Append one run; returns the experiment id. There is no update/delete."""
        cursor = self._conn.execute(
            "INSERT INTO experiments (ts_utc, strategy, config_hash, params_json, symbols,"
            " span_start, span_end, n_bars, n_trades, metrics_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                strategy,
                config_hash({"strategy": strategy, "params": params}),
                json.dumps(params, sort_keys=True, default=str),
                ",".join(symbols),
                span_start.isoformat(),
                span_end.isoformat(),
                n_bars,
                n_trades,
                json.dumps(metrics, sort_keys=True),
            ),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def trial_count(self, strategy: str | None = None) -> int:
        """TRUE trial count for deflated Sharpe: every run ever logged."""
        if strategy is None:
            row = self._conn.execute("SELECT COUNT(*) FROM experiments").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM experiments WHERE strategy = ?", (strategy,)
            ).fetchone()
        return int(row[0])

    def records(self, strategy: str | None = None) -> list[ExperimentRecord]:
        query = (
            "SELECT id, ts_utc, strategy, config_hash, params_json, symbols,"
            " span_start, span_end, n_bars, n_trades, metrics_json FROM experiments"
        )
        args: tuple[str, ...] = ()
        if strategy is not None:
            query += " WHERE strategy = ?"
            args = (strategy,)
        query += " ORDER BY id"
        out = []
        for row in self._conn.execute(query, args):
            out.append(
                ExperimentRecord(
                    experiment_id=row[0],
                    ts_utc=row[1],
                    strategy=row[2],
                    config_hash=row[3],
                    params=json.loads(row[4]),
                    symbols=row[5].split(",") if row[5] else [],
                    span_start=row[6],
                    span_end=row[7],
                    n_bars=row[8],
                    n_trades=row[9],
                    metrics=json.loads(row[10]),
                )
            )
        return out

    @property
    def raw_connection(self) -> sqlite3.Connection:
        """Exposed for tests proving the append-only triggers hold even here."""
        return self._conn
