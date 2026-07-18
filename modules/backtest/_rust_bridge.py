"""CLI ↔ Rust PyO3 回测桥（v4.0.2）。

设计目标：
- 让 CLI 调用方 (`cli_commands.cmd_backtest` 等) 不必感知 Rust 是否可用
- Rust 不可用 / 调用失败 → silent fallback 到 Python
- ZETTARANC_BACKTEST_IMPL=python → 强制 Python（由 _rust_compat.compute_func 处理）

为什么需要这一层而不是直接 in-line 在 cli_commands.py 写：
- Rust 返回 schema (`{trades:[], metrics:{}, equity_curve:[]}`) 与 Python
  `ShaofuBacktestResult` dataclass 不同，需要做字段映射（avg_pnl / profit_factor /
  avg_holding_days 等 Python 侧有，Rust 侧要从 trades 派生）
- silent fallback（try/except + log warning + Python 路径）应该封装在一处
- 后续若 Rust screener 暴露 `screen_stocks_py`，bridge 也是统一的接入点
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from modules.core._rust_compat import compute_func as _rust_compat_compute_func

logger = logging.getLogger(__name__)

# CLI 业务层可以直接 `from modules.backtest._rust_bridge import compute_func`
compute_func = _rust_compat_compute_func


def is_rust_available() -> bool:
    """`_core_compute` 模块是否可用（不触发 import 缓存重置）。"""
    from modules.core._rust_compat import get_compute_module

    try:
        return get_compute_module() is not None
    except RuntimeError:
        # rust 模式下 import 失败被转成 RuntimeError；CLI 视角等价于"不可用"
        return False


def try_call(name: str, *args: Any, **kwargs: Any) -> Any:
    """尝试调 `_core_compute.<name>(*args, **kwargs)`。

    返回：Rust 调用返回值，或 None（不可用 / 抛错）。
    用法：业务层 `result = try_call(...) or python_fallback(...)`。
    """
    fn = compute_func(name)
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning(
            "Rust call %s(%s) failed, falling back to Python: %s",
            name,
            _arg_repr(args, kwargs),
            e,
        )
        return None


def _arg_repr(args: tuple, kwargs: dict, max_len: int = 80) -> str:
    """参数压缩展示（避免 logging 里 dump 整个 klines 列表）。"""
    parts: list[str] = [repr(a)[:max_len] for a in args[:3]]
    if len(args) > 3:
        parts.append(f"... +{len(args) - 3} more args")
    parts.extend(f"{k}={repr(v)[:max_len]}" for k, v in list(kwargs.items())[:3])
    return ", ".join(parts)


# ─────────────────────────────────────────────────────────────────────
# Schema 映射：Rust output dict → CLI 输出 dict
# ─────────────────────────────────────────────────────────────────────


def _kline_to_dict(kline: Any) -> dict:
    """K 线对象（dataclass / Pydantic / dict）→ Rust 期望的 dict。

    Rust 侧 parse_klines 期望的字段：trade_date / open / high / low / close / vol。
    """
    if isinstance(kline, dict):
        return kline
    # Pydantic v2
    if hasattr(kline, "model_dump"):
        return kline.model_dump()
    # dataclass
    if hasattr(kline, "__dict__"):
        return dict(kline.__dict__)
    # duck-type fallback
    return {
        "trade_date": getattr(kline, "trade_date", ""),
        "open": getattr(kline, "open", 0.0),
        "high": getattr(kline, "high", 0.0),
        "low": getattr(kline, "low", 0.0),
        "close": getattr(kline, "close", 0.0),
        "vol": getattr(kline, "vol", 0.0),
    }


def rust_single_result_to_cli_dict(ts_code: str, rust_result: dict) -> dict:
    """把 `run_single_strategy_backtest_py` 的 dict 输出映射成 CLI 期望的 dict。

    CLI 当前用 `_shaofu_result_to_dict(ShaofuBacktestResult)` 输出以下字段：
      ts_code / total_trades / win_count / win_rate / avg_pnl / max_win / max_loss /
      profit_factor / total_return / max_drawdown / sharpe_ratio /
      avg_holding_days / trades (list[dict])

    Rust 返回：
      trades: [{entry_date, exit_date, entry_price, exit_price, pnl, return, exit_reason}]
      metrics: {total_return, sharpe_ratio, max_drawdown, win_rate, final_value,
                initial_cash, total_trades}
      equity_curve: [float]

    派生字段（avg_pnl / max_win / max_loss / profit_factor / win_count /
    avg_holding_days）从 trades 计算。
    """
    metrics = rust_result.get("metrics", {}) or {}
    trades_raw = rust_result.get("trades", []) or []

    total = len(trades_raw)
    wins = [t for t in trades_raw if (t.get("pnl", 0.0) or 0.0) > 0]
    losses = [t for t in trades_raw if (t.get("pnl", 0.0) or 0.0) < 0]

    pnls = [t.get("return", 0.0) or 0.0 for t in trades_raw]
    avg_pnl = (sum(pnls) / total) if total else 0.0
    max_win = max(pnls) if pnls else 0.0
    max_loss = min(pnls) if pnls else 0.0

    win_sum = sum(t.get("pnl", 0.0) or 0.0 for t in wins)
    loss_sum = abs(sum(t.get("pnl", 0.0) or 0.0 for t in losses))
    profit_factor = (win_sum / loss_sum) if loss_sum > 1e-12 else 0.0

    # avg_holding_days：rust schema 当前没暴露 holding_days，但 entry_date/exit_date 可推
    holding_days = []
    for t in trades_raw:
        try:
            entry = t.get("entry_date", "")
            exit_ = t.get("exit_date")
            if entry and exit_:
                holding_days.append(_days_between(str(entry), str(exit_)))
        except Exception:
            continue
    avg_holding_days = (sum(holding_days) / len(holding_days)) if holding_days else 0.0

    trades_out = []
    for t in trades_raw:
        entry = t.get("entry_date", "")
        exit_ = t.get("exit_date")
        hdays = 0
        try:
            if entry and exit_:
                hdays = _days_between(str(entry), str(exit_))
        except Exception:
            pass
        trades_out.append(
            {
                "entry_date": entry,
                "entry_price": round(t.get("entry_price", 0.0) or 0.0, 2),
                "exit_date": exit_,
                "exit_price": round(t.get("exit_price", 0.0), 2) if t.get("exit_price") is not None else None,
                "exit_reason": t.get("exit_reason", "") or "",
                "pnl_pct": round((t.get("return", 0.0) or 0.0) * 100, 2),
                "holding_days": hdays,
            }
        )

    return {
        "ts_code": ts_code,
        "total_trades": total,
        "win_count": len(wins),
        "win_rate": round(metrics.get("win_rate", 0.0) or 0.0, 3),
        "avg_pnl": round(avg_pnl * 100, 2),
        "max_win": round(max_win * 100, 2),
        "max_loss": round(max_loss * 100, 2),
        "profit_factor": round(profit_factor, 2),
        "total_return": round((metrics.get("total_return", 0.0) or 0.0) * 100, 2),
        "max_drawdown": round((metrics.get("max_drawdown", 0.0) or 0.0) * 100, 2),
        "sharpe_ratio": round(metrics.get("sharpe_ratio", 0.0) or 0.0, 2),
        "avg_holding_days": round(avg_holding_days, 1),
        "trades": trades_out,
    }


def _days_between(d1: str, d2: str) -> int:
    """粗略计算两个日期字符串相差的天数（接受 'YYYYMMDD' 或 'YYYY-MM-DD'）。"""
    from datetime import datetime

    def _parse(s: str) -> datetime:
        s = s.strip()
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValueError(f"unrecognized date: {s!r}")

    return abs((_parse(d2) - _parse(d1)).days)


# ─────────────────────────────────────────────────────────────────────
# 单股少妇回测 bridge（CLI 侧 shaofu 子命令用）
# ─────────────────────────────────────────────────────────────────────


# Rust parse_single_config 的默认值（与 rust/crates/bindings/src/backtest_bindings.rs
# 中 parse_single_config 保持一致；CLI 调 Rust 时不传 config 即用这些）
_RUST_SINGLE_DEFAULTS: dict[str, Any] = {
    "j_threshold": -5.0,
    "stop_loss_pct": 0.05,
    "vol_shrink_threshold": 0.5,
    "bbi_break_days": 3,
    "min_holding_days": 3,
    "lu_half": True,
    "position_pct": 0.5,
    "initial_cash": 100_000.0,
}


def bridge_shaofu_single(
    ts_code: str,
    days: int = 250,
    klines: list | None = None,
    config: dict | None = None,
) -> dict:
    """单股少妇战法回测（CLI 用）。

    - Rust 可用：调 `run_single_strategy_backtest_py`，schema 映射后返回 CLI dict
    - Rust 不可用 / 失败：调 Python `backtest_shaofu_single` → `_shaofu_result_to_dict`

    Args:
        ts_code: 股票代码
        days: 回测天数（仅 Python 路径使用；Rust 路径从 klines 长度推断）
        klines: 已加载的 K 线（list[DailyData] / list[dict]）；None 时自动懒加载
        config: 策略参数 dict；None 时使用 `_RUST_SINGLE_DEFAULTS`（Rust 路径）

    Returns:
        与 `_shaofu_result_to_dict(ShaofuBacktestResult)` 同 schema 的 dict
    """
    # is_rust_available() 内部捕获 RuntimeError（impl=rust 但模块缺失时），
    # 保证 silent fallback；否则直接走 compute_func 会在 rust 模式下抛 RuntimeError
    if is_rust_available():
        fn = compute_func("run_single_strategy_backtest_py")
        if fn is not None:
            try:
                # 懒加载 K 线（CLI 调用方通常不传 klines，节省 Python 路径的二次拉取）
                if not klines:
                    from modules.indicators import get_kline_data

                    klines = get_kline_data(ts_code, days)

                if klines:
                    cfg = dict(_RUST_SINGLE_DEFAULTS)
                    if config:
                        cfg.update(config)
                    kline_dicts = [_kline_to_dict(k) for k in klines]
                    rust_result = fn(cfg, kline_dicts)
                    return rust_single_result_to_cli_dict(ts_code, rust_result)
            except Exception as e:
                logger.warning(
                    "Rust shaofu backtest failed for %s, falling back: %s",
                    ts_code,
                    e,
                )

    # Python fallback
    from modules.backtest_six_step import backtest_shaofu_single
    from modules.cli_commands import _shaofu_result_to_dict

    result = backtest_shaofu_single(ts_code, days=days, klines=klines)
    return _shaofu_result_to_dict(result)


# ─────────────────────────────────────────────────────────────────────
# 网格搜索 bridge（verify / portfolio_walk_forward 用）
# ─────────────────────────────────────────────────────────────────────


def bridge_grid_search(
    base_config: dict,
    param_grid: list[dict],
    splits: list[dict],
    klines_by_code: dict[str, list],
) -> dict | None:
    """Walk-forward 网格搜索（CLI / verify pipeline 用）。

    - Rust 可用：调 `run_grid_search_py`
    - Rust 不可用 / 失败：返回 None（调用方应回退 Python `portfolio_grid_search_optimize`）

    Returns:
        `{all_results, best_params, best_score, n_results}` 或 None
    """
    fn = compute_func("run_grid_search_py")
    if fn is None:
        return None

    try:
        # K 线转 dict
        klines_payload = {
            code: [_kline_to_dict(k) for k in series]
            for code, series in klines_by_code.items()
        }
        return fn(base_config, param_grid, splits, klines_payload)
    except Exception as e:
        logger.warning("Rust grid search failed, falling back: %s", e)
        return None


def reset_all_caches() -> None:
    """测试用：清空所有缓存（get_compute_module + 函数级）。"""
    from modules.core import _rust_compat

    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()