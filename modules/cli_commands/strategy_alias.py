"""CLI 中文别名 → screener 英文 criteria 的统一映射。

单一事实来源：``modules/screener/aliases.py``（Web API 侧复用同一份），
此处只做 re-export，避免两份映射漂移（曾出现 CLI 少 3 个「简单完美图形」别名的问题）。
"""

from __future__ import annotations

from modules.screener.aliases import STRATEGY_ALIAS

STRATEGY_CHOICES: list[str] = list(STRATEGY_ALIAS.keys())

__all__ = ["STRATEGY_ALIAS", "STRATEGY_CHOICES"]
