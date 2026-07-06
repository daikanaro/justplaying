"""Parameter heatmaps + plateau assessment (§3: accept parameter changes only
if a broad NEIGHBORHOOD improves — never a single cell)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HeatmapData:
    row_label: str
    col_label: str
    row_values: list[float]
    col_values: list[float]
    cells: list[list[float]]  # cells[row][col]

    def __post_init__(self) -> None:
        if len(self.cells) != len(self.row_values) or any(
            len(row) != len(self.col_values) for row in self.cells
        ):
            msg = "cells shape must be (len(row_values), len(col_values))"
            raise ValueError(msg)


def neighborhood_means(data: HeatmapData) -> list[list[float]]:
    """Each cell replaced by the SUM of its 3x3 neighborhood divided by 9
    (zero-padded at the grid edge). The plateau rule compares THESE, not raw
    cells: a lone spike averages away, a genuine plateau survives. Dividing by
    9 everywhere deliberately penalizes edge/corner cells — a neighborhood
    half outside the explored grid is not "broad" (§3)."""
    rows, cols = len(data.row_values), len(data.col_values)
    out: list[list[float]] = []
    for r in range(rows):
        row_means: list[float] = []
        for c in range(cols):
            total = sum(
                data.cells[rr][cc]
                for rr in range(max(0, r - 1), min(rows, r + 2))
                for cc in range(max(0, c - 1), min(cols, c + 2))
            )
            row_means.append(total / 9.0)
        out.append(row_means)
    return out


@dataclass(frozen=True)
class PlateauAssessment:
    best_cell: tuple[int, int]  # argmax of raw cells
    best_neighborhood: tuple[int, int]  # argmax of neighborhood means
    best_is_on_plateau: bool  # raw best sits inside the best neighborhood's 3x3


def assess_plateau(data: HeatmapData) -> PlateauAssessment:
    def argmax(cells: list[list[float]]) -> tuple[int, int]:
        best = (0, 0)
        for r, row in enumerate(cells):
            for c, value in enumerate(row):
                if value > cells[best[0]][best[1]]:
                    best = (r, c)
        return best

    raw_best = argmax(data.cells)
    smooth_best = argmax(neighborhood_means(data))
    on_plateau = abs(raw_best[0] - smooth_best[0]) <= 1 and abs(raw_best[1] - smooth_best[1]) <= 1
    return PlateauAssessment(
        best_cell=raw_best, best_neighborhood=smooth_best, best_is_on_plateau=on_plateau
    )


def render_heatmap(data: HeatmapData, title: str, out_png: Path) -> None:
    import matplotlib  # noqa: PLC0415 - backend must be set before pyplot loads

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, ax = plt.subplots(figsize=(1.2 * len(data.col_values) + 3, len(data.row_values) + 2))
    image = ax.imshow(data.cells, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(data.col_values)), [str(v) for v in data.col_values])
    ax.set_yticks(range(len(data.row_values)), [str(v) for v in data.row_values])
    ax.set_xlabel(data.col_label)
    ax.set_ylabel(data.row_label)
    ax.set_title(title)
    for r in range(len(data.row_values)):
        for c in range(len(data.col_values)):
            ax.text(c, r, f"{data.cells[r][c]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, shrink=0.8)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
