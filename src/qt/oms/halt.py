"""HALT flag semantics (§2 watchdog + §4.5 reconciliation).

Writing the flag is easy; clearing it is DELIBERATELY not implemented here —
re-arm is a manual owner action (delete the file after investigating), and no
code path in this repo may do it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


class HaltError(Exception):
    """The HALT flag exists: the engine must refuse to run."""


def write_halt(path: Path, reason: str) -> None:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = f"[{stamp}] {reason}\n"
    with path.open("a", encoding="utf-8") as fh:  # append: keep every halt reason
        fh.write(entry)


def require_not_halted(path: Path) -> None:
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        msg = (
            f"HALT flag present at {path} — engine refuses to start. Investigate, then "
            f"the OWNER deletes the file to re-arm (manual, §2). Reasons:\n{content}"
        )
        raise HaltError(msg)
