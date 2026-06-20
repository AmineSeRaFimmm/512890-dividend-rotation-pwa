import pandas as pd

from strategy.state_machine import evaluate_strategy


def test_high_r_does_not_hard_veto_512890_observation_buy():
    rows = []
    dates = pd.date_range("2026-01-01", periods=25, freq="B")
    for i, day in enumerate(dates):
        close_512 = 1.00 + i * 0.004
        close_588 = 1.88 + i * 0.002
        rows.append(
            {
                "date": day,
                "open_512890": close_512 - 0.002,
                "high_512890": close_512 + 0.004,
                "low_512890": close_512 - 0.006,
                "close_512890": close_512,
                "volume_512890": 100000000 + i,
                "amount_512890": 110000000 + i,
                "open_588000": close_588 - 0.002,
                "high_588000": close_588 + 0.005,
                "low_588000": close_588 - 0.005,
                "close_588000": close_588,
                "volume_588000": 200000000 + i,
                "amount_588000": 360000000 + i,
            }
        )

    result = evaluate_strategy(pd.DataFrame(rows), current_position=0.0, capital=100000)

    assert result.raw["r_tech_dividend"] > 1.70
    assert result.action == "BUY_512890"
    assert result.target_position == 0.20
