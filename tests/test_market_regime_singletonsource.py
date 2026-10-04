"""回归测试:MarketRegime 单一来源 + TrendRegime 命名规则。

- 唯一 `MarketRegime` 枚举必须来自 modules.core.market_context(STRONG/NEUTRAL/WEAK, Chinese values)
- modules.market_regime 必须命名为 TrendRegime(BULL/BEAR/SIDEWAYS, English values)
- 防止 v3.10.x 之前的"两个 MarketRegime 同名"问题复发
"""

import ast
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _iter_python_files() -> list[Path]:
    """遍历 modules/ 和 tests/ 下的所有 .py 文件(不含 __pycache__)。"""
    out: list[Path] = []
    for sub in ("modules", "tests"):
        base = PROJECT_ROOT / sub
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    return out


def test_market_regime_defined_only_in_core_market_context():
    """class MarketRegime(Enum) 只允许在 modules/core/market_context.py 出现。"""
    offenders: list[str] = []
    for p in _iter_python_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MarketRegime":
                # 允许:core/market_context.py
                rel = p.relative_to(PROJECT_ROOT)
                if rel != Path("modules/core/market_context.py"):
                    offenders.append(str(rel))
    assert not offenders, (
        f"MarketRegime 只允许在 modules/core/market_context.py 定义;"
        f"违规: {offenders}。若新模块需要趋势方向枚举,应使用 modules.market_regime.TrendRegime。"
    )


def test_no_import_of_market_regime_marketregime():
    """不允许 from modules.market_regime import MarketRegime (老命名)。"""
    offenders: list[str] = []
    for p in _iter_python_files():
        # 用 AST 解析,只检查 import 语句,跳过 docstring 误伤
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "market_regime" in node.module:
                for alias in node.names:
                    if alias.name == "MarketRegime" and alias.name != "MarketRegimeClassifier":
                        offenders.append(
                            f"{p.relative_to(PROJECT_ROOT)}:{node.lineno}: from {node.module} import {alias.name}"
                        )
    assert not offenders, "禁止 import 已废弃的 modules.market_regime.MarketRegime;违规:\n  " + "\n  ".join(offenders)


def test_core_market_context_market_regime_is_canonical():
    """core.market_context.MarketRegime 仍存在,值是中文(STRONG/NEUTRAL/WEAK = 强势/震荡/弱势)。"""
    from modules.core.market_context import MarketRegime

    assert MarketRegime.STRONG.value == "强势"
    assert MarketRegime.NEUTRAL.value == "震荡"
    assert MarketRegime.WEAK.value == "弱势"


def test_market_regime_module_exposes_trend_regime():
    """modules.market_regime 仍暴露 TrendRegime(BULL/BEAR/SIDEWAYS)。"""
    from modules.market_regime import TrendRegime, MarketRegimeClassifier

    assert TrendRegime.BULL.value == "BULL"
    assert TrendRegime.BEAR.value == "BEAR"
    assert TrendRegime.SIDEWAYS.value == "SIDEWAYS"
    # 分类器签名应使用 TrendRegime(from __future__ import annotations 下,annotation 是字符串)
    import typing

    resolved = typing.get_type_hints(MarketRegimeClassifier.classify).get("return")
    assert resolved is TrendRegime


def test_market_regime_classifier_returns_trend_regime():
    """MarketRegimeClassifier.classify() 必须返回 TrendRegime,不是 core.market_context.MarketRegime。"""
    from modules.indicators import DailyData
    from modules.market_regime import MarketRegimeClassifier, TrendRegime
    from modules.core.market_context import MarketRegime as CoreMarketRegime

    # 构造 200 天上升趋势 K 线
    klines = []
    price = 100.0
    for i in range(200):
        price *= 1.003  # +0.3%/日
        klines.append(
            DailyData(
                ts_code="000001.SH",
                trade_date=f"2026{(i // 30) + 1:02d}{(i % 30) + 1:02d}",
                open=price * 0.99,
                high=price * 1.01,
                low=price * 0.98,
                close=price,
                vol=1e8,
                amount=price * 1e8,
                pct_chg=0.3,
                prev_close=price / 1.003,
            )
        )
    result = MarketRegimeClassifier().classify(klines)
    # 关键不变量:返回值属于 TrendRegime,不是 CoreMarketRegime
    assert isinstance(result, TrendRegime)
    assert not isinstance(result, CoreMarketRegime), (
        "MarketRegimeClassifier 不应返回 core.market_context.MarketRegime;"
        "两个枚举语义不同(BULL/BEAR/SIDEWAYS 趋势方向 vs STRONG/NEUTRAL/WEAK 仓位档位)"
    )
