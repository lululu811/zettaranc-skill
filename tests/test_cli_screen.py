"""
P0-1 回归测试：修 cmd_screen 必崩 + cmd_watchlist scan 静默

- cmd_screen 必须接受 11 种 strategy 中文别名并正确映射到 screener 英文 criteria
- cmd_screen 必须调 screener.screen_stocks()，不再访问 StockScore 上不存在的字段
- cmd_watchlist scan 必须读 alerts 字段（不是 stocks）
"""

import sys
from unittest.mock import patch, MagicMock

import pytest


# 16 个 strategy 中文别名（与 cli.STRATEGY_ALIAS 保持同步）
EXPECTED_STRATEGIES = [
    "B1",
    "B2",
    "B3",
    "完美图形",
    "超级B1",
    "长安战法",
    "建仓波",
    "吸筹",
    "安全",
    "超跌",
    "突破",
    "牵牛",
    "牛绳",
    "沙漏",
    "沙漏评分",
    "量比战法",
]


@pytest.fixture
def fake_screen_result():
    """构造一个 fake StockScore 列表供 mock 返回"""
    from modules.screener import StockScore

    return [
        StockScore(
            ts_code="600519.SH",
            name="贵州茅台",
            score=85.0,
            b1_score=80.0,
            trend_score=90.0,
            volume_score=75.0,
            risk_score=80.0,
            reasons=["B1买点出现", "KDJ金叉"],
            warnings=["接近压力位"],
        ),
        StockScore(
            ts_code="000001.SZ",
            name="平安银行",
            score=72.0,
            b1_score=70.0,
            trend_score=75.0,
            volume_score=70.0,
            risk_score=65.0,
            reasons=["趋势向上"],
            warnings=[],
        ),
    ]


# ==================== cmd_screen 修复验证 ====================


def test_strategy_alias_covers_all_sixteen():
    """STRATEGY_ALIAS 必须覆盖 16 种 strategy"""
    from modules.cli import STRATEGY_ALIAS

    assert len(STRATEGY_ALIAS) == 16
    for name in EXPECTED_STRATEGIES:
        assert name in STRATEGY_ALIAS, f"STRATEGY_ALIAS 缺 {name}"


def test_strategy_alias_mapping_is_correct():
    """关键映射必须正确（B1→b1, B2→b2_breakout 等）"""
    from modules.cli import STRATEGY_ALIAS

    assert STRATEGY_ALIAS["B1"] == "b1"
    assert STRATEGY_ALIAS["B2"] == "b2_breakout"
    assert STRATEGY_ALIAS["B3"] == "b3_consensus"
    assert STRATEGY_ALIAS["完美图形"] == "perfect"
    assert STRATEGY_ALIAS["超级B1"] == "super_b1"
    assert STRATEGY_ALIAS["长安战法"] == "changan"
    assert STRATEGY_ALIAS["建仓波"] == "build_wave"
    assert STRATEGY_ALIAS["吸筹"] == "xishou"
    assert STRATEGY_ALIAS["安全"] == "safe"
    assert STRATEGY_ALIAS["超跌"] == "oversold"
    assert STRATEGY_ALIAS["突破"] == "breakout"
    assert STRATEGY_ALIAS["牵牛"] == "bull_rope"
    assert STRATEGY_ALIAS["牛绳"] == "bull_rope"
    assert STRATEGY_ALIAS["沙漏"] == "sandglass_perfect"
    assert STRATEGY_ALIAS["沙漏评分"] == "sandglass_perfect"
    assert STRATEGY_ALIAS["量比战法"] == "volume_ratio_super"


def test_strategy_choices_matches_alias_keys():
    """STRATEGY_CHOICES 必须等于 STRATEGY_ALIAS.keys()"""
    from modules.cli import STRATEGY_ALIAS, STRATEGY_CHOICES

    assert set(STRATEGY_CHOICES) == set(STRATEGY_ALIAS.keys())


@pytest.mark.parametrize("chinese_name", EXPECTED_STRATEGIES)
def test_screen_parser_accepts_all_strategies(chinese_name, fake_screen_result, capsys):
    """main() parser 必须接受 11 种 strategy 中文别名"""
    from modules.cli import main

    test_args = ["zt", "screen", "--strategy", chinese_name, "--limit", "5", "--no-parallel"]

    with (
        patch.object(sys, "argv", test_args),
        patch("modules.screener.screen_stocks", return_value=fake_screen_result) as mock_screen,
    ):
        main()

    # 1. screen_stocks 必须被调用
    assert mock_screen.called, f"screen_stocks 未被调用（strategy={chinese_name}）"

    # 2. 调用参数中的 criteria 必须是英文别名（不再是中文）
    call_kwargs = mock_screen.call_args.kwargs
    assert call_kwargs["criteria"] != chinese_name, f"criteria 仍是中文 {chinese_name}，未走 STRATEGY_ALIAS 映射"

    # 3. use_parallel 应该是 False（因为传了 --no-parallel）
    assert call_kwargs["use_parallel"] is False

    # 4. max_stocks 应该是 5（不是 args.limit 默认 20）
    assert call_kwargs["max_stocks"] == 5

    # 5. 输出包含 ts_code + score + rating
    out = capsys.readouterr().out
    assert "600519.SH" in out
    assert "85.0" in out
    assert "推荐" in out or "强烈推荐" in out  # rating property


