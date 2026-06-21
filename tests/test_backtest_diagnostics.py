from strategy.backtest import _s0_gate_diagnostic_row
from strategy.config import load_strategy_thresholds
from strategy.data_loader import load_live_data
from strategy.indicators import add_indicators


def test_s0_gate_diagnostics_use_configured_thresholds():
    thresholds = load_strategy_thresholds()
    row = add_indicators(load_live_data()).iloc[-1].copy()
    row["r_tech_dividend"] = thresholds.r_warning - 0.01
    row["clv_512890"] = thresholds.clv_support
    row["new_5d_low_512890"] = False
    row["amount_512890"] = row["amount_ma5_512890"]

    diagnostic = _s0_gate_diagnostic_row("2026-06-18", row, total_score=4)

    assert diagnostic["passed_all"] is True
    assert f"CLV>={thresholds.clv_support:.2f}" not in diagnostic["failed_conditions"]
