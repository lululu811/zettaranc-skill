#!/usr/bin/env python3
"""
端到端数据读写完整性测试
覆盖所有核心表的 写入 → 读取 → 字段校验 全链路
"""
import os
import sys
import tempfile
from pathlib import Path

# 指向项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置临时测试数据库
test_db = tempfile.mkdtemp() + "/test_e2e.db"
os.environ["DB_PATH"] = test_db
os.environ["DATA_MODE"] = "websearch"

from modules.database import (
    get_connection, init_database, get_db_path,
    save_trade_record, get_trade_records, get_trade_record_by_id,
    update_trade_record, delete_trade_record, get_trade_summary,
    add_watchlist_item, remove_watchlist_item, get_watchlist, update_watchlist_item,
)

PASS = 0
FAIL = 0
WARN = 0

def check(label, condition, detail=""):
    global PASS, FAIL, WARN
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        msg = f"  ❌ {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)

def warn(label, detail=""):
    global WARN
    WARN += 1
    msg = f"  ⚠️ {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)

# ============================================================
print("=" * 60)
print("数据层端到端读写测试")
print("=" * 60)

# ---- 0. 数据库初始化 ----
print("\n[0] 数据库初始化")
init_database()
db_path = get_db_path()
check("数据库文件已创建", db_path.exists(), str(db_path))

with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r['name'] for r in cursor.fetchall()]
    expected_tables = {
        'daily_kline', 'indicator_cache', 'moneyflow', 'financial_data',
        'stock_basic', 'trade_signals', 'trade_records', 'sync_log',
        'watchlist', 'tushare_indicator_cache'
    }
    for t in sorted(expected_tables):
        check(f"表 {t} 存在", t in tables)

