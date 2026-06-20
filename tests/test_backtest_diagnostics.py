from strategy.backtest import run_backtest
from strategy.data_loader import load_sample_data


def test_backtest_returns_benchmark_and_diagnostics():
    df = load_sample_data()
    result = run_backtest(df, initial_capital=100000)

    assert "benchmark_total_return" in result.metrics
    assert "excess_return" in result.metrics
    assert "average_position" in result.diagnostics
    assert "s0_ratio" in result.diagnostics
    assert "state_counts" in result.diagnostics
    assert result.benchmark_curve is not None
    assert result.state_history is not None
    assert result.s0_gate_failures is not None
