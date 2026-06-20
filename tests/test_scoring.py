from strategy.scoring import score_relative_strength, score_support


def test_score_relative_strength_thresholds():
    assert score_relative_strength(1.80)[0] == 0
    assert score_relative_strength(1.72)[0] == 1
    assert score_relative_strength(1.66)[0] == 2
    assert score_relative_strength(1.60)[0] == 3


def test_score_support():
    assert score_support(0.20, 0)[0] == 0
    assert score_support(0.50, 0)[0] == 1
    assert score_support(0.65, 1)[0] == 2
    assert score_support(0.65, 3)[0] == 3