def test_screen_calls_screen_stocks_not_self_loop(fake_screen_result, capsys):
    """cmd_screen 必须调 screener.screen_stocks()，不调 StockScore 自写循环"""
    from modules.cli import main

    test_args = ["zt", "screen", "--strategy", "B1", "--limit", "5", "--no-parallel"]

    with (
        patch.object(sys, "argv", test_args),
        patch("modules.screener.screen_stocks", return_value=fake_screen_result) as mock_screen,
        patch("modules.screener.StockScore") as mock_bare_score,
    ):
        main()

    # screen_stocks 必须被调
    assert mock_screen.called
    # 裸 StockScore 构造（无 K 线参数）不应该被调——这正是 v2.9.0 bug 的触发点
    # 如果未来有人重新引入自写循环，StockScore(ts_code) 会被大量调
    assert mock_bare_score.call_count == 0, (
        f"cmd_screen 仍调用 StockScore() 自写循环（{mock_bare_score.call_count} 次）"
    )


def test_screen_limit_zero_means_full_market(fake_screen_result, capsys):
    """--limit 0 表示扫全市场（pass max_stocks=0 给 screen_stocks）"""
    from modules.cli import main

    test_args = ["zt", "screen", "--strategy", "B1", "--limit", "0", "--no-parallel"]

    with (
        patch.object(sys, "argv", test_args),
        patch("modules.screener.screen_stocks", return_value=fake_screen_result) as mock_screen,
    ):
        main()

    call_kwargs = mock_screen.call_args.kwargs
    assert call_kwargs["max_stocks"] == 0, "limit=0 必须透传给 max_stocks=0"


# ==================== cmd_watchlist scan 修复验证 ====================


def test_watchlist_scan_uses_alerts_key():
    """cmd_watchlist scan 必须读 alerts 字段，不再读 stocks（v2.9.0 静默零结果 bug）"""
    from modules.cli import main

    test_args = ["zt", "watchlist", "scan"]

    fake_alert = MagicMock()
    fake_alert.level = "INFO"
    fake_alert.ts_code = "600519.SH"
    fake_alert.name = "茅台"
    fake_alert.alert_type = "B1"
    fake_alert.message = "测试 B1 买点"

    fake_result = {
        "alerts": [fake_alert],
        "summary": {
            "total": 1,
            "b1_count": 1,
            "b2_count": 0,
            "exit_count": 0,
            "break_count": 0,
            "abnormal_count": 0,
        },
    }

    # patch 源位置 modules.watchlist.scan_watchlist（cmd_watchlist 内部 from import）
    with (
        patch.object(sys, "argv", test_args),
        patch("modules.watchlist.scan_watchlist", return_value=fake_result) as mock_scan,
        patch("sys.stdout") as mock_stdout,
    ):
        main()

    # scan_watchlist 必须被调
    assert mock_scan.called
    # 关键断言：输出必须包含 alert 内容（不是空）
    printed = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
    assert "600519.SH" in printed, "B1 警报内容未打印"
    assert "测试 B1 买点" in printed, "B1 警报消息未打印"
    assert "B1=1" in printed, "summary 未打印"


def test_watchlist_scan_empty_alerts_does_not_crash():
    """空 alerts 时 cmd_watchlist scan 必须优雅打印 0（不崩）"""
    from modules.cli import main

    test_args = ["zt", "watchlist", "scan"]

    fake_result = {
        "alerts": [],
        "summary": {"total": 5, "b1_count": 0, "b2_count": 0, "exit_count": 0, "break_count": 0, "abnormal_count": 0},
    }

    with patch.object(sys, "argv", test_args), patch("modules.watchlist.scan_watchlist", return_value=fake_result):
        # 不应抛异常
        main()


# ==================== 端到端 smoke：parser 接受 11 种 ====================


def test_help_lists_all_sixteen_strategies(capsys):
    """zt screen --help 应该列出 16 种 strategy"""
    from modules.cli import main

    with patch.object(sys, "argv", ["zt", "screen", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    for name in EXPECTED_STRATEGIES:
        assert name in out, f"screen --help 未列出 {name}"
