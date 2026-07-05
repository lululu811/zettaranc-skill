"""
少女/少妇模拟器 v0.2 CLI 参数解析测试
"""

from __future__ import annotations

from modules.cli import build_parser


def test_cli_simulate_arguments_parsed():
    """新 v0.2 参数必须被正确解析为 argparse 属性"""
    parser = build_parser()
    args = parser.parse_args(["simulate", "000001.SZ", "--atr-sizing", "--max-position-pct", "0.15"])
    assert args.atr_sizing is True
    assert args.max_position_pct == 0.15


def test_cli_simulate_defaults_unchanged():
    """默认行为与 v0.1/v0.2 保持一致"""
    parser = build_parser()
    args = parser.parse_args(["simulate"])
    assert args.codes is None
    assert args.days == 250
    assert args.capital == 1_000_000
    assert args.max_positions == 5
    assert args.risk == 0.02
    assert args.score == 70.0
    assert args.signals == 2
    assert args.benchmark == "000300.SH"
    assert args.cost_model == "simple"
    assert args.slippage == "fixed"
    assert args.atr_sizing is False
    assert args.max_position_pct == 0.20
    assert args.no_st is False
    assert args.t1_lock is True
    # v0.3 新增默认值
    assert args.strategy_mode == "simple"
    assert args.strategy_lookback == 5
    assert args.min_resonance_score == 0.35


def test_cli_strategy_mode_argument():
    """v0.3 战法共振参数必须被正确解析"""
    parser = build_parser()
    args = parser.parse_args(
        ["simulate", "000001.SZ", "--strategy-mode", "resonance", "--strategy-lookback", "3", "--min-resonance-score", "0.5"]
    )
    assert args.strategy_mode == "resonance"
    assert args.strategy_lookback == 3
    assert args.min_resonance_score == 0.5


def test_cli_simulate_advanced_options():
    """进阶选项解析"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "simulate",
            "000001.SZ,000002.SZ",
            "--benchmark",
            "000905.SH",
            "--cost-model",
            "advanced",
            "--slippage",
            "dynamic",
            "--atr-sizing",
            "--max-position-pct",
            "0.10",
            "--no-st",
            "--no-t1-lock",
            "--json",
        ]
    )
    assert args.codes == "000001.SZ,000002.SZ"
    assert args.benchmark == "000905.SH"
    assert args.cost_model == "advanced"
    assert args.slippage == "dynamic"
    assert args.atr_sizing is True
    assert args.max_position_pct == 0.10
    assert args.no_st is True
    assert args.t1_lock is False
    assert args.json is True


def test_cli_simulate_t1_lock_explicit():
    """显式 --t1-lock 保持 True"""
    parser = build_parser()
    args = parser.parse_args(["simulate", "000001.SZ", "--t1-lock"])
    assert args.t1_lock is True
