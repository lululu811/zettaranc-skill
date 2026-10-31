"""CLI 子命令测试"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.verify.cli import build_parser, run_verify_v10


def test_build_parser_has_required_args():
    """必填参数都在"""
    parser = build_parser()
    # 用 sys.argv 模拟
    args = parser.parse_args(["--limit", "30", "--days", "200"])
    assert args.limit == 30
    assert args.days == 200
    assert args.walk_forward is False
    assert args.json is False


def test_build_parser_limit_range_validation():
    """--limit 必须在 [10, 500]"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "5"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "1000"])


def test_run_verify_v10_invokes_pipeline():
    """run_verify_v10 调用 pipeline"""
    with patch("modules.verify.cli.verify_v10_pipeline") as mock_pipeline:
        from modules.verify.pipeline import VerifyResult, AggregateMetrics

        mock_pipeline.return_value = VerifyResult(
            aggregate=AggregateMetrics(),
        )
        run_verify_v10(
            ts_codes=["000001.SZ"],
            days=250,
        )
        mock_pipeline.assert_called_once()


def test_run_verify_v10_resolves_ts_codes_arg(temp_db, tmp_path):
    """端到端路径：run_verify_v10 接收 ts_codes= 时，pipeline 必须被调用且
    实际传入我们给的股票列表（**不** mock verify_v10_pipeline —— 只 mock 底层 backtest/data，
    把 Task 11 之前发现的 ImportError + 参数断层补上）。

    该测试同时验证：
      1. modules.database.get_all_stock_codes 真的存在（修复 ImportError）
      2. verify/cli.py 的 _resolve_ts_codes 路径走得通
      3. ts_codes 传给底层 backtest（不会回落到 stock_basic 全表）
    """
    from modules.database import get_all_stock_codes
    from modules.verify.pipeline import VerifyResult, AggregateMetrics

    # 注入一只到 stock_basic，验证 fallback 路径确实被绕过
    from modules.database import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO stock_basic
            (ts_code, name, area, industry, market, list_date, is_hs)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("999999.SH", "退市测试股", "深圳", "测试", "主板", "20010101", "SH"),
        )
        conn.commit()

    # 把 backtest_shaofu_single 打桩成返回空结果 —— 这样不用真实行情数据
    # v4.9.0 起验收走**真组合**分支（PortfolioBacktestEngine），
    # 与自优化器 V10VerifyScorer 的默认一致——原先 CLI 走的是逐股独立回测
    # + 等权合并曲线，优化目标与验收口径脱节。
    with (
        patch("modules.verify.portfolio_engine.PortfolioBacktestEngine") as mock_engine_cls,
        patch("modules.verify.pipeline.get_datasource") as mock_ds,
        patch("modules.verify.pipeline.LoopConfig") as mock_loop_cfg,
    ):
        # datasource 给一只股票返回足量 K 线（>60 根）
        fake_klines = [
            {
                "ts_code": "600519.SH",
                "trade_date": "20260101",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "vol": 10000.0,
                "amount": 1000000.0,
                "pct_chg": 0.5,
            }
            for _ in range(120)
        ]
        mock_ds.return_value.get_kline_dicts.return_value = fake_klines

        # LoopConfig.from_registry 默认返回 None 的实际类型兼容
        from modules.loop_engine import LoopConfig as RealLoopConfig

        mock_loop_cfg.from_registry.return_value = RealLoopConfig()

        # PortfolioBacktestResult-like 简易对象
        from types import SimpleNamespace

        mock_engine_cls.return_value.run.return_value = SimpleNamespace(
            total_trades=0,
            win_count=0,
            loss_count=0,
            win_rate=0.0,
            avg_pnl=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            max_win=0.0,
            max_loss=0.0,
            profit_factor=0.0,
            avg_holding_days=0.0,
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            calmar=0.0,
            trades=[],
            net_values=[],
            dates=[],
        )

        out_dir = tmp_path / "reports"
        result = run_verify_v10(
            ts_codes=["600519.SH"],
            days=250,
            write_markdown=False,
            output_dir=str(out_dir),
        )

        # result 是一个 VerifyResult
        assert isinstance(result, VerifyResult)
        assert result.meta.get("ts_codes_count") == 1
        # 没有回落到 get_all_stock_codes
        mock_engine = mock_engine_cls.return_value
        assert mock_engine.run.call_count == 1
        mock_engine.run.assert_called_once()
        called_args, called_kwargs = mock_engine.run.call_args
        assert called_args[0] == ["600519.SH"]

        # 验证 get_all_stock_codes 真的可用（Bug 1 已修）
        codes = get_all_stock_codes()
        assert "999999.SH" in codes  # 我们注入的那只


class TestVerifyOutputAndExitCode:
    """zt verify 的 --output 转发与退出码。

    背景：顶层 CLI 曾把解析好的参数重新拼成 argv 交给第二个 argparse，
    --output 因此被静默丢弃（报告落到 data/reports 而不是用户指定的目录），
    且 handler 的退出码在 cli.py 的分发处被丢掉——参数错误时进程仍退 0。
    """

    @staticmethod
    def _args(**overrides):
        from argparse import Namespace

        base = {
            "limit": 50,
            "days": 250,
            "walk_forward": False,
            "wf_train": 120,
            "wf_test": 60,
            "ts_codes": "600519.SH",
            "output": None,
            "json": False,
            "no_markdown": False,
        }
        base.update(overrides)
        return Namespace(**base)

    def test_cmd_verify_v10_forwards_output_dir(self, tmp_path, monkeypatch):
        """--output 必须真的生效：报告写进用户指定的目录。"""
        from modules.cli_commands.backtest import cmd_verify_v10
        from modules.verify.pipeline import VerifyResult

        out_dir = tmp_path / "custom_reports"
        monkeypatch.setattr(
            "modules.verify.cli.verify_v10_pipeline",
            lambda **kwargs: VerifyResult(),
        )

        rc = cmd_verify_v10(self._args(output=str(out_dir)))

        assert rc == 0
        assert out_dir.is_dir(), "--output 指定的目录应被创建"
        assert list(out_dir.glob("verify_v10_*.json")), "报告应写在 --output 指定的目录"
        assert list(out_dir.glob("verify_v10_*.md")), "Markdown 报告同样应在那里"

    def test_cmd_verify_v10_returns_2_on_invalid_param(self, capsys):
        """参数非法 → 退出码 2（不是 0）。"""
        from modules.cli_commands.backtest import cmd_verify_v10

        rc = cmd_verify_v10(self._args(days=50))  # days 必须在 [120, 1000]

        assert rc == 2
        assert "参数错误" in capsys.readouterr().out

    def test_verify_cli_main_returns_2_on_invalid_param(self, capsys):
        """argparse 适配层同样返回 2。"""
        from modules.verify.cli import main as verify_main

        rc = verify_main(["--days", "50"])

        assert rc == 2
        assert "参数错误" in capsys.readouterr().out

    def test_run_verify_v10_command_returns_0_on_valid_params(self, monkeypatch, capsys):
        """参数合法 → 退出码 0。"""
        from modules.verify.cli import run_verify_v10_command
        from modules.verify.pipeline import VerifyResult

        monkeypatch.setattr(
            "modules.verify.cli.verify_v10_pipeline",
            lambda **kwargs: VerifyResult(),
        )

        rc = run_verify_v10_command(ts_codes_arg="600519.SH", days=250)

        assert rc == 0
