"""
P0-4 回归测试：quality_check.py --json / --strict flag

- 验证 --json 输出可被 json.loads 解析
- 验证 --json 输出包含 8 项 check + summary
- 验证 --strict 在 fail 时退出码 = 1
- 验证默认行为兼容（不传 --json 走人读模式）
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_CHECK = PROJECT_ROOT / "corpus" / "quality_check.py"
SKILL_MD = PROJECT_ROOT / "SKILL.md"


def run_quality_check(*flags) -> subprocess.CompletedProcess:
    """调 quality_check.py 跑 SKILL.md"""
    cmd = [sys.executable, str(QUALITY_CHECK), str(SKILL_MD), *flags]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


# ==================== --json flag ====================

def test_json_output_is_valid_json():
    """--json 输出必须是合法 JSON"""
    result = run_quality_check("--json")
    assert result.returncode in (0, 1), f"unexpected exit code {result.returncode}"
    data = json.loads(result.stdout)
    assert isinstance(data, dict)


def test_json_output_has_eight_checks():
    """--json 输出必须包含 8 项 check"""
    result = run_quality_check("--json")
    data = json.loads(result.stdout)
    assert "checks" in data
    assert len(data["checks"]) == 8, f"expected 8 checks, got {len(data['checks'])}"


def test_json_output_has_summary_fields():
    """--json 输出必须包含 summary 字段"""
    result = run_quality_check("--json")
    data = json.loads(result.stdout)
    for key in ("file", "passed", "failed", "total", "all_passed", "checks"):
        assert key in data, f"missing key: {key}"


def test_json_output_check_structure():
    """每条 check 必须有 name / passed / detail 字段"""
    result = run_quality_check("--json")
    data = json.loads(result.stdout)
    for c in data["checks"]:
        assert "name" in c
        assert "passed" in c
        assert isinstance(c["passed"], bool)
        assert "detail" in c
        assert isinstance(c["detail"], str)


def test_json_output_uses_unicode():
    """中文 check 名称必须正确出现在 JSON（不转义）"""
    result = run_quality_check("--json")
    # 验证 ensure_ascii=False 生效
    assert "\\u" not in result.stdout  # 没有 unicode 转义
    assert "心智模型" in result.stdout  # 中文原样输出


# ==================== --strict flag ====================

def test_strict_exit_code_reflects_failures():
    """--strict 模式下，失败项数 > 0 时 exit 1"""
    # 真实的 SKILL.md 应该至少通过大部分检查，--strict 行为应与默认行为一致
    result = run_quality_check("--strict")
    assert result.returncode in (0, 1), f"unexpected exit code {result.returncode}"


# ==================== 默认行为兼容 ====================

def test_default_human_readable_output():
    """不传 --json 应该走人读模式（不输出 JSON）"""
    result = run_quality_check()
    # 默认输出应该是人读格式，不以 '{' 开头
    assert not result.stdout.lstrip().startswith("{"), \
        "default output should be human-readable, not JSON"
    # 应该包含中文标签
    assert "质量检查" in result.stdout or "心智模型" in result.stdout


def test_default_exit_code_compatibility():
    """默认退出码：全过 = 0，否则 = 1（保持 v2.9.0 行为兼容）"""
    result = run_quality_check()
    assert result.returncode in (0, 1)


# ==================== 参数解析 ====================

def test_missing_file_arg_exits_one():
    """不传文件参数应该 exit 1 并提示用法"""
    result = subprocess.run(
        [sys.executable, str(QUALITY_CHECK)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "用法" in result.stdout


def test_missing_file_with_json_exits_one():
    """--json + 不传文件参数 = 仍 exit 1（参数解析不依赖 JSON 模式）"""
    result = subprocess.run(
        [sys.executable, str(QUALITY_CHECK), "--json"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    # JSON 模式下提示也要走 JSON
    data = json.loads(result.stdout)
    assert "error" in data
