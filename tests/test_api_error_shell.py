"""API 错误外壳的护栏（候选 5）。

API 侧此前把 50+ 个 ``ErrorCode`` 全压成 ``{"error": "internal_error"}``，
宿主既拿不到错误码，也无法区分 4xx 与 5xx。

这些测试锁死：
- API 错误响应是**扁平统一外壳**（与 CLI 同形，不被 ``{"detail": …}`` 包一层）；
- ``ErrorCode`` 保真；
- 状态码按错误码区分 4xx / 404 / 5xx。

``fastapi`` 不在 ``requirements.txt``（是可选依赖），缺失时整文件跳过。
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from modules.core.errors import ErrorCode, ZettarancError  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _patch_analysis(monkeypatch, exc: BaseException):
    """让 stock 路由的分析接口抛出指定异常。"""
    import api.routes.stock as stock_route

    def boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(stock_route.stock_service, "get_full_analysis", boom)


class TestApiErrorShell:
    def test_error_response_is_flat_not_nested(self, client, monkeypatch):
        """错误体是扁平的 ``{"ok": false, …}``，不是 ``{"detail": {"ok": false, …}}``。

        FastAPI 默认会把 ``HTTPException.detail`` 包一层——那样宿主要写两套解析。
        """
        _patch_analysis(monkeypatch, ZettarancError(ErrorCode.INVALID_PARAM, "参数非法"))
        resp = client.get("/api/v1/stock/analyze/600519.SH?days=30")
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" not in body, "错误体被 FastAPI 多包了一层 detail"
        assert body["ok"] is False
        assert body["error_code"] == "INVALID_PARAM"
        assert body["message"] == "参数非法"

    def test_error_code_is_preserved(self, client, monkeypatch):
        """具体错误码不得退化成 internal_error。"""
        _patch_analysis(monkeypatch, ZettarancError(ErrorCode.RATE_LIMIT, "触发限流"))
        resp = client.get("/api/v1/stock/analyze/600519.SH?days=30")
        assert resp.json()["error_code"] == ErrorCode.RATE_LIMIT.value

    def test_unclassified_exception_gets_internal_error_code(self, client, monkeypatch):
        """未分类异常仍有明确错误码 + 5xx。"""
        _patch_analysis(monkeypatch, RuntimeError("底层崩了"))
        resp = client.get("/api/v1/stock/analyze/600519.SH?days=30")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error_code"] == ErrorCode.INTERNAL_ERROR.value
        assert "底层崩了" in body["message"]

    def test_client_error_maps_to_400(self, client, monkeypatch):
        _patch_analysis(monkeypatch, ZettarancError(ErrorCode.INVALID_PARAM, "参数非法"))
        assert client.get("/api/v1/stock/analyze/600519.SH?days=30").status_code == 400

    def test_missing_data_maps_to_404(self, client, monkeypatch):
        """数据不存在是 404，不是 500。"""
        _patch_analysis(monkeypatch, ZettarancError(ErrorCode.SIMULATOR_NO_KLINES, "无 K 线"))
        assert client.get("/api/v1/stock/analyze/600519.SH?days=30").status_code == 404

    def test_shell_has_same_fields_as_cli(self, client, monkeypatch):
        """API 与 CLI 的错误外壳字段集完全一致。"""
        from modules.core.command_result import exception_to_dict

        _patch_analysis(monkeypatch, ZettarancError(ErrorCode.INVALID_PARAM, "参数非法"))
        api_body = client.get("/api/v1/stock/analyze/600519.SH?days=30").json()
        cli_body = exception_to_dict(ZettarancError(ErrorCode.INVALID_PARAM, "参数非法"))
        assert set(api_body) == set(cli_body)
