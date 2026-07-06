"""Unit tests for scripts/measure_rtt.py: stats math, endpoint parsing, and a
hermetic end-to-end run against a local listener (no external network)."""

import argparse
import json
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from scripts import measure_rtt

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_summarize_known_values() -> None:
    stats = measure_rtt.summarize([float(i) for i in range(1, 101)])
    assert stats["min_ms"] == 1.0
    assert stats["max_ms"] == 100.0
    assert stats["median_ms"] == 50.5
    assert stats["mean_ms"] == 50.5
    assert stats["p95_ms"] == 95.05
    assert stats["p99_ms"] == 99.01
    assert stats["jitter_iqr_ms"] == 49.5
    assert stats["jitter_stddev_ms"] == pytest.approx(29.011, abs=0.001)


def test_summarize_single_sample() -> None:
    stats = measure_rtt.summarize([42.0])
    assert stats["median_ms"] == 42.0
    assert stats["p95_ms"] == 42.0
    assert stats["jitter_stddev_ms"] == 0.0
    assert stats["jitter_iqr_ms"] == 0.0


def test_summarize_order_independent() -> None:
    assert measure_rtt.summarize([3.0, 1.0, 2.0]) == measure_rtt.summarize([1.0, 2.0, 3.0])


def test_percentile_interpolates() -> None:
    assert measure_rtt.percentile([10.0, 20.0], 50.0) == 15.0
    assert measure_rtt.percentile([10.0, 20.0], 0.0) == 10.0
    assert measure_rtt.percentile([10.0, 20.0], 100.0) == 20.0


# ---------------------------------------------------------------------------
# Endpoint parsing
# ---------------------------------------------------------------------------


def test_parse_endpoint_valid() -> None:
    assert measure_rtt.parse_endpoint("api.ibkr.com:443") == ("api.ibkr.com", 443)


def test_parse_endpoint_bracketed_ipv6() -> None:
    assert measure_rtt.parse_endpoint("[2001:db8::1]:443") == ("2001:db8::1", 443)


@pytest.mark.parametrize(
    "bad",
    [
        "no-port",
        ":443",
        "host:",
        "host:abc",
        "host:0",
        "host:99999",
        "https://api.ibkr.com:443",
        "[]:443",
    ],
)
def test_parse_endpoint_invalid(bad: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        measure_rtt.parse_endpoint(bad)


# ---------------------------------------------------------------------------
# Hermetic measurement against a local listener
# ---------------------------------------------------------------------------


@pytest.fixture
def local_listener() -> Iterator[tuple[str, int]]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    host, port = server.getsockname()
    stop = threading.Event()

    def accept_loop() -> None:
        server.settimeout(0.1)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except TimeoutError:
                continue
            except OSError:
                break

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    yield host, port
    stop.set()
    thread.join(timeout=2)
    server.close()


def test_measure_endpoint_success(local_listener: tuple[str, int]) -> None:
    host, port = local_listener
    result = measure_rtt.measure_endpoint(host, port, samples=5, timeout_s=2.0, delay_s=0.0)
    assert result["ok"] == 5
    assert result["failed"] == 0
    assert result["address"] == "127.0.0.1"
    assert result["stats"]["median_ms"] >= 0.0
    assert "failure_reasons" not in result


def test_measure_endpoint_resolution_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(host: str, port: int) -> tuple[socket.AddressFamily, object, str]:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(measure_rtt, "resolve_endpoint", boom)
    result = measure_rtt.measure_endpoint("nowhere.invalid", 443, 5, 1.0, 0.0)
    assert result["ok"] == 0
    assert result["failed"] == 5
    assert "address" not in result
    assert "resolution failed" in result["failure_reasons"][0]


def test_measure_endpoint_refused() -> None:
    # Bind-then-close guarantees the port exists but nothing is listening.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    _, dead_port = probe.getsockname()
    probe.close()
    result = measure_rtt.measure_endpoint(
        "127.0.0.1", dead_port, samples=3, timeout_s=0.5, delay_s=0.0
    )
    assert result["ok"] == 0
    assert result["failed"] == 3
    assert "stats" not in result
    assert result["failure_reasons"]


def test_main_writes_report(tmp_path: Path, local_listener: tuple[str, int]) -> None:
    host, port = local_listener
    out = tmp_path / "baseline_rtt.json"
    code = measure_rtt.main(
        [
            "--endpoint",
            f"{host}:{port}",
            "--samples",
            "3",
            "--delay",
            "0",
            "--output",
            str(out),
            "--note",
            "unit test",
        ]
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["note"] == "unit test"
    assert report["samples_per_endpoint"] == 3
    (result,) = report["results"]
    assert result["ok"] == 3
    for key in ("median_ms", "p95_ms", "jitter_stddev_ms", "jitter_iqr_ms"):
        assert key in result["stats"]


def test_main_all_failures_returns_nonzero(tmp_path: Path) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    _, dead_port = probe.getsockname()
    probe.close()
    out = tmp_path / "baseline_rtt.json"
    code = measure_rtt.main(
        [
            "--endpoint",
            f"127.0.0.1:{dead_port}",
            "--samples",
            "2",
            "--delay",
            "0",
            "--timeout",
            "0.5",
            "--output",
            str(out),
        ]
    )
    assert code == 1
    assert out.exists()  # the report is still written; failures are recorded facts


@pytest.mark.parametrize(
    "argv",
    [
        ["--samples", "0"],
        ["--timeout", "0"],
        ["--timeout", "-1"],
        ["--delay", "-0.5"],
    ],
)
def test_main_rejects_invalid_numeric_args(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        measure_rtt.main(argv)
    assert excinfo.value.code == 2  # argparse usage error, not a mid-run crash


# ---------------------------------------------------------------------------
# The shipped baseline artifact (slice 4.0 acceptance: file exists with stats)
# ---------------------------------------------------------------------------


def test_shipped_baseline_has_required_stats() -> None:
    baseline = Path(__file__).resolve().parent.parent / "data" / "baseline_rtt.json"
    report = json.loads(baseline.read_text(encoding="utf-8"))
    assert report["results"], "baseline has no endpoint results"
    assert any(r["ok"] > 0 for r in report["results"]), "no endpoint has a successful sample"
    for r in report["results"]:
        if r["ok"] > 0:
            for key in ("median_ms", "p95_ms", "jitter_stddev_ms", "jitter_iqr_ms"):
                assert key in r["stats"], f"{r['endpoint']} missing {key}"
