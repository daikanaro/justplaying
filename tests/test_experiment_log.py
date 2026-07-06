"""Experiment log tests: append/read round-trip, TRUE trial count, and the
structural append-only guarantee (G4.3 acceptance)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.validation.experiment_log import ExperimentLog, config_hash

SPAN = (datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 6, 28, tzinfo=UTC))


def make_log(tmp_path: Path) -> ExperimentLog:
    return ExperimentLog(tmp_path / "experiments.sqlite")


def append_one(log: ExperimentLog, strategy: str = "s1", sharpe: float = 1.0) -> int:
    return log.append(
        strategy=strategy,
        params={"n": 55, "k": 3.0},
        symbols=["MES"],
        span_start=SPAN[0],
        span_end=SPAN[1],
        n_bars=120,
        n_trades=7,
        metrics={"sharpe": sharpe},
    )


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    with make_log(tmp_path) as log:
        experiment_id = append_one(log)
        (record,) = log.records()
        assert record.experiment_id == experiment_id
        assert record.strategy == "s1"
        assert record.params == {"n": 55, "k": 3.0}
        assert record.symbols == ["MES"]
        assert record.n_trades == 7
        assert record.metrics == {"sharpe": 1.0}
        assert record.config_hash == config_hash({"strategy": "s1", "params": {"n": 55, "k": 3.0}})


def test_trial_count_is_total_not_latest(tmp_path: Path) -> None:
    with make_log(tmp_path) as log:
        for i in range(5):
            append_one(log, strategy="s1", sharpe=float(i))
        append_one(log, strategy="s2")
        assert log.trial_count() == 6
        assert log.trial_count("s1") == 5
        assert log.trial_count("s2") == 1
        assert log.trial_count("s3") == 0


def test_log_persists_across_reopen(tmp_path: Path) -> None:
    with make_log(tmp_path) as log:
        append_one(log)
    with make_log(tmp_path) as reopened:
        assert reopened.trial_count() == 1
        append_one(reopened)
        assert reopened.trial_count() == 2


def test_update_is_structurally_impossible(tmp_path: Path) -> None:
    with make_log(tmp_path) as log:
        append_one(log)
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            log.raw_connection.execute("UPDATE experiments SET strategy = 'rewritten'")


def test_delete_is_structurally_impossible(tmp_path: Path) -> None:
    with make_log(tmp_path) as log:
        append_one(log)
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            log.raw_connection.execute("DELETE FROM experiments")
        assert log.trial_count() == 1


def test_config_hash_stable_and_order_independent() -> None:
    a = config_hash({"strategy": "s1", "params": {"n": 55, "k": 3.0}})
    b = config_hash({"params": {"k": 3.0, "n": 55}, "strategy": "s1"})
    c = config_hash({"strategy": "s1", "params": {"n": 20, "k": 3.0}})
    assert a == b
    assert a != c
