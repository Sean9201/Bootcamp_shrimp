"""클릭 매칭 지표."""

from shrimp_ai.metrics import match_clicks


def test_boundary_and_duplicate():
    assert match_clicks([1.0], [1.005]).tp == 1
    m = match_clicks([1.0], [0.999, 1.001])
    assert (m.tp, m.fp, m.fn) == (1, 1, 0)


def test_empty():
    assert match_clicks([], []).f1 == 1.0
    assert match_clicks([1.0], []).f1 == 0.0