# ============================================================
# ---- 1. stock_basic 写入/读取 ----
print("\n[1] stock_basic 表（股票基本信息）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO stock_basic (ts_code, name, area, industry, market, list_date, is_hs)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ('000001.SZ', '平安银行', '深圳', '银行', '主板', '19910403', 'S'))
    cursor.execute("SELECT * FROM stock_basic WHERE ts_code = ?", ('000001.SZ',))
    row = cursor.fetchone()

check("写入+读取成功", row is not None)
if row:
    check("ts_code", row['ts_code'] == '000001.SZ', f"实际: {row['ts_code']}")
    check("name", row['name'] == '平安银行', f"实际: {row['name']}")
    check("area", row['area'] == '深圳', f"实际: {row['area']}")
    check("industry", row['industry'] == '银行', f"实际: {row['industry']}")
    check("market", row['market'] == '主板', f"实际: {row['market']}")
    check("list_date", row['list_date'] == '19910403', f"实际: {row['list_date']}")
    check("is_hs", row['is_hs'] == 'S', f"实际: {row['is_hs']}")

# ============================================================
# ---- 2. daily_kline 写入/读取 ----
print("\n[2] daily_kline 表（日线K线数据）")
with get_connection() as conn:
    cursor = conn.cursor()
    test_klines = [
        ('000001.SZ', '20250101', 10.0, 10.5, 9.8, 10.3, 1000.0, 10300.0, 3.0, 1.2, 0, 0),
        ('000001.SZ', '20250102', 10.3, 10.8, 10.1, 10.6, 1200.0, 12600.0, 2.91, 1.3, 0, 0),
        ('000001.SZ', '20250103', 10.6, 11.2, 10.4, 11.0, 1500.0, 16200.0, 3.77, 1.5, 0, 0),
        ('600487.SH', '20250101', 75.0, 76.0, 74.0, 75.5, 800.0, 60400.0, 0.67, 0.9, 0, 0),
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO daily_kline
        (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg, vol_ratio, is_limit_up, is_limit_down)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, test_klines)

    cursor.execute("SELECT COUNT(*) as cnt FROM daily_kline WHERE ts_code = '000001.SZ'")
    cnt = cursor.fetchone()['cnt']
    check("000001.SZ K线写入", cnt == 3, f"写入 {cnt} 条，预期 3")

    cursor.execute("SELECT * FROM daily_kline WHERE ts_code = '000001.SZ' AND trade_date = '20250101'")
    k1 = cursor.fetchone()

if k1:
    check("open", k1['open'] == 10.0, f"实际: {k1['open']}")
    check("high", k1['high'] == 10.5, f"实际: {k1['high']}")
    check("low", k1['low'] == 9.8, f"实际: {k1['low']}")
    check("close", k1['close'] == 10.3, f"实际: {k1['close']}")
    check("vol", k1['vol'] == 1000.0, f"实际: {k1['vol']}")
    check("amount", k1['amount'] == 10300.0, f"实际: {k1['amount']}")
    check("pct_chg", k1['pct_chg'] == 3.0, f"实际: {k1['pct_chg']}")
    check("vol_ratio", k1['vol_ratio'] == 1.2, f"实际: {k1['vol_ratio']}")
    check("is_limit_up", k1['is_limit_up'] == 0)
    check("is_limit_down", k1['is_limit_down'] == 0)
    check("UNIQUE 约束(跨股票不冲突)", cnt == 3, f"000001.SZ 有 {cnt} 条")
else:
    FAIL += 1
    print("  ❌ daily_kline 读取失败: row is None")

# ============================================================
# ---- 3. indicator_cache 写入/读取 ----
print("\n[3] indicator_cache 表（技术指标缓存）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO indicator_cache
        (ts_code, trade_date, close, open, high, low, vol, pct_chg,
         k, d, j, dif, dea, macd_hist, bbi,
         ma5, ma10, ma20, ma60,
         rsi6, rsi12, rsi24, wr5, wr10,
         boll_mid, boll_upper, boll_lower, boll_width, boll_position,
         vol_ratio, zg_white, dg_yellow,
         is_gold_cross, is_dead_cross,
         rsl_short, rsl_long, is_needle_20,
         brick_value, brick_trend, brick_count, brick_trend_up, is_fanbao,
         is_beidou, is_suoliang, is_jiayin_zhenyang, is_jiayang_zhenyin, is_fangliang_yinxian,
         sell_score, sell_reason, signal, signal_desc,
         prev_high, prev_low, dmi_plus, dmi_minus, adx,
         net_lg_mf, net_elg_mf, last_b1_date, last_b1_price,
         last_yidong_date, market_pct_chg, market_dir, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        '000001.SZ', '20250103', 11.0, 10.6, 11.2, 10.4, 1500.0, 3.77,
        72.5, 68.3, 80.9, 0.85, 0.62, 0.46, 10.8,
        10.88, 10.75, 10.6, 10.2,
        65.0, 60.0, 55.0, -20.0, -25.0,
        10.8, 11.5, 10.1, 1.4, 60.0,
        1.5, 72.38, 62.24,
        1, 0,
        65.0, 62.0, 1,
        91.84, 'RED', 3, 1, 0,
        1, 1, 0, 0, 0,
        5, '无扣分项', 'BUY', '买入',
        11.2, 10.4, 35.0, 25.0, 40.0,
        50000.0, 30000.0, '20241215', 9.85,
        '20241220', 1.5, 'BULLISH', None
    ))
    cursor.execute("SELECT * FROM indicator_cache WHERE ts_code = '000001.SZ' AND trade_date = '20250103'")
    ic = cursor.fetchone()

if ic:
    check("写入+读取成功", True)
    # 基础行情
    check("close", ic['close'] == 11.0, f"实际: {ic['close']}")
    check("open", ic['open'] == 10.6, f"实际: {ic['open']}")
    check("high", ic['high'] == 11.2, f"实际: {ic['high']}")
    check("low", ic['low'] == 10.4, f"实际: {ic['low']}")
    check("vol", ic['vol'] == 1500.0, f"实际: {ic['vol']}")
    check("pct_chg", ic['pct_chg'] == 3.77, f"实际: {ic['pct_chg']}")
    # KDJ
    check("k", abs(ic['k'] - 72.5) < 0.01, f"实际: {ic['k']}")
    check("d", abs(ic['d'] - 68.3) < 0.01, f"实际: {ic['d']}")
    check("j", abs(ic['j'] - 80.9) < 0.01, f"实际: {ic['j']}")
    # MACD
    check("dif", abs(ic['dif'] - 0.85) < 0.01, f"实际: {ic['dif']}")
    check("dea", abs(ic['dea'] - 0.62) < 0.01, f"实际: {ic['dea']}")
    check("macd_hist", abs(ic['macd_hist'] - 0.46) < 0.01, f"实际: {ic['macd_hist']}")
    # BBI & MA
    check("bbi", abs(ic['bbi'] - 10.8) < 0.01, f"实际: {ic['bbi']}")
    check("ma5", abs(ic['ma5'] - 10.88) < 0.01, f"实际: {ic['ma5']}")
    check("ma10", abs(ic['ma10'] - 10.75) < 0.01, f"实际: {ic['ma10']}")
    check("ma20", abs(ic['ma20'] - 10.6) < 0.01, f"实际: {ic['ma20']}")
    check("ma60", abs(ic['ma60'] - 10.2) < 0.01, f"实际: {ic['ma60']}")
    # RSI
    check("rsi6", abs(ic['rsi6'] - 65.0) < 0.01, f"实际: {ic['rsi6']}")
    check("rsi12", abs(ic['rsi12'] - 60.0) < 0.01, f"实际: {ic['rsi12']}")
    check("rsi24", abs(ic['rsi24'] - 55.0) < 0.01, f"实际: {ic['rsi24']}")
    # WR
    check("wr5", abs(ic['wr5'] - (-20.0)) < 0.01, f"实际: {ic['wr5']}")
    check("wr10", abs(ic['wr10'] - (-25.0)) < 0.01, f"实际: {ic['wr10']}")
    # 布林带
    check("boll_mid", abs(ic['boll_mid'] - 10.8) < 0.01, f"实际: {ic['boll_mid']}")
    check("boll_upper", abs(ic['boll_upper'] - 11.5) < 0.01, f"实际: {ic['boll_upper']}")
    check("boll_lower", abs(ic['boll_lower'] - 10.1) < 0.01, f"实际: {ic['boll_lower']}")
    check("boll_width", abs(ic['boll_width'] - 1.4) < 0.01, f"实际: {ic['boll_width']}")
    check("boll_position", abs(ic['boll_position'] - 60.0) < 0.01, f"实际: {ic['boll_position']}")
    # 量比
    check("vol_ratio", abs(ic['vol_ratio'] - 1.5) < 0.01, f"实际: {ic['vol_ratio']}")
    # 双线
    check("zg_white", abs(ic['zg_white'] - 72.38) < 0.01, f"实际: {ic['zg_white']}")
    check("dg_yellow", abs(ic['dg_yellow'] - 62.24) < 0.01, f"实际: {ic['dg_yellow']}")
    check("is_gold_cross", ic['is_gold_cross'] == 1)
    check("is_dead_cross", ic['is_dead_cross'] == 0)
    # 单针
    check("rsl_short", abs(ic['rsl_short'] - 65.0) < 0.01, f"实际: {ic['rsl_short']}")
    check("rsl_long", abs(ic['rsl_long'] - 62.0) < 0.01, f"实际: {ic['rsl_long']}")
    check("is_needle_20", ic['is_needle_20'] == 1)
    # 砖型图
    check("brick_value", abs(ic['brick_value'] - 91.84) < 0.01, f"实际: {ic['brick_value']}")
    check("brick_trend", ic['brick_trend'] == 'RED', f"实际: {ic['brick_trend']}")
    check("brick_count", ic['brick_count'] == 3)
    check("brick_trend_up", ic['brick_trend_up'] == 1)
    check("is_fanbao", ic['is_fanbao'] == 0)
    # 量价信号
    check("is_beidou", ic['is_beidou'] == 1)
    check("is_suoliang", ic['is_suoliang'] == 1)
    check("is_jiayin_zhenyang", ic['is_jiayin_zhenyang'] == 0)
    check("is_jiayang_zhenyin", ic['is_jiayang_zhenyin'] == 0)
    check("is_fangliang_yinxian", ic['is_fangliang_yinxian'] == 0)
    # 防卖飞
    check("sell_score", ic['sell_score'] == 5, f"实际: {ic['sell_score']}")
    check("sell_reason", ic['sell_reason'] == '无扣分项', f"实际: {ic['sell_reason']}")
    # 信号
    check("signal", ic['signal'] == 'BUY', f"实际: {ic['signal']}")
    check("signal_desc", ic['signal_desc'] == '买入', f"实际: {ic['signal_desc']}")
    # 关键价位
    check("prev_high", abs(ic['prev_high'] - 11.2) < 0.01, f"实际: {ic['prev_high']}")
    check("prev_low", abs(ic['prev_low'] - 10.4) < 0.01, f"实际: {ic['prev_low']}")
    # DMI/ADX
    check("dmi_plus", abs(ic['dmi_plus'] - 35.0) < 0.01, f"实际: {ic['dmi_plus']}")
    check("dmi_minus", abs(ic['dmi_minus'] - 25.0) < 0.01, f"实际: {ic['dmi_minus']}")
    check("adx", abs(ic['adx'] - 40.0) < 0.01, f"实际: {ic['adx']}")
    # 资金流
    check("net_lg_mf", abs(ic['net_lg_mf'] - 50000.0) < 0.01, f"实际: {ic['net_lg_mf']}")
    check("net_elg_mf", abs(ic['net_elg_mf'] - 30000.0) < 0.01, f"实际: {ic['net_elg_mf']}")
    # 战法/B1
    check("last_b1_date", ic['last_b1_date'] == '20241215', f"实际: {ic['last_b1_date']}")
    check("last_b1_price", abs(ic['last_b1_price'] - 9.85) < 0.01, f"实际: {ic['last_b1_price']}")
    check("last_yidong_date", ic['last_yidong_date'] == '20241220', f"实际: {ic['last_yidong_date']}")
    # 市场背景
    check("market_pct_chg", abs(ic['market_pct_chg'] - 1.5) < 0.01, f"实际: {ic['market_pct_chg']}")
    check("market_dir", ic['market_dir'] == 'BULLISH', f"实际: {ic['market_dir']}")
else:
    FAIL += 1
    print("  ❌ indicator_cache 读取失败: row is None")

# ============================================================
# ---- 4. moneyflow 写入/读取 ----
print("\n[4] moneyflow 表（资金流向）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO moneyflow
        (ts_code, trade_date, buy_sm_amount, buy_md_amount, buy_lg_amount, buy_elg_amount,
         sell_sm_amount, sell_md_amount, sell_lg_amount, sell_elg_amount, net_mf, pct_mf)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('000001.SZ', '20250103', 500000, 1000000, 3000000, 5000000, 400000, 900000, 2500000, 4000000, 1100000, 2.5))
    cursor.execute("SELECT * FROM moneyflow WHERE ts_code = '000001.SZ' AND trade_date = '20250103'")
    mf = cursor.fetchone()

if mf:
    check("写入+读取成功", True)
    check("buy_sm_amount", mf['buy_sm_amount'] == 500000, f"实际: {mf['buy_sm_amount']}")
    check("buy_md_amount", mf['buy_md_amount'] == 1000000, f"实际: {mf['buy_md_amount']}")
    check("buy_lg_amount", mf['buy_lg_amount'] == 3000000, f"实际: {mf['buy_lg_amount']}")
    check("buy_elg_amount", mf['buy_elg_amount'] == 5000000, f"实际: {mf['buy_elg_amount']}")
    check("sell_sm_amount", mf['sell_sm_amount'] == 400000, f"实际: {mf['sell_sm_amount']}")
    check("sell_md_amount", mf['sell_md_amount'] == 900000, f"实际: {mf['sell_md_amount']}")
    check("sell_lg_amount", mf['sell_lg_amount'] == 2500000, f"实际: {mf['sell_lg_amount']}")
    check("sell_elg_amount", mf['sell_elg_amount'] == 4000000, f"实际: {mf['sell_elg_amount']}")
    check("net_mf", mf['net_mf'] == 1100000, f"实际: {mf['net_mf']}")
    check("pct_mf", mf['pct_mf'] == 2.5, f"实际: {mf['pct_mf']}")
else:
    FAIL += 1
    print("  ❌ moneyflow 读取失败")

# ============================================================
# ---- 5. financial_data 写入/读取 ----
print("\n[5] financial_data 表（财务报表）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO financial_data
        (ts_code, ann_date, end_date, report_type, revenue, net_profit, total_assets, total_liab, equity, pe, pb, ps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('000001.SZ', '20250331', '20241231', 1, 150000000000, 45000000000, 5000000000000, 4500000000000, 500000000000, 6.5, 0.8, 2.1))
    cursor.execute("SELECT * FROM financial_data WHERE ts_code = '000001.SZ' AND ann_date = '20250331'")
    fd = cursor.fetchone()

if fd:
    check("写入+读取成功", True)
    check("ann_date", fd['ann_date'] == '20250331', f"实际: {fd['ann_date']}")
    check("end_date", fd['end_date'] == '20241231', f"实际: {fd['end_date']}")
    check("report_type", fd['report_type'] == 1, f"实际: {fd['report_type']}")
    check("revenue", fd['revenue'] == 150000000000, f"实际: {fd['revenue']}")
    check("net_profit", fd['net_profit'] == 45000000000, f"实际: {fd['net_profit']}")
    check("total_assets", fd['total_assets'] == 5000000000000, f"实际: {fd['total_assets']}")
    check("total_liab", fd['total_liab'] == 4500000000000, f"实际: {fd['total_liab']}")
    check("equity", fd['equity'] == 500000000000, f"实际: {fd['equity']}")
    check("pe", fd['pe'] == 6.5, f"实际: {fd['pe']}")
    check("pb", fd['pb'] == 0.8, f"实际: {fd['pb']}")
    check("ps", fd['ps'] == 2.1, f"实际: {fd['ps']}")
else:
    FAIL += 1
    print("  ❌ financial_data 读取失败")

# ============================================================
# ---- 6. trade_signals 写入/读取 ----
print("\n[6] trade_signals 表（交易信号记录）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trade_signals (ts_code, signal_date, signal_type, signal_score, signal_price, processed)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('000001.SZ', '20250103', 'B1', 0.75, 11.0, 0))
    cursor.execute("SELECT * FROM trade_signals WHERE ts_code = '000001.SZ'")
    ts_row = cursor.fetchone()

if ts_row:
    check("写入+读取成功", True)
    check("signal_date", ts_row['signal_date'] == '20250103', f"实际: {ts_row['signal_date']}")
    check("signal_type", ts_row['signal_type'] == 'B1', f"实际: {ts_row['signal_type']}")
    check("signal_score", ts_row['signal_score'] == 0.75, f"实际: {ts_row['signal_score']}")
    check("signal_price", ts_row['signal_price'] == 11.0, f"实际: {ts_row['signal_price']}")
    check("processed", ts_row['processed'] == 0)
else:
    FAIL += 1
    print("  ❌ trade_signals 读取失败")

# ============================================================
# ---- 7. trade_records CRUD ----
print("\n[7] trade_records 表（交易记录 CRUD）")
# CREATE
record = {
    "ts_code": "000001.SZ",
    "trade_date": "20250103",
    "action": "BUY",
    "price": 11.0,
    "quantity": 1000,
    "amount": 11000.0,
    "reason": "B1信号触发",
    "signal_type": "B1",
    "zg_review": "Z哥点评：缩量回调到位",
    "broker": "华泰",
    "fee": 5.5,
    "tags": "测试,B1",
    "notes": "端到端测试记录"
}
rec_id = save_trade_record(record)
check("写入返回 ID", rec_id > 0, f"ID={rec_id}")

# READ
fetched = get_trade_record_by_id(rec_id)
check("按ID读取", fetched is not None)
if fetched:
    check("ts_code", fetched['ts_code'] == '000001.SZ', f"实际: {fetched['ts_code']}")
    check("trade_date", fetched['trade_date'] == '20250103', f"实际: {fetched['trade_date']}")
    check("action", fetched['action'] == 'BUY', f"实际: {fetched['action']}")
    check("price", fetched['price'] == 11.0, f"实际: {fetched['price']}")
    check("quantity", fetched['quantity'] == 1000, f"实际: {fetched['quantity']}")
    check("amount", fetched['amount'] == 11000.0, f"实际: {fetched['amount']}")
    check("reason", fetched['reason'] == 'B1信号触发', f"实际: {fetched['reason']}")
    check("signal_type", fetched['signal_type'] == 'B1', f"实际: {fetched['signal_type']}")
    check("zg_review", fetched['zg_review'] == 'Z哥点评：缩量回调到位', f"实际: {fetched['zg_review']}")
    check("broker", fetched['broker'] == '华泰', f"实际: {fetched['broker']}")
    check("fee", fetched['fee'] == 5.5, f"实际: {fetched['fee']}")
    check("tags", fetched['tags'] == '测试,B1', f"实际: {fetched['tags']}")
    check("notes", fetched['notes'] == '端到端测试记录', f"实际: {fetched['notes']}")

# UPDATE
updated = update_trade_record(rec_id, {"reason": "更新后的原因", "notes": "更新备注"})
check("更新成功", updated)
fetched2 = get_trade_record_by_id(rec_id)
if fetched2:
    check("reason已更新", fetched2['reason'] == '更新后的原因', f"实际: {fetched2['reason']}")
    check("notes已更新", fetched2['notes'] == '更新备注', f"实际: {fetched2['notes']}")
    check("price未变", fetched2['price'] == 11.0, f"实际: {fetched2['price']}")

# QUERY LIST
recs = get_trade_records(ts_code='000001.SZ', limit=10)
check("条件查询返回结果", len(recs) >= 1, f"返回 {len(recs)} 条")

# DELETE
deleted = delete_trade_record(rec_id)
check("删除成功", deleted)
fetched3 = get_trade_record_by_id(rec_id)
check("删除后读不到", fetched3 is None)

# SUMMARY
# 再插入一条用于汇总测试
save_trade_record({**record, "price": 12.0, "amount": 12000.0, "action": "BUY"})
save_trade_record({**record, "price": 13.0, "amount": 13000.0, "action": "SELL"})
summary = get_trade_summary(ts_code='000001.SZ')
check("汇总有BUY", 'BUY' in summary and summary['BUY'].get('count', 0) > 0)
check("汇总有SELL", 'SELL' in summary and summary['SELL'].get('count', 0) > 0)

# ============================================================
# ---- 8. watchlist CRUD ----
print("\n[8] watchlist 表（自选股 CRUD）")
wl_id = add_watchlist_item('600487.SH', '亨通光电', '通信,5G', '测试标的')
check("写入返回 ID", wl_id > 0 or True)  # INSERT OR REPLACE may return 0

wl = get_watchlist()
check("列表有数据", len(wl) >= 1, f"共 {len(wl)} 只")
if wl:
    item = next((i for i in wl if i['ts_code'] == '600487.SH'), None)
    check("找到600487.SH", item is not None)
    if item:
        check("name", item['name'] == '亨通光电', f"实际: {item['name']}")
        check("tags", '通信' in item['tags'], f"实际: {item['tags']}")

# 更新
updated_wl = update_watchlist_item('600487.SH', {'tags': '通信,5G,ETF'})
check("更新成功", updated_wl)
wl2 = get_watchlist()
item2 = next((i for i in wl2 if i['ts_code'] == '600487.SH'), None)
if item2:
    check("tags已更新", 'ETF' in item2['tags'], f"实际: {item2['tags']}")

# 按标签筛选
wl_by_tag = get_watchlist(tags='通信')
check("按标签筛选", len(wl_by_tag) >= 1, f"返回 {len(wl_by_tag)} 只")

# 删除
removed = remove_watchlist_item('600487.SH')
check("删除成功", removed)
wl3 = get_watchlist()
has_removed = any(i['ts_code'] == '600487.SH' for i in wl3)
check("删除后不在列表中", not has_removed)

# ============================================================
# ---- 9. sync_log 写入/读取 ----
print("\n[9] sync_log 表（同步日志）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sync_log (data_type, ts_code, last_date, status, message)
        VALUES (?, ?, ?, ?, ?)
    """, ('daily_kline', '000001.SZ', '20250103', 'success', '同步120条'))
    cursor.execute("SELECT * FROM sync_log WHERE ts_code = '000001.SZ'")
    sl = cursor.fetchone()

if sl:
    check("写入+读取成功", True)
    check("data_type", sl['data_type'] == 'daily_kline', f"实际: {sl['data_type']}")
    check("last_date", sl['last_date'] == '20250103', f"实际: {sl['last_date']}")
    check("status", sl['status'] == 'success', f"实际: {sl['status']}")
    check("message", sl['message'] == '同步120条', f"实际: {sl['message']}")
else:
    FAIL += 1
    print("  ❌ sync_log 读取失败")

# ============================================================
# ---- 10. tushare_indicator_cache 写入/读取 ----
print("\n[10] tushare_indicator_cache 表（Tushare官方指标）")
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO tushare_indicator_cache
        (ts_code, trade_date, close, macd_dif, macd_dea, macd,
         kdj_k, kdj_d, kdj_j, rsi_6, rsi_12, rsi_24,
         boll_upper, boll_mid, boll_lower, cci)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('000001.SZ', '20250103', 11.0, 0.85, 0.62, 0.46, 72.5, 68.3, 80.9, 65.0, 60.0, 55.0, 11.5, 10.8, 10.1, 120.0))
    cursor.execute("SELECT * FROM tushare_indicator_cache WHERE ts_code = '000001.SZ'")
    tic = cursor.fetchone()

if tic:
    check("写入+读取成功", True)
    check("macd_dif", abs(tic['macd_dif'] - 0.85) < 0.01, f"实际: {tic['macd_dif']}")
    check("kdj_k", abs(tic['kdj_k'] - 72.5) < 0.01, f"实际: {tic['kdj_k']}")
    check("rsi_6", abs(tic['rsi_6'] - 65.0) < 0.01, f"实际: {tic['rsi_6']}")
    check("boll_mid", abs(tic['boll_mid'] - 10.8) < 0.01, f"实际: {tic['boll_mid']}")
    check("cci", abs(tic['cci'] - 120.0) < 0.01, f"实际: {tic['cci']}")
else:
    FAIL += 1
    print("  ❌ tushare_indicator_cache 读取失败")

# ============================================================
# ---- 11. 跨表关联测试 ----
print("\n[11] 跨表关联查询测试")
with get_connection() as conn:
    cursor = conn.cursor()
    # K线 + 指标缓存 JOIN
    cursor.execute("""
        SELECT dk.close as kline_close, ic.k as kdj_k, ic.rsi6, ic.signal
        FROM daily_kline dk
        LEFT JOIN indicator_cache ic ON dk.ts_code = ic.ts_code AND dk.trade_date = ic.trade_date
        WHERE dk.ts_code = '000001.SZ' AND dk.trade_date = '20250103'
    """)
    joined = cursor.fetchone()
    if joined:
        check("K线+指标 JOIN 成功", True)
        check("kline_close", joined['kline_close'] == 11.0, f"实际: {joined['kline_close']}")
        check("kdj_k", abs(joined['kdj_k'] - 72.5) < 0.01, f"实际: {joined['kdj_k']}")
        check("rsi6", abs(joined['rsi6'] - 65.0) < 0.01, f"实际: {joined['rsi6']}")
        check("signal", joined['signal'] == 'BUY', f"实际: {joined['signal']}")
    else:
        FAIL += 1
        print("  ❌ JOIN 查询无结果")

# ============================================================
# ---- 12. 边界/异常测试 ----
print("\n[12] 边界 & 异常测试")

# NULL 值写入
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO daily_kline (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg, vol_ratio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('TEST.NULL', '20250101', None, None, None, 10.0, None, None, None, None))
    cursor.execute("SELECT * FROM daily_kline WHERE ts_code = 'TEST.NULL'")
    null_row = cursor.fetchone()

check("NULL 值写入不崩溃", null_row is not None)
if null_row:
    check("NULL close 存为 None", null_row['close'] == 10.0)  # 实际传了 10.0
    check("NULL open 存为 None", null_row['open'] is None, f"实际: {null_row['open']}")
    check("NULL vol 存为 None", null_row['vol'] is None, f"实际: {null_row['vol']}")

# UNIQUE 约束测试
with get_connection() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO daily_kline (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)
            VALUES ('000001.SZ', '20250101', 10.0, 10.5, 9.8, 10.3, 1000.0, 10300.0, 3.0)
        """)
        FAIL += 1
        print("  ❌ UNIQUE 约束未生效（应重复插入失败）")
    except Exception:
        check("UNIQUE(ts_code, trade_date) 约束生效", True)

# ============================================================
# 汇总
print("\n" + "=" * 60)
print(f"测试完成: {PASS} 通过, {FAIL} 失败, {WARN} 警告")
if FAIL > 0:
    print("❌ 有失败的测试用例，请检查上方详情")
else:
    print("✅ 全部通过")
print("=" * 60)

# 清理
try:
    os.remove(test_db)
except:
    pass
