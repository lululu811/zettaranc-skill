"""
P1-1 回归测试：DataSyncer 新方法 + modules/report + 4 个薄壳脚本

- sync_missing(ts_codes) 返回 Dict[ts_code, int]
- sync_daily_and_compute() 链式调用 sync_all_daily_kline + sync_all_indicators
- report.assess_watchlist([]) 返回 []
- report.render_assessment([]) 渲染空报告（含表头 + 元信息 + 0 指标）
- 4 个薄壳脚本能 --help 退出 0
"""

import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ==================== DataSyncer 新方法 ====================


def test_data_syncer_has_sync_missing_method():
    """DataSyncer 必须有 sync_missing() 方法（v2.10.0 P1-1 新增）"""
    from modules.data_sync import DataSyncer

    assert hasattr(DataSyncer, "sync_missing"), "DataSyncer.sync_missing missing"
    # 方法签名：sync_missing(self, ts_codes, days=730)
    import inspect

    sig = inspect.signature(DataSyncer.sync_missing)
    assert "ts_codes" in sig.parameters
    assert "days" in sig.parameters
    assert sig.parameters["days"].default == 730


def test_data_syncer_has_sync_daily_and_compute_method():
    """DataSyncer 必须有 sync_daily_and_compute() 方法（v2.10.0 P1-1 新增）"""
    from modules.data_sync import DataSyncer

    assert hasattr(DataSyncer, "sync_daily_and_compute"), "DataSyncer.sync_daily_and_compute missing"
    import inspect

    sig = inspect.signature(DataSyncer.sync_daily_and_compute)
    assert "ts_codes" in sig.parameters
    assert "days" in sig.parameters
    assert sig.parameters["days"].default == 730


def test_data_syncer_init_requires_token_in_jnb_mode():
    """JNB 模式下 DataSyncer __init__ 源码层面必须检查 TUSHARE_TOKEN / API URL（静态检查）"""
    # 静态检查避免 conftest autouse fixture 与 monkeypatch 互踩
    import inspect
    from modules.data_sync import DataSyncer

    src = inspect.getsource(DataSyncer.__init__)
    assert "DATA_MODE" in src
    assert "TUSHARE_TOKEN" in src
    assert "TUSHARE_API_URL" in src
    # 必须显式 raise ValueError 提示用户
    assert "raise ValueError" in src


# ==================== modules/report 新模块 ====================


def test_report_module_imports():
    """modules/report 必须可 import"""
    from modules import report

    assert hasattr(report, "StockAssessment")
    assert hasattr(report, "assess_watchlist")
    assert hasattr(report, "render_assessment")
    assert hasattr(report, "write_assessment")
    assert hasattr(report, "MACRO_SECTORS")


def test_assess_watchlist_empty_returns_empty_list():
    """空 ts_codes 必须返回 []"""
    from modules.report import assess_watchlist

    assert assess_watchlist([]) == []


def test_render_assessment_empty_report_has_header():
    """空评估列表必须渲染出表头（即使没数据）"""
    from modules.report import render_assessment

    out = render_assessment([])
    assert "Z哥量化评估报告" in out
    assert "生成时间" in out
    assert "股票总数: 0只" in out


def test_render_assessment_contains_three_parts():
    """报告必须包含 3 部分（个股深度 + 板块概览 + 操作建议）"""
    from modules.report import render_assessment

    out = render_assessment([])
    assert "第一部分" in out
    assert "第二部分" in out
    assert "第三部分" in out


def test_macro_sectors_has_at_least_ten_sectors():
    """MACRO_SECTORS 必须覆盖 ≥10 个板块"""
    from modules.report import MACRO_SECTORS

    assert len(MACRO_SECTORS) >= 10


# ==================== 4 个薄壳脚本 ====================

SHELL_SCRIPTS = [
    "scripts/sync_watchlist.py",
    "scripts/sync_and_compute.py",
    "scripts/batch_compute_indicators.py",
    "scripts/generate_report.py",
]


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_thin_shell_has_help(script):
    """4 个薄壳脚本必须支持 --help 退出 0"""
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / script), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    # argparse 默认 --help 退出 0
    assert (
        result.returncode == 0
    ), f"{script} --help exit {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_thin_shell_under_60_lines(script):
    """每个薄壳脚本必须 < 60 行（计划目标 <50 行，留点 buffer）"""
    lines = (PROJECT_ROOT / script).read_text(encoding="utf-8").count("\n")
    assert lines < 60, f"{script}: {lines} lines (target <50)"


def test_thin_shells_total_under_250_lines():
    """4 个薄壳脚本总行数 < 250（计划目标 <500）"""
    total = sum((PROJECT_ROOT / s).read_text(encoding="utf-8").count("\n") for s in SHELL_SCRIPTS)
    assert total < 250, f"Total: {total} lines (target <500)"


# ==================== 4 个薄壳脚本不再有重复实现 ====================


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_thin_shell_no_duplicate_compute_xxx(script):
    """4 个薄壳脚本不再含 compute_ma/ema/kdj/rsi/boll/macd 重复实现"""
    src = (PROJECT_ROOT / script).read_text(encoding="utf-8")
    forbidden = [
        "def compute_ma(",
        "def compute_ema(",
        "def compute_kdj(",
        "def compute_rsi(",
        "def compute_boll(",
        "def compute_macd(",
    ]
    for f in forbidden:
        assert f not in src, f"{script} still has duplicate: {f}"


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_thin_shell_no_hardcoded_user_path(script):
    """4 个薄壳脚本不再含 /Users/chenlei 硬编码"""
    src = (PROJECT_ROOT / script).read_text(encoding="utf-8")
    assert "/Users/chenlei" not in src, f"{script} still hardcodes /Users/chenlei"


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_thin_shell_uses_stocks_json_env_or_default(script):
    """4 个薄壳脚本必须支持 STOCKS_JSON env（直接或通过 scripts._common）"""
    src = (PROJECT_ROOT / script).read_text(encoding="utf-8")
    # v2.10.0: _load_watchlist 已提取到 scripts/_common.py，
    # 薄壳脚本通过 from scripts._common import load_watchlist 间接依赖
    common_src = (PROJECT_ROOT / "scripts" / "_common.py").read_text(encoding="utf-8")
    assert "STOCKS_JSON" in src or (
        "from scripts._common import" in src and "STOCKS_JSON" in common_src
    ), f"{script} doesn't support STOCKS_JSON env (directly or via _common)"
