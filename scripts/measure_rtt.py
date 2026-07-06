"""Measure TCP connect-time baselines to broker/exchange endpoints (slice 4.0).

Takes N raw TCP connect samples per endpoint and writes summary statistics
(median, p95, jitter, ...) plus environment metadata to a JSON file.

Stdlib-only on purpose: the numbers only mean something when measured from the
production machine (the owner's box in Kazakhstan), which may not have the
project venv. A run from a cloud container is a smoke test, not a baseline —
label it via --note.

Usage:
    python scripts/measure_rtt.py                       # defaults, 100 samples
    python scripts/measure_rtt.py --samples 20 --note "container smoke test"
    python scripts/measure_rtt.py --endpoint host:443 --endpoint other:4001
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINTS = [
    "api.ibkr.com:443",
    "api.binance.com:443",
    "fapi.binance.com:443",
]
DEFAULT_SAMPLES = 100
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_DELAY_S = 0.05
DEFAULT_OUTPUT = "data/baseline_rtt.json"


def parse_endpoint(value: str) -> tuple[str, int]:
    host, sep, port_str = value.rpartition(":")
    if not sep or not host:
        msg = f"endpoint {value!r} is not host:port"
        raise argparse.ArgumentTypeError(msg)
    try:
        port = int(port_str)
    except ValueError as exc:
        msg = f"endpoint {value!r} has non-integer port"
        raise argparse.ArgumentTypeError(msg) from exc
    if not 0 < port < 65536:
        msg = f"endpoint {value!r} port out of range"
        raise argparse.ArgumentTypeError(msg)
    return host, port


def sample_connect_ms(host: str, port: int, timeout_s: float) -> float:
    """One TCP connect; returns elapsed milliseconds. Raises OSError on failure."""
    start = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout_s):
        pass
    return (time.perf_counter() - start) * 1000.0


def percentile(sorted_ms: list[float], pct: float) -> float:
    """Linear-interpolated percentile over an already-sorted, non-empty list."""
    if len(sorted_ms) == 1:
        return sorted_ms[0]
    rank = (pct / 100.0) * (len(sorted_ms) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_ms) - 1)
    frac = rank - lo
    return sorted_ms[lo] + (sorted_ms[hi] - sorted_ms[lo]) * frac


def summarize(samples_ms: list[float]) -> dict[str, float]:
    """Stats over successful samples: median/p95 per the acceptance criteria,
    jitter as both stddev and IQR (IQR is robust to a single stray SYN retry)."""
    ordered = sorted(samples_ms)
    return {
        "min_ms": round(ordered[0], 3),
        "median_ms": round(statistics.median(ordered), 3),
        "mean_ms": round(statistics.fmean(ordered), 3),
        "p95_ms": round(percentile(ordered, 95.0), 3),
        "p99_ms": round(percentile(ordered, 99.0), 3),
        "max_ms": round(ordered[-1], 3),
        "jitter_stddev_ms": round(statistics.stdev(ordered), 3) if len(ordered) > 1 else 0.0,
        "jitter_iqr_ms": round(percentile(ordered, 75.0) - percentile(ordered, 25.0), 3),
    }


def measure_endpoint(
    host: str, port: int, samples: int, timeout_s: float, delay_s: float
) -> dict[str, Any]:
    ok_ms: list[float] = []
    failures: list[str] = []
    for i in range(samples):
        if i:
            time.sleep(delay_s)
        try:
            ok_ms.append(sample_connect_ms(host, port, timeout_s))
        except OSError as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
    result: dict[str, Any] = {
        "endpoint": f"{host}:{port}",
        "samples": samples,
        "ok": len(ok_ms),
        "failed": len(failures),
    }
    if ok_ms:
        result["stats"] = summarize(ok_ms)
    if failures:
        # Deduplicated: 100 identical timeouts are one fact, not one hundred.
        result["failure_reasons"] = sorted(set(failures))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        action="append",
        type=parse_endpoint,
        dest="endpoints",
        help="host:port to measure (repeatable; default: IBKR + Binance endpoints)",
    )
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument(
        "--note",
        default="",
        help="free-text label, e.g. 'production baseline' or 'container smoke test'",
    )
    args = parser.parse_args(argv)
    if args.samples < 1:
        parser.error("--samples must be >= 1")

    endpoints: list[tuple[str, int]] = args.endpoints or [
        parse_endpoint(e) for e in DEFAULT_ENDPOINTS
    ]

    results = []
    for host, port in endpoints:
        print(f"measuring {host}:{port} ({args.samples} samples)...", flush=True)
        results.append(measure_endpoint(host, port, args.samples, args.timeout, args.delay))

    report = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "note": args.note,
        "samples_per_endpoint": args.samples,
        "timeout_s": args.timeout,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")

    any_ok = any(r["ok"] > 0 for r in results)
    if not any_ok:
        print("WARNING: no endpoint produced a single successful sample", file=sys.stderr)
    return 0 if any_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
