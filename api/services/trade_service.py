"""交易记录服务"""

import logging

logger = logging.getLogger(__name__)


def list_trades(page: int = 1, page_size: int = 20, ts_code: str | None = None) -> dict:
    """分页列出交易记录"""
    from modules.trade_manager import TradeManager

    tm = TradeManager()
    result = tm.list_all_trades(page=page, page_size=page_size)

    records = []
    for r in result.get("records", []):
        if ts_code and r.get("ts_code") != ts_code:
            continue
        records.append(
            {
                "id": r.get("id", 0),
                "ts_code": r.get("ts_code", ""),
                "trade_date": r.get("trade_date", ""),
                "action": r.get("action", ""),
                "price": r.get("price", 0),
                "quantity": r.get("quantity", 0),
                "amount": r.get("amount", 0),
                "reason": r.get("reason", ""),
                "signal_type": r.get("signal_type", ""),
                "zg_review": r.get("zg_review", ""),
                "tags": r.get("tags", ""),
                "notes": r.get("notes", ""),
            }
        )

    return {
        "total": result.get("total", len(records)),
        "page": page,
        "page_size": page_size,
        "records": records,
    }


def parse_trade(text: str) -> dict:
    """解析口语化交易描述（不保存）"""
    from modules.trade_parser import TradeParser

    parser = TradeParser()
    result = parser.parse(text)
    return {
        "success": result.success,
        "confidence": result.confidence,
        "data": result.data,
        "missing_fields": result.missing_fields,
        "error_message": result.error_message,
    }


def add_trade(text: str) -> dict:
    """解析并保存交易记录"""
    from modules.trade_parser import TradeParser
    from modules.trade_manager import TradeManager

    parser = TradeParser()
    parse_result = parser.parse(text)

    if not parse_result.success or not parse_result.data:
        return {
            "success": False,
            "error": parse_result.error_message or "解析失败",
            "missing_fields": parse_result.missing_fields,
        }

    tm = TradeManager()
    record_id = tm.add_trade(parse_result.data)
    return {
        "success": True,
        "id": record_id,
        "data": parse_result.data,
    }


def update_trade(trade_id: int, updates: dict) -> dict:
    """更新交易记录"""
    from modules.database import update_trade_record

    success = update_trade_record(trade_id, updates)
    return {"status": "ok" if success else "not_found"}


def delete_trade(trade_id: int) -> dict:
    """删除交易记录"""
    from modules.database import delete_trade_record

    success = delete_trade_record(trade_id)
    return {"status": "ok" if success else "not_found"}


def get_stats(ts_code: str | None = None) -> dict:
    """获取交易统计"""
    from modules.trade_manager import TradeManager

    tm = TradeManager()
    summary = tm.get_summary(ts_code=ts_code)
    pnl = tm.calculate_pnl(ts_code=ts_code)
    return {"summary": summary, "pnl": pnl}
