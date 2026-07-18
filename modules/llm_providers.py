#!/usr/bin/env python3
"""
LLM 生成层

支持多种 LLM 提供商，用于将 Router 组装的系统提示词转化为最终回复。
使用 OpenAI 兼容接口调用 MiniMax 模型。
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
        """同步生成（使用 OpenAI 兼容接口）"""
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
            resp.raise_for_status()
            data = resp.json()

            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            else:
                return f"[MiniMax API 返回格式异常] {str(data)[:200]}"
        except httpx.HTTPError as e:
            return f"[MiniMax API 请求失败] {e}"
        except Exception as e:
            return f"[MiniMax 生成异常] {e}"

    def generate_stream(
        self, system_prompt: str, user_message: str, temperature: float = 0.7
    ) -> Generator[str, None, None]:
        """流式生成（使用 OpenAI 兼容接口）"""
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
            "stream": True,
            "max_tokens": 4096,
        }

        try:
            with httpx.stream(
                "POST",
                self.base_url,
                headers=headers,
                json=payload,
                timeout=120.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        json_str = line[6:]
                        if json_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(json_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            yield f"[MiniMax 流式生成异常] {e}"
