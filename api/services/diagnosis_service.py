"""持仓诊断服务"""

import logging

logger = logging.getLogger(__name__)


def diagnose(ts_code: str, days: int = 120) -> dict:
    """对单只股票进行完整诊断"""
    from modules.portfolio_diagnosis import diagnose_stock

    report = diagnose_stock(ts_code, days=days)

    # 序列化出货信号
    exit_signals = []
    for sig in getattr(report, "exit_signals", []):
        if isinstance(sig, dict):
            exit_signals.append(
                {
                    "signal_type": sig.get("signal_type", ""),
                    "date": sig.get("date", ""),
                    "description": sig.get("description", ""),
                    "confidence": sig.get("confidence", 0),
                }
            )

    # 序列化买入信号
    buy_signals = []
    for sig in getattr(report, "buy_signals", []):
        if isinstance(sig, dict):
            buy_signals.append(
                {
                    "signal_type": sig.get("signal_type", ""),
                    "date": sig.get("date", ""),
                    "description": sig.get("description", ""),
                    "confidence": sig.get("confidence", 0),
                    "action": sig.get("action", ""),
                }
            )
        elif hasattr(sig, "strategy"):
            buy_signals.append(
                {
                    "signal_type": sig.strategy.value if hasattr(sig.strategy, "value") else str(sig.strategy),
                    "date": sig.trade_date,
                    "description": sig.description,
                    "confidence": sig.confidence,
                    "action": sig.action,
                }
            )

    return {
        "ts_code": ts_code,
        "name": getattr(report, "name", ts_code),
        "price": getattr(report, "price", 0),
        "trade_date": getattr(report, "trade_date", ""),
        "price_position": getattr(report, "price_position", ""),
        "trend_status": getattr(report, "trend_status", ""),
        "kdj_j": getattr(report, "kdj_j", 0),
        "macd_dif": getattr(report, "macd_dif", 0),
        "macd_veto": getattr(report, "macd_veto", False),
        "bbi": getattr(report, "bbi", 0),
        "white_line": getattr(report, "white_line", 0),
        "yellow_line": getattr(report, "yellow_line", 0),
        "is_gold_cross": getattr(report, "is_gold_cross", False),
        "is_dead_cross": getattr(report, "is_dead_cross", False),
        "sell_score": getattr(report, "sell_score", 0),
        "sell_score_desc": getattr(report, "sell_score_desc", ""),
        "sell_score_details": getattr(report, "sell_score_details", {}),
        "exit_signals": exit_signals,
        "buy_signals": buy_signals,
        "kirin_phase": getattr(report, "kirin_phase", "UNKNOWN"),
        "kirin_confidence": getattr(report, "kirin_confidence", 0),
        "is_centipede": getattr(report, "is_centipede", False),
        "centipede_score": getattr(report, "centipede_score", 0),
        "bull_rope_status": getattr(report, "bull_rope_status", ""),
        "bull_rope_gap_pct": getattr(report, "bull_rope_gap_pct", 0),
        "sandglass_score": getattr(report, "sandglass_score", 0),
        "sandglass_is_perfect": getattr(report, "sandglass_is_perfect", False),
        "stop_loss": getattr(report, "stop_loss", None),
        "target_price": getattr(report, "target_price", None),
        "recommendation": getattr(report, "recommendation", ""),
        "risk_level": getattr(report, "risk_level", "UNKNOWN"),
    }
