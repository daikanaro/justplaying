"""Heatmap + plateau-rule tests."""

from pathlib import Path

import pytest

from qt.validation.heatmap import HeatmapData, assess_plateau, neighborhood_means, render_heatmap


def grid(cells: list[list[float]]) -> HeatmapData:
    return HeatmapData(
        row_label="N",
        col_label="k",
        row_values=[float(i) for i in range(len(cells))],
        col_values=[float(j) for j in range(len(cells[0]))],
        cells=cells,
    )


def test_neighborhood_means_hand_case() -> None:
    data = grid([[1.0, 2.0], [3.0, 4.0]])
    # Every neighborhood covers the whole 2x2 grid, zero-padded to /9: 10/9.
    expected = 10.0 / 9.0
    assert neighborhood_means(data) == [[expected] * 2, [expected] * 2]


def test_neighborhood_means_center_of_3x3() -> None:
    data = grid([[1.0, 1.0, 1.0], [1.0, 9.0, 1.0], [1.0, 1.0, 1.0]])
    means = neighborhood_means(data)
    assert means[1][1] == pytest.approx((8 * 1 + 9) / 9)
    assert means[0][0] == pytest.approx((1 + 1 + 1 + 9) / 9)  # corner: zero-padded


def test_lone_spike_is_off_plateau() -> None:
    # A single hot cell in a cold corner vs a warm 3x3 plateau elsewhere.
    cells = [
        [9.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 3.0, 3.0, 3.0],
        [0.0, 0.0, 3.0, 3.5, 3.0],
        [0.0, 0.0, 3.0, 3.0, 3.0],
    ]
    assessment = assess_plateau(grid(cells))
    assert assessment.best_cell == (0, 0)  # the spike wins raw
    assert assessment.best_neighborhood == (3, 3)  # the plateau's core wins smoothed
    assert not assessment.best_is_on_plateau  # -> §3: do NOT accept the spike


def test_plateau_best_is_accepted() -> None:
    cells = [
        [1.0, 1.0, 1.0],
        [1.0, 5.0, 4.0],
        [1.0, 4.0, 4.0],
    ]
    assessment = assess_plateau(grid(cells))
    assert assessment.best_cell == (1, 1)
    assert assessment.best_is_on_plateau


def test_shape_validation() -> None:
    with pytest.raises(ValueError, match="shape"):
        HeatmapData("a", "b", [1.0, 2.0], [1.0], [[1.0]])


def test_render_writes_png(tmp_path: Path) -> None:
    out = tmp_path / "heatmap.png"
    render_heatmap(grid([[1.0, 2.0], [3.0, 4.0]]), "sharpe", out)
    assert out.is_file()
    assert out.stat().st_size > 0
