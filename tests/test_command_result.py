"""命令结果外壳的护栏。

候选 5（CommandResult）的核心缺陷：**CLI ``--json`` 出错时 stdout 完全为空**，
宿主的 JSON 解析直接失败，也拿不到 ``ErrorCode``。API 侧同样把 50+ 个
``ErrorCode`` 压成 ``{"error": "internal_error"}``。

这些测试锁死：
- CLI ``--json`` 错误路径产出**合法 JSON** 且带 ``error_code``；
- ``ErrorCode`` 在 CLI 与 API 两侧都**保真**（不被压成通用字符串）；
- CLI 与 API 的错误外壳**同形**（字段集与取值一致）。
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from modules.core.command_result import CommandResult, exception_to_dict, http_status_for
from modules.core.errors import ErrorCode, ZettarancError


def _run_cli(*args: str) -> tuple[int, str, str]:
    """跑一次 zt CLI，返回 (退出码, stdout, stderr)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "modules.cli", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestExceptionToDict:
    def test_zettaranc_error_keeps_code_and_message(self):
        payload = exception_to_dict(ZettarancError(ErrorCode.INVALID_PARAM, "days 必须 > 0"))
        assert payload["ok"] is False
        assert payload["error_code"] == "INVALID_PARAM"
        assert payload["message"] == "days 必须 > 0"
        assert payload["cause"] is None

    def test_cause_is_preserved(self):
        cause = ValueError("底层原因")
        payload = exception_to_dict(ZettarancError(ErrorCode.DB_ERROR, "查询失败", cause=cause))
        assert "底层原因" in payload["cause"]

    def test_plain_exception_falls_back_to_internal_error(self):
        """未分类异常不再退化成无语义的 internal_error 字符串，而是有明确错误码。"""
        payload = exception_to_dict(RuntimeError("崩了"))
        assert payload["error_code"] == ErrorCode.INTERNAL_ERROR.value
        assert payload["message"] == "崩了"

    def test_all_error_codes_have_unique_values(self):
        """错误码必须唯一——否则宿主按 code 分支会串。"""
        values = [c.value for c in ErrorCode]
        assert len(values) == len(set(values))


class TestHttpStatusFor:
    @pytest.mark.parametrize(
        "code",
        [
            ErrorCode.INVALID_PARAM,
            ErrorCode.SIMULATOR_INVALID_PRICE,
            ErrorCode.SCREENER_INVALID_CRITERIA,
            ErrorCode.BACKTEST_INVALID_CONFIG,
            ErrorCode.CONFIG_MISSING,
        ],
    )
    def test_client_errors_are_4xx(self, code):
        """参数非法属调用方问题——此前一律 500，宿主无法区分。"""
        assert http_status_for(ZettarancError(code, "x")) == 400

    @pytest.mark.parametrize(
        "code",
        [
            ErrorCode.SCREENER_NO_DATA,
            ErrorCode.SIMULATOR_NO_KLINES,
            ErrorCode.BACKTEST_EMPTY_KLINES,
            ErrorCode.INDEVS_NO_DATA,
        ],
    )
    def test_missing_data_is_404(self, code):
        assert http_status_for(ZettarancError(code, "x")) == 404

    def test_other_errors_are_5xx(self):
        assert http_status_for(ZettarancError(ErrorCode.DB_ERROR, "x")) == 500
        assert http_status_for(RuntimeError("x")) == 500


class TestCommandResult:
    def test_success_keeps_payload_as_is(self):
        """成功路径**不改**各命令原有的 JSON 载荷形状（向后兼容）。"""
        payload = {"success": True, "count": 3}
        result = CommandResult.success(payload)
        assert result.ok is True
        assert result.data == payload
        assert result.to_dict() == {"ok": True, "data": payload}

    def test_failure_has_error_code(self):
        result = CommandResult.failure(ErrorCode.INVALID_PARAM, "参数错")
        assert result.ok is False
        assert result.error_code == "INVALID_PARAM"
        assert result.to_dict() == {
            "ok": False,
            "error_code": "INVALID_PARAM",
            "message": "参数错",
            "cause": None,
        }

    def test_from_exception(self):
        result = CommandResult.from_exception(ZettarancError(ErrorCode.RATE_LIMIT, "太频繁"))
        assert result.ok is False
        assert result.error_code == "RATE_LIMIT"


class TestCliJsonErrorPath:
    """CLI ``--json`` 错误路径——本候选的核心缺陷。"""

    def test_error_outputs_valid_json_on_stdout(self):
        """出错时 stdout 必须是**合法 JSON**，不能是空的。"""
        code, stdout, stderr = _run_cli("simulate", "--days", "0", "--json")
        assert code != 0
        assert stdout.strip(), "错误时 stdout 为空——宿主的 JSON 解析会直接失败"
        payload = json.loads(stdout)  # 解析失败即测试失败
        assert payload["ok"] is False
        assert payload["error_code"], "错误码丢失——宿主无法按 code 分支"
        assert payload["message"]

    def test_error_code_is_preserved(self):
        """错误码必须保真为具体的 ErrorCode，而不是通用字符串。"""
        _, stdout, _ = _run_cli("simulate", "--days", "0", "--json")
        payload = json.loads(stdout)
        assert payload["error_code"] == ErrorCode.SIMULATOR_INVALID_PRICE.value

    def test_stderr_still_has_human_readable_message(self):
        """stderr 仍保留人类可读信息（不为了 JSON 牺牲可读性）。"""
        _, _, stderr = _run_cli("simulate", "--days", "0", "--json")
        assert "SIMULATOR_INVALID_PRICE" in stderr

    def test_argparse_error_also_outputs_json(self):
        """argparse 自身的参数错误（解析阶段就退出）也必须产出合法 JSON。"""
        code, stdout, _ = _run_cli("verify", "--bogus-flag", "--json")
        assert code != 0
        payload = json.loads(stdout)
        assert payload["ok"] is False
        assert payload["error_code"] == ErrorCode.INVALID_PARAM.value

    def test_without_json_flag_stdout_stays_empty(self):
        """不加 --json 时保持原有行为（stdout 空，错误信息在 stderr）。"""
        code, stdout, stderr = _run_cli("simulate", "--days", "0")
        assert code != 0
        assert stdout.strip() == ""
        assert "SIMULATOR_INVALID_PRICE" in stderr


class TestCliApiErrorShellParity:
    """CLI 与 API 的错误外壳必须同形——宿主只写一套解析。"""

    def test_same_field_set(self):
        cli_payload = json.loads(_run_cli("simulate", "--days", "0", "--json")[1])
        api_payload = exception_to_dict(ZettarancError(ErrorCode.SIMULATOR_INVALID_PRICE, "days 必须 > 0"))
        assert set(cli_payload) == set(api_payload)

    def test_same_values_for_same_error(self):
        cli_payload = json.loads(_run_cli("simulate", "--days", "0", "--json")[1])
        api_payload = exception_to_dict(ZettarancError(ErrorCode.SIMULATOR_INVALID_PRICE, "days 必须 > 0，当前: 0"))
        assert cli_payload["error_code"] == api_payload["error_code"]
        assert cli_payload["message"] == api_payload["message"]
