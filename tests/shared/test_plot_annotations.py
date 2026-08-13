import matplotlib.pyplot as plt
import pandas as pd

import dmw_experiments.shared.analysis as ut


def test_top_statistic_clearance_survives_final_layout_change() -> None:
    """Recalculate a small frame gap after subplot geometry changes."""
    figure, axis = plt.subplots(figsize=(3.0, 3.0))
    data = pd.DataFrame({"condition": ["first", "second"], "value": [1, 1]})
    axis.bar((0, 1), (1.0, 1.0))
    axis.set_ylim(0.0, 1.0)
    annotation = ut.annotate_xaxis_group_statistic(
        axis,
        data=data,
        x="condition",
        y="value",
        x_order=("first", "second"),
        statistic="count",
        placement="top",
        base_ylim=(0.0, 1.0),
    )
    figure.subplots_adjust(top=0.55)

    ut.refresh_above_xaxis_annotations(axis)
    figure.canvas.draw()

    renderer = figure.canvas.get_renderer()
    gap_pixels = (
        axis.get_window_extent(renderer).y1
        - annotation.texts[0].get_window_extent(renderer).y1
    )
    gap_points = gap_pixels * 72.0 / figure.dpi
    try:
        assert 1.9 <= gap_points <= 2.1
        assert axis.get_ylim()[1] > 1.0
    finally:
        plt.close(figure)
