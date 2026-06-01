"""
P1-2 回归测试：5 个独立 main() 合并到 cli.py

- 7 个顶层 subcommand 都可识别（analyze/screen/score/workflow/diagnose/watchlist/sync）
- watchlist 5 个子动作（add/remove/list/scan/report）
- sync 4 个子动作（init/sync/status/stk-factor）
- 顶层 subcommand 缺失时 exit 非 0
- 全局 prog = "zt"
"""
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_zt(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "modules.cli", *args],
        capture_output=True, text=True, timeout=15,
        cwd=str(PROJECT_ROOT),
    )


# ==================== 顶层 subcommand ====================

EXPECTED_TOP_COMMANDS = ["analyze", "screen", "score", "workflow", "diagnose", "watchlist", "sync"]


def test_top_level_help_lists_all_seven_commands():
    """zt --help 必须列出 7 个顶层 subcommand"""
    result = run_zt("--help")
    assert result.returncode == 0
    for cmd in EXPECTED_TOP_COMMANDS:
        assert cmd in result.stdout, f"--help 缺 {cmd}"


@pytest.mark.parametrize("cmd", EXPECTED_TOP_COMMANDS)
def test_each_top_command_has_help(cmd):
    """每个顶层 subcommand 必须支持 --help"""
    result = runzt_safe = run_zt(cmd, "--help")
    assert result.returncode == 0, \
        f"{cmd} --help exit {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"


def test_missing_command_exits_nonzero():
    """不传任何 subcommand 应该 exit 非 0（required=True）"""
    result = run_zt()
    assert result.returncode != 0
    # argparse 应该打印 usage + 错误到 stderr
    assert "usage:" in result.stderr or "usage:" in result.stdout


def test_prog_is_zt():
    """顶层 ArgumentParser 的 prog 必须是 zt"""
    result = run_zt("--help")
    assert "usage: zt " in result.stdout


# ==================== watchlist 子动作 ====================

EXPECTED_WL_ACTIONS = ["add", "remove", "list", "scan", "report"]


def test_watchlist_help_lists_all_five_actions():
    """zt watchlist --help 必须列出 5 个 action（含新增 report）"""
    result = run_zt("watchlist", "--help")
    assert result.returncode == 0
    for action in EXPECTED_WL_ACTIONS:
        assert action in result.stdout, f"watchlist --help 缺 {action}"


# ==================== sync 子动作 ====================

EXPECTED_SYNC_ACTIONS = ["init", "sync", "status", "stk-factor"]


def test_sync_help_lists_all_four_actions():
    """zt sync --help 必须列出 4 个 action"""
    result = run_zt("sync", "--help")
    assert result.returncode == 0
    for action in EXPECTED_SYNC_ACTIONS:
        assert action in result.stdout, f"sync --help 缺 {action}"


def test_sync_init_help():
    """zt sync init --help 必须 exit 0"""
    result = run_zt("sync", "init", "--help")
    assert result.returncode == 0


def test_sync_sync_help():
    """zt sync sync --help 必须 exit 0"""
    result = run_zt("sync", "sync", "--help")
    assert result.returncode == 0
    # ts_code 是位置参数（nargs='?'），不是 --ts_code flag
    # 其余是 flag
    for flag in ("ts_code", "--days", "--indicators", "--skip-indicators"):
        assert flag in result.stdout, f"sync sync --help 缺 {flag}"


def test_sync_stk_factor_help():
    """zt sync stk-factor --help 必须 exit 0"""
    result = run_zt("sync", "stk-factor", "--help")
    assert result.returncode == 0


# ==================== screen 11 种 strategy 仍被接受 ====================

STRATEGY_ALIAS = {
    "B1": "b1", "B2": "b2_breakout", "B3": "b3_consensus",
    "完美图形": "perfect", "超级B1": "super_b1",
    "长安战法": "changan", "建仓波": "build_wave",
    "吸筹": "xishou", "安全": "safe", "超跌": "oversold", "突破": "breakout",
}


@pytest.mark.parametrize("strategy", STRATEGY_ALIAS.keys())
def test_screen_accepts_all_strategies_via_cli(strategy):
    """screen --help 应该列出所有 11 种 strategy"""
    result = run_zt("screen", "--help")
    assert result.returncode == 0
    assert strategy in result.stdout, f"screen --help 缺 {strategy}"


# ==================== analyze / diagnose / score / workflow 必要 flag ====================

def test_analyze_help_has_required_args():
    result = run_zt("analyze", "--help")
    assert result.returncode == 0
    assert "ts_code" in result.stdout
    assert "--days" in result.stdout


def test_diagnose_help_has_required_args():
    result = run_zt("diagnose", "--help")
    assert result.returncode == 0
    assert "ts_code" in result.stdout
    assert "--days" in result.stdout


def test_score_help_has_ts_code():
    result = run_zt("score", "--help")
    assert result.returncode == 0
    assert "ts_code" in result.stdout


def test_workflow_help_works():
    """workflow 无参数，但 --help 应该 exit 0"""
    result = run_zt("workflow", "--help")
    assert result.returncode == 0


# ==================== zt 整体可用性 smoke ====================

def test_zt_help_does_not_crash():
    """最简单 smoke：zt --help 完整跑通"""
    result = run_zt("--help")
    assert result.returncode == 0
    # 应该看到 epilog 中的示例
    assert "zt analyze" in result.stdout
    assert "zt sync" in result.stdout
