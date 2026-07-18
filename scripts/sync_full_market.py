#!/usr/bin/env python3
"""
全量同步全市场日K线数据

通过 tushare-data-bridge 的 CLI 逐日同步全市场数据
然后批量导入到 stock_data.db

用法:
    python3 scripts/sync_full_market.py                  # 同步最近 2 年数据
    python3 scripts/sync_full_market.py --start 20240101  # 指定起始日期
    python3 scripts/sync_full_market.py --dry-run         # 只查看计划，不执行
"""

import sys
import os
import json
import time
import sqlite3
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


# tushare-data-bridge 路径
BRIDGE_DIR = Path.home() / ".kimi" / "daimon" / "skills" / "tushare-data-bridge"
BRIDGE_CLI = BRIDGE_DIR / "scripts" / "cli.py"
BRIDGE_DB = BRIDGE_DIR / "data" / "tushare.db"

# 我们的数据库
OUR_DB = Path("data/stock_data.db")


def get_trade_dates(start_date: str, end_date: str) -> list[str]:
    """从 trade_cal 表获取交易日历"""
    conn = sqlite3.connect(BRIDGE_DB)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cal_date FROM trade_cal
        WHERE cal_date >= ? AND cal_date <= ? AND is_open = 1
        ORDER BY cal_date ASC
    """,
        (start_date, end_date),
    )
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates


def get_existing_dates() -> set[str]:
    """获取我们数据库中已有的股票代码"""
    conn = sqlite3.connect(OUR_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ts_code FROM daily_kline")
    stocks = set(row[0] for row in cursor.fetchall())
    conn.close()
    return stocks


def get_existing_dates_range() -> tuple[str, str]:
    """获取我们数据库中已有数据的日期范围"""
    conn = sqlite3.connect(OUR_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_kline")
    row = cursor.fetchone()
    conn.close()
    return row[0] or "", row[1] or ""


def get_synced_dates_in_bridge() -> set[str]:
    """获取 bridge DB 中已同步的 trade_date"""
    conn = sqlite3.connect(BRIDGE_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT trade_date FROM daily")
    dates = set(row[0] for row in cursor.fetchall())
    conn.close()
    return dates


def sync_one_day(trade_date: str) -> dict:
    """同步某一天的全市场数据"""
    result = subprocess.run(
        ["python3", str(BRIDGE_CLI), "sync", "--api", "daily", "--trade-date", trade_date],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # 解析 JSON 结果（cli 输出最后几行有 JSON）
    for line in reversed(result.stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return {"status": "error", "error": result.stderr[:200] if result.stderr else "unknown"}


def import_to_our_db(trade_dates: list[str]) -> int:
    """从 bridge DB 导入指定日期范围的数据到我们的 DB"""
    conn_bridge = sqlite3.connect(BRIDGE_DB)
    cursor_bridge = conn_bridge.cursor()

    conn_our = sqlite3.connect(OUR_DB)
    cursor_our = conn_our.cursor()

    # 获取我们数据库的股票列表（只导入已有的股票）
    cursor_our.execute("SELECT DISTINCT ts_code FROM daily_kline")
    our_stocks = set(row[0] for row in cursor_our.fetchall())

    inserted = 0
    for td in trade_dates:
        cursor_bridge.execute(
            """
            SELECT ts_code, trade_date, open, high, low, close, vol, amount,
                   pct_chg, pre_close
            FROM daily
            WHERE trade_date = ? AND ts_code IN ({})
        """.format(",".join("?" * len(our_stocks))),
            [td] + list(our_stocks),
        )

        rows = cursor_bridge.fetchall()
        for row in rows:
            ts_code, trade_date, open_p, high, low, close, vol, amount, pct_chg, pre_close = row

            try:
                open_f = float(open_p) if open_p else 0
                high_f = float(high) if high else 0
                low_f = float(low) if low else 0
                close_f = float(close) if close else 0
                vol_f = float(vol) if vol else 0
                amount_f = float(amount) if amount else 0
                pct_chg_f = float(pct_chg) if pct_chg else 0
                pre_close_f = float(pre_close) if pre_close else 0

                change = close_f - pre_close_f if pre_close_f > 0 else 0

                # 涨跌停判断
                if ts_code.endswith("BJ"):
                    is_limit_up = pct_chg_f >= 29
                    is_limit_down = pct_chg_f <= -29
                elif ts_code.startswith("300") or ts_code.startswith("688"):
                    is_limit_up = pct_chg_f >= 19.5
                    is_limit_down = pct_chg_f <= -19.5
                else:
                    is_limit_up = pct_chg_f >= 9.5
                    is_limit_down = pct_chg_f <= -9.5

                cursor_our.execute(
                    """
                    INSERT OR REPLACE INTO daily_kline
                    (ts_code, trade_date, open, high, low, close, vol, amount,
                     pct_chg, pre_close, change, is_limit_up, is_limit_down)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        ts_code,
                        trade_date,
                        open_f,
                        high_f,
                        low_f,
                        close_f,
                        vol_f,
                        amount_f,
                        pct_chg_f,
                        pre_close_f,
                        change,
                        1 if is_limit_up else 0,
                        1 if is_limit_down else 0,
                    ),
                )
                inserted += 1

            except (ValueError, TypeError):
                continue

    conn_our.commit()
    conn_bridge.close()
    conn_our.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="全量同步全市场日K线数据")
    parser.add_argument("--start", default="20240101", help="起始日期 (YYYYMMDD)")
    parser.add_argument("--end", default=None, help="结束日期 (YYYYMMDD，默认今天)")
    parser.add_argument("--dry-run", action="store_true", help="只查看计划，不执行")
    parser.add_argument("--skip-import", action="store_true", help="只同步不导入")
    parser.add_argument("--batch-size", type=int, default=20, help="每批同步天数")
    args = parser.parse_args()

    end_date = args.end or datetime.now().strftime("%Y%m%d")
    start_date = args.start

    print("\n" + "=" * 70)
    print("全量同步全市场日K线数据")
    print("=" * 70)
    print(f"  起始日期: {start_date}")
    print(f"  结束日期: {end_date}")
    print(f"  Bridge DB: {BRIDGE_DB}")
    print(f"  目标 DB: {OUR_DB}")

    # 1. 获取交易日历
    print("\n【Step 1】获取交易日历...")
    trade_dates = get_trade_dates(start_date, end_date)
    print(f"  交易日数量: {len(trade_dates)}")

    # 2. 检查哪些日期需要同步
    print("\n【Step 2】检查需要同步的日期...")
    synced_dates = get_synced_dates_in_bridge()
    pending_dates = [d for d in trade_dates if d not in synced_dates]
    print(f"  已同步: {len(trade_dates) - len(pending_dates)} 天")
    print(f"  待同步: {len(pending_dates)} 天")

    if not pending_dates:
        print("\n✅ 所有日期已同步，无需操作")
    elif args.dry_run:
        print("\n📋 Dry-run 模式，不执行同步")
        print(f"  前 5 天: {pending_dates[:5]}")
        print(f"  后 5 天: {pending_dates[-5:]}")
    else:
        # 3. 逐日同步
        print(f"\n【Step 3】开始同步（每批 {args.batch_size} 天）...\n")

        success = 0
        failed = 0
        total_rows = 0

        for i, td in enumerate(pending_dates, 1):
            result = sync_one_day(td)
            status = result.get("status", "unknown")
            rows = result.get("rows", 0)

            if status == "success":
                success += 1
                total_rows += rows
                print(f"  [{i}/{len(pending_dates)}] {td}: ✅ {rows} 条")
            else:
                failed += 1
                error = result.get("error", "")[:50]
                print(f"  [{i}/{len(pending_dates)}] {td}: ❌ {error}")

            # 小延迟避免过快
            time.sleep(0.3)

        print(f"\n同步完成: 成功 {success}, 失败 {failed}, 总行数 {total_rows:,}")

    # 4. 导入到我们的数据库
    if not args.skip_import and not args.dry_run:
        print(f"\n【Step 4】导入数据到 {OUR_DB}...")

        # 获取已同步的日期
        synced_dates = get_synced_dates_in_bridge()
        import_dates = [d for d in trade_dates if d in synced_dates]

        print(f"  准备导入 {len(import_dates)} 天的数据...")
        inserted = import_to_our_db(import_dates)
        print(f"  ✅ 导入完成: {inserted:,} 条记录")

        # 验证
        conn = sqlite3.connect(OUR_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM daily_kline")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT MAX(trade_date) FROM daily_kline")
        max_date = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT ts_code) FROM daily_kline")
        stocks = cursor.fetchone()[0]
        conn.close()

        print(f"\n{'=' * 70}")
        print("✅ 全部完成!")
        print(f"{'=' * 70}")
        print(f"  数据库总记录: {total:,}")
        print(f"  股票数量: {stocks}")
        print(f"  最新日期: {max_date}")
    elif args.dry_run:
        pass
    else:
        print("\n⏭️  跳过导入")


if __name__ == "__main__":
    main()
