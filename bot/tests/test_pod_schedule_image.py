import pytest

from bot.services.pod_schedule_image import CELL_H, CELL_W, COLS, MIN_ASPECT, PAD, WEEKDAY_H, _cell_width


@pytest.mark.parametrize("weeks", range(1, 9))
def test_the_grid_never_renders_taller_than_discords_image_box_allows(weeks):
    width = PAD * 2 + COLS * _cell_width(weeks)
    height = PAD * 2 + WEEKDAY_H + weeks * CELL_H

    assert width / height >= MIN_ASPECT


def test_a_span_short_enough_to_fit_keeps_the_standard_cell():
    assert _cell_width(4) == CELL_W
