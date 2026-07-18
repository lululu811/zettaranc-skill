#!/usr/bin/env python3
"""
LLM 生成层

支持多种 LLM 提供商，用于将 Router 组装的系统提示词转化为最终回复。
使用 OpenAI 兼容接口调用 MiniMax 模型。

v3.10.4: 接入 ZettarancError
- 超时 → ``ZettarancError(LLM_TIMEOUT, ...)``
- API 返回非 2xx → ``ZettarancError(LLM_API_ERROR, ...)``
- 返回结构异常 → ``ZettarancError(LLM_INVALID_RESPONSE, ...)``
"""

from typing import Optional
import os
import httpx
import json
from collections.abc import Generator

from modules.core.errors import ErrorCode, ZettarancError


class LLMProvider:
    """LLM 生成基类"""

    def generate(self, system_prompt: str, user_message: str, temperature: float = 0.7, stream: bool = False) -> str:
        raise NotImplementedError


class MiniMaxProvider(LLMProvider):
    """MiniMax 提供商 (OpenAI 兼容模式)"""

    DEFAULT_BASE_URL = "https://api.minimaxi.com/v1/chat/completions"
    DEFAULT_MODEL = "MiniMax-M3"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        # 支持 LLM_API_KEY 或 ANTHROPIC_API_KEY
        self.api_key = api_key or os.getenv("LLM_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url: str = base_url or os.getenv("LLM_BASE_URL") or self.DEFAULT_BASE_URL
        self.model = model or os.getenv("LLM_MODEL", self.DEFAULT_MODEL)

        if not self.api_key:
            raise ZettarancError(
                ErrorCode.CONFIG_MISSING,
                "LLM_API_KEY not set. Please configure LLM_API_KEY in .env",
            )

    def generate(self, system_prompt: str, user_message: str, temperature: float = 0.7, stream: bool = False) -> str:
        """同步生成（使用 OpenAI 兼容接口）

        v3.10.4: 失败时抛 ``ZettarancError``：
        - 超时 → ``LLM_TIMEOUT``
        - API 非 2xx → ``LLM_API_ERROR``
        - 返回结构异常（无 choices / 解析失败）→ ``LLM_INVALID_RESPONSE``
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            "max_tokens": 4096,
        }

        try:
            resp = httpx.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=120.0,
            )
        except httpx.TimeoutException as e:
            raise ZettarancError(
                ErrorCode.LLM_TIMEOUT,
                f"MiniMax 请求超时 (120s): {e}",
                cause=e,
            ) from e
        except httpx.HTTPError as e:
            raise ZettarancError(
                ErrorCode.LLM_API_ERROR,
                f"MiniMax 请求失败: {e}",
                cause=e,
            ) from e

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ZettarancError(
                ErrorCode.LLM_API_ERROR,
                f"MiniMax HTTP {e.response.status_code}: {e.response.text[:200]}",
                cause=e,
            ) from e

        try:
            data = resp.json()
        except Exception as e:
            raise ZettarancError(
                ErrorCode.LLM_INVALID_RESPONSE,
                f"MiniMax 返回无法解析为 JSON: {e}",
                cause=e,
            ) from e

        if not isinstance(data, dict) or "choices" not in data or not data["choices"]:
            raise ZettarancError(
                ErrorCode.LLM_INVALID_RESPONSE,
                f"MiniMax 返回结构异常（无 choices）: {str(data)[:200]}",
            )

        content = data["choices"][0].get("message", {}).get("content")
        if not content:
            raise ZettarancError(
                ErrorCode.LLM_INVALID_RESPONSE,
                f"MiniMax 返回空内容: {str(data)[:200]}",
            )
        return content

    def generate_stream(
        self, system_prompt: str, user_message: str, temperature: float = 0.7
    ) -> Generator[str, None, None]:
        """流式生成（使用 OpenAI 兼容接口）

        v3.10.4: 网络/HTTP 错误抛 ``ZettarancError(LLM_TIMEOUT / LLM_API_ERROR)``。
        增量解析错误被跳过（不影响后续 delta），不再 yield 占位字符串。
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": 4096,
        }

        try:
            response = httpx.stream(
                "POST",
                self.base_url,
                headers=headers,
                json=payload,
                timeout=120.0,
            )
        except httpx.TimeoutException as e:
            raise ZettarancError(
                ErrorCode.LLM_TIMEOUT,
                f"MiniMax 流式请求超时 (120s): {e}",
                cause=e,
            ) from e
        except httpx.HTTPError as e:
            raise ZettarancError(
                ErrorCode.LLM_API_ERROR,
                f"MiniMax 流式请求失败: {e}",
                cause=e,
            ) from e

        try:
            with response as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line.startswith("data: "):
                        json_str = line[6:]
                        if json_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(json_str)
                        except json.JSONDecodeError:
                            continue
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
        except httpx.HTTPStatusError as e:
            raise ZettarancError(
                ErrorCode.LLM_API_ERROR,
                f"MiniMax 流式 HTTP {e.response.status_code}",
                cause=e,
            ) from e
