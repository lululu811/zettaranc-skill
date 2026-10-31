"""自选股管理服务"""

import logging

logger = logging.getLogger(__name__)


def list_watchlist(tags: str | None = None) -> dict:
    """列出自选股"""
    from modules.watchlist import list_watch

    items = list_watch(tags=tags)
    result_items = []
    for item in items:
        result_items.append(
            {
                "id": item.get("id", 0),
                "ts_code": item.get("ts_code", ""),
                "name": item.get("name", ""),
                "tags": item.get("tags", ""),
                "notes": item.get("notes", ""),
                "added_date": item.get("added_date", ""),
                "alert_enabled": item.get("alert_enabled", True),
            }
        )
    return {"count": len(result_items), "items": result_items}


def add_to_watchlist(ts_code: str, tags: str = "", notes: str = "") -> dict:
    """添加到自选股"""
    from modules.watchlist import add_watch

    row_id = add_watch(ts_code, tags=tags, notes=notes)
    return {"status": "ok", "id": row_id}


def remove_from_watchlist(ts_code: str) -> dict:
    """从自选股移除"""
    from modules.watchlist import remove_watch

    success = remove_watch(ts_code)
    return {"status": "ok" if success else "not_found"}


def scan_watchlist() -> dict:
    """扫描自选股信号"""
    from modules.watchlist import scan_watchlist

    result = scan_watchlist()
    alerts = []
    for a in result.get("alerts", []):
        if hasattr(a, "ts_code"):
            alerts.append(
                {
                    "ts_code": a.ts_code,
                    "name": a.name,
                    "alert_type": a.alert_type,
                    "level": a.level,
                    "message": a.message,
                }
            )
        elif isinstance(a, dict):
            alerts.append(
                {
                    "ts_code": a.get("ts_code", ""),
                    "name": a.get("name", ""),
                    "alert_type": a.get("alert_type", ""),
                    "level": a.get("level", ""),
                    "message": a.get("message", ""),
                }
            )

    summary = result.get("summary", {})
    return {
        "total": summary.get("total", 0),
        "b1_count": summary.get("b1_count", 0),
        "b2_count": summary.get("b2_count", 0),
        "exit_count": summary.get("exit_count", 0),
        "break_count": summary.get("break_count", 0),
        "abnormal_count": summary.get("abnormal_count", 0),
        "alerts": alerts,
    }


def generate_report() -> dict:
    """生成日报"""
    from modules.watchlist import generate_daily_report

    report_text = generate_daily_report()
    return {"report": report_text}
