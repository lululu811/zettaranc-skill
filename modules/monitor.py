#!/usr/bin/env python3
"""
Z哥量化自选股监视引擎
负责同步自选股、计算指标、扫描信号，并执行桌面及 IM 推送。
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# 加载环境变量与包目录（如果作为脚本运行）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.data_sync import DataSyncer
from modules.watchlist import scan_watchlist, generate_daily_report, get_watchlist
from modules.notifier import notify_all

logger = logging.getLogger("zettaranc-monitor")


def run_watchlist_monitor(sync_days: int = 30, enable_push: bool = True) -> dict:
    """
    运行自选股同步与主动监控
    """
    logger.info("启动自选股主动监控...")

    # 1. 获取自选股代码
    watches = get_watchlist()
    if not watches:
        logger.info("自选股清单为空，跳过监控。")
        return {"alerts_count": 0, "status": "empty"}

    ts_codes = [w["ts_code"] for w in watches]

    # 2. 增量同步数据并计算缓存
    logger.info(f"开始同步 {len(ts_codes)} 只自选股的 K 线数据(回溯 {sync_days} 天)...")
    try:
        syncer = DataSyncer()
        syncer.sync_daily_and_compute(ts_codes=ts_codes, days=sync_days)
    except Exception as e:
        logger.error(f"同步数据失败: {e}，将直接进行本地扫描。")

    # 3. 扫描信号
    scan_result = scan_watchlist()
    alerts = scan_result["alerts"]
    summary = scan_result["summary"]

    # 4. 生成文本报告并保存到工作区
    report_text = generate_daily_report()

    report_dir = Path("data/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "monitor_alert.md"

    # 转换为 Markdown 友好格式并保存
    report_file.write_text(report_text, encoding="utf-8")
    logger.info(f"报告已写入 {report_file}")

    # 5. 主动推送核心警报
    if enable_push and alerts:
        # 统计各级别警报
        criticals = [a for a in alerts if a.level == "CRITICAL"]
        warnings = [a for a in alerts if a.level == "WARNING"]
        infos = [a for a in alerts if a.level == "INFO"]

        # 构造一条简短紧凑的消息发送到通知栏或 IM
        # 优先通知 CRITICAL 和 WARNING
        alert_msgs = []
        for a in (criticals + warnings + infos)[:5]:
            code_show = a.ts_code.split(".")[0]
            alert_msgs.append(f"{a.name}({code_show}): {a.message}")

        summary_msg = f"共发现 {len(alerts)} 个自选股警报！\n"
        summary_msg += "\n".join(alert_msgs)
        if len(alerts) > 5:
            summary_msg += f"\n...等共 {len(alerts)} 条，详情请看 data/reports/monitor_alert.md"

        title = "Z哥交易风险警报" if (criticals or warnings) else "Z哥盘后机会扫描"

        # 触发推送
        logger.info("发现警报，触发多通路主动推送...")
        notify_all(title=title, message=summary_msg)

    return {"alerts_count": len(alerts), "summary": summary, "status": "success"}


def main():
    import argparse

    p = argparse.ArgumentParser(description="自选股主动预警服务")
    p.add_argument("--days", type=int, default=30, help="同步 K 线回溯天数")
    p.add_argument("--no-push", action="store_true", help="关闭主动推送通知")
    args = p.parse_args()

    # 配置基础日志输出到控制台
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    res = run_watchlist_monitor(sync_days=args.days, enable_push=not args.no_push)
    print(f"扫描完毕。状态: {res['status']}, 警报数: {res.get('alerts_count', 0)}")


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    main()
