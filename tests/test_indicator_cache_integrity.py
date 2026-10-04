"""
指标缓存完整性与正确性校验

校验批量指标同步（``zt sync sync --indicators``）产出的数据是否「跑完且正确」。
对应排查记录见 ``docs/TODO.md`` P0（SQLite 写锁导致约 12% 股票漏算）。

三个层次，缺一不可：

1. **完整性** —— 全市场股票是否都有缓存、每只条数是否符合窗口
   （只查数量会掩盖「算错但写满了」）
2. **值域合法性** —— RSI 是否在 0-100、BOLL 三轨是否有序、关键字段是否为空
   （只查值域会掩盖「算错但仍在合法区间」）
3. **正确性** —— 两条独立路径交叉验证：
   - 列映射：用同一实现重算，逐字段比对缓存值（防列错位/截断）
   - 独立算法：用与实现无关的定义重算 MA5/收盘价，验证语义而非自证

关于算法本身的正确性（KDJ/MACD 口径）由 ``test_indicators.py`` 与
``test_indicators_realdata.py``（与 Tushare 官方 stk_factor 对拍）覆盖，
本文件不重复。

分层执行：
- 默认跑：合成数据，校验同步链路 → CI 可跑、无需外部依赖
- realdata：生产库全量校验，需 ``RUN_REALDATA=true``
"""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ==================== 常量 ====================

SYNC_DAYS = 120
SEED_STOCKS = 6  # 合成数据规模（够触发并发写锁，又不拖慢 CI）
PROD_DB = Path(__file__).parent.parent / "data" / "stock_data.db"

# 参与逐字段比对的字段（覆盖各主要计算分支）
COMPARE_FIELDS = [
    "close",
    "j",
    "k",
    "d",
    "dif",
    "dea",
    "macd_hist",
    "bbi",
    "ma5",
    "ma10",
    "ma20",
    "rsi6",
    "rsi12",
    "rsi24",
    "boll_mid",
    "boll_upper",
    "boll_lower",
    "vol_ratio",
]

_RUN_REALDATA = os.environ.get("RUN_REALDATA", "").lower() == "true"


# ==================== 辅助函数 ====================


def _seed_klines(conn, ts_code, n=SYNC_DAYS, start_price=10.0):
    """写入波动的合成 K 线（正弦 + 微趋势），保证各指标可算出非平凡值"""
    rows = []
    dt = datetime(2025, 1, 2)
    for i in range(n):
        price = start_price + 2.0 * (i % 17) / 17.0 + i * 0.01
        rows.append(
            (
                ts_code,
                dt.strftime("%Y%m%d"),
                round(price, 2),  # open
                round(price * 1.02, 2),  # high
                round(price * 0.98, 2),  # low
                round(price, 2),  # close
                100000.0 + i * 100,  # vol
                price * 100000,  # amount
                round((i % 7) - 3, 3),  # pct_chg
                0,  # is_limit_up
                0,  # is_limit_down
            )
        )
        dt += timedelta(days=1)
    conn.executemany(
        """INSERT OR REPLACE INTO daily_kline
           (ts_code, trade_date, open, high, low, close, vol, amount,
            pct_chg, is_limit_up, is_limit_down)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()


def _recompute_last_day(ts_code):
    """独立重算某只股票最后一天的指标，返回字段 dict。

    走与批量同步相同的实现，用于验证「列映射正确、写入无错位」。
    """
    from modules.data_sync.syncer import (
        _INDICATOR_INSERT_COLUMNS,
        _build_indicator_row,
        _compute_day_indicators,
        _get_indicator_funcs,
    )

    f = _get_indicator_funcs()
    klines = f.get_kline_data(ts_code, SYNC_DAYS)
    if not klines:
        return None, None

    kdj = f.precompute_kdj_sequence(klines) if len(klines) >= 9 else None
    if len(klines) >= 30:
        dif_seq, dea_seq, hist_seq = f.precompute_macd_sequence(klines)
    else:
        dif_seq = dea_seq = hist_seq = None

    i = len(klines) - 1
    sub = klines[: i + 1]
    prev = sub[-2] if len(sub) > 1 else None
    ind = _compute_day_indicators(f, sub, klines[i], prev, kdj, dif_seq, dea_seq, hist_seq, i)
    row = _build_indicator_row(ts_code, klines[i].trade_date, ind)

    cols = [c.strip() for c in _INDICATOR_INSERT_COLUMNS.split(",") if c.strip()]
    return dict(zip(cols, row)), klines[i].trade_date


# ==================== Fixtures ====================


@pytest.fixture
def seeded_db(db_conn):
    """临时库灌入合成 K 线并执行指标同步，返回已同步的股票代码列表"""
    from modules.data_sync import DataSyncer
    from modules.datasource import get_datasource

    codes = [f"{600000 + i}.SH" for i in range(SEED_STOCKS)]
    for c in codes:
        _seed_klines(db_conn, c)

    syncer = DataSyncer(datasource=get_datasource("tushare"))
    for c in codes:
        syncer.sync_indicator_cache(c, days=SYNC_DAYS)

    return codes


# ==================== 1. 完整性 ====================


class TestIndicatorCacheCompleteness:
    """批量同步是否「跑完」：覆盖度与条数"""

    def test_all_seeded_stocks_have_cache(self, db_conn, seeded_db):
        """每只同步过的股票都应有指标缓存（漏算会在此暴露）"""
        have = {r[0] for r in db_conn.execute("SELECT DISTINCT ts_code FROM indicator_cache")}
        missing = [c for c in seeded_db if c not in have]
        assert not missing, f"以下股票同步后无指标缓存: {missing}"

    def test_row_count_matches_window(self, db_conn, seeded_db):
        """每只股票的缓存条数应等于同步窗口天数"""
        for code in seeded_db:
            n = db_conn.execute("SELECT COUNT(*) FROM indicator_cache WHERE ts_code=?", (code,)).fetchone()[0]
            assert n == SYNC_DAYS, f"{code} 缓存 {n} 条，期望 {SYNC_DAYS} 条"

    def test_no_duplicate_rows(self, db_conn, seeded_db):
        """同一 (ts_code, trade_date) 不应重复（复合主键已约束，此处防回归）"""
        dup = db_conn.execute(
            """SELECT ts_code, trade_date, COUNT(*) c FROM indicator_cache
               GROUP BY ts_code, trade_date HAVING c > 1"""
        ).fetchall()
        assert not dup, f"存在重复行: {dup[:5]}"


# ==================== 2. 值域合法性 ====================


class TestIndicatorCacheValueRange:
    """算出的值是否在合法区间（能抓出 NaN、越界、倒挂）"""

    @pytest.mark.parametrize("field", ["rsi6", "rsi12", "rsi24"])
    def test_rsi_within_bounds(self, db_conn, seeded_db, field):
        """RSI 必须落在 0-100"""
        bad = db_conn.execute(
            f"SELECT ts_code, trade_date, {field} FROM indicator_cache "
            f"WHERE {field} IS NOT NULL AND ({field} < 0 OR {field} > 100)"
        ).fetchall()
        assert not bad, f"{field} 越界: {bad[:5]}"

    def test_bollinger_bands_ordered(self, db_conn, seeded_db):
        """BOLL 上轨 >= 中轨 >= 下轨"""
        bad = db_conn.execute(
            """SELECT ts_code, trade_date, boll_upper, boll_mid, boll_lower
               FROM indicator_cache
               WHERE boll_upper < boll_mid OR boll_mid < boll_lower"""
        ).fetchall()
        assert not bad, f"BOLL 三轨倒挂: {bad[:5]}"

    @pytest.mark.parametrize("field", ["close", "j", "dif", "bbi", "ma5"])
    def test_key_fields_not_null(self, db_conn, seeded_db, field):
        """关键指标字段不应为 NULL（窗口内应有足够数据算出）"""
        nulls = db_conn.execute(f"SELECT COUNT(*) FROM indicator_cache WHERE {field} IS NULL").fetchone()[0]
        assert nulls == 0, f"{field} 有 {nulls} 行为 NULL"

    def test_no_nan_or_inf(self, db_conn, seeded_db):
        """不应出现 NaN/Inf（SQLite 会存为 NULL 或极大值，需显式拦截）"""
        import math

        rows = db_conn.execute("SELECT ts_code, trade_date, j, dif, rsi6, bbi FROM indicator_cache").fetchall()
        bad = []
        for r in rows:
            for v in r[2:]:
                if v is not None and (math.isnan(v) or math.isinf(v)):
                    bad.append((r[0], r[1]))
                    break
        assert not bad, f"存在 NaN/Inf: {bad[:5]}"


# ==================== 3. 正确性 ====================


class TestIndicatorCacheCorrectness:
    """值是否「算对」：列映射一致性 + 独立算法验证"""

    def test_recompute_matches_cache(self, db_conn, seeded_db):
        """列映射一致性：独立重算的最后一天应与缓存逐字段相同。

        能抓出列顺序错位、字段截断、并发写入串数据等问题。
        """
        mismatches = []
        compared = 0
        for code in seeded_db:
            recomputed, trade_date = _recompute_last_day(code)
            if recomputed is None:
                continue

            cached = db_conn.execute(
                "SELECT * FROM indicator_cache WHERE ts_code=? AND trade_date=?",
                (code, trade_date),
            ).fetchone()
            assert cached is not None, f"{code} {trade_date} 无缓存"

            cols = [d[0] for d in db_conn.execute("SELECT * FROM indicator_cache LIMIT 1").description]
            cached_map = dict(zip(cols, cached))

            for fld in COMPARE_FIELDS:
                if fld not in recomputed:
                    continue
                a, b = cached_map.get(fld), recomputed.get(fld)
                compared += 1
                if a is None and b is None:
                    continue
                if (a is None) != (b is None):
                    mismatches.append(f"{code} {trade_date} {fld}: 缓存={a} 重算={b}")
                elif a is not None and abs(float(a) - float(b)) > 1e-6:
                    mismatches.append(f"{code} {trade_date} {fld}: 缓存={a} 重算={b}")

        assert compared > 0, "未比对任何字段，测试数据可能不正常"
        assert not mismatches, f"共 {compared} 个字段中 {len(mismatches)} 个不一致:\n" + "\n".join(mismatches[:10])

    def test_ma5_matches_independent_calculation(self, db_conn, seeded_db):
        """独立算法验证：MA5 必须等于最近 5 个交易日收盘价均值。

        不依赖被测实现，用定义直接算 —— 能抓出实现层面的语义错误。
        """
        for code in seeded_db:
            rows = db_conn.execute(
                """SELECT c.trade_date, c.ma5, k.close
                   FROM indicator_cache c
                   JOIN daily_kline k ON k.ts_code = c.ts_code AND k.trade_date = c.trade_date
                   WHERE c.ts_code = ? ORDER BY c.trade_date""",
                (code,),
            ).fetchall()
            assert len(rows) >= 5, f"{code} 数据不足 5 天"

            for idx in range(4, len(rows)):
                window = [r[2] for r in rows[idx - 4 : idx + 1]]
                expected = sum(window) / 5.0
                actual = rows[idx][1]
                assert actual is not None, f"{code} {rows[idx][0]} ma5 为 NULL"
                assert abs(actual - expected) < 1e-4, f"{code} {rows[idx][0]} ma5={actual}，独立计算={expected:.6f}"

    def test_close_matches_kline(self, db_conn, seeded_db):
        """缓存的 close 必须与 daily_kline 的 close 一致（防数据源错位）"""
        bad = db_conn.execute(
            """SELECT c.ts_code, c.trade_date, c.close, k.close
               FROM indicator_cache c
               JOIN daily_kline k ON k.ts_code = c.ts_code AND k.trade_date = c.trade_date
               WHERE abs(c.close - k.close) > 1e-6"""
        ).fetchall()
        assert not bad, f"close 与 K 线不一致: {bad[:5]}"

    # ---- 数学恒等式：不依赖被测实现，可抓出「实现层算错」 ----
    # 说明：test_recompute_matches_cache 用的是同一实现重算，若缺陷出在
    # _build_indicator_row / _compute_day_indicators，两边会同步出错形成
    # 自证循环（已用变异测试验证：注入 j+1 后该用例仍通过）。
    # 因此必须用与实现无关的定义式来兜底。

    def test_kdj_identity_j_equals_3k_minus_2d(self, db_conn, seeded_db):
        """KDJ 定义式：J = 3K - 2D

        容差 0.03：k/d/j 各自 round(2) 后落库，舍入误差上限约
        3*0.005 + 2*0.005 = 0.025，实测全量最大偏差 0.02。
        """
        bad = db_conn.execute(
            """SELECT ts_code, trade_date, k, d, j FROM indicator_cache
               WHERE k IS NOT NULL AND d IS NOT NULL AND j IS NOT NULL
                 AND abs(j - (3 * k - 2 * d)) > 0.03"""
        ).fetchall()
        assert not bad, f"J≠3K-2D: {bad[:5]}"

    def test_macd_identity_hist_equals_2x_dif_minus_dea(self, db_conn, seeded_db):
        """MACD 定义式：MACD 柱 = 2 × (DIF - DEA)

        本项目采用 A 股常用口径（柱 = 2 倍差），非 dif-dea。
        实测全量 662,401 行该恒等式 0 违反，而 dif-dea 口径 77% 违反。
        """
        bad = db_conn.execute(
            """SELECT ts_code, trade_date, dif, dea, macd_hist FROM indicator_cache
               WHERE dif IS NOT NULL AND dea IS NOT NULL AND macd_hist IS NOT NULL
                 AND abs(macd_hist - 2 * (dif - dea)) > 0.001"""
        ).fetchall()
        assert not bad, f"MACD 柱 ≠ 2×(DIF-DEA): {bad[:5]}"

    def test_bollinger_identity_mid_is_bands_mean(self, db_conn, seeded_db):
        """BOLL 定义式：中轨 = (上轨 + 下轨) / 2"""
        bad = db_conn.execute(
            """SELECT ts_code, trade_date, boll_upper, boll_mid, boll_lower
               FROM indicator_cache
               WHERE boll_upper IS NOT NULL AND boll_lower IS NOT NULL
                 AND boll_mid IS NOT NULL
                 AND abs(boll_mid - (boll_upper + boll_lower) / 2.0) > 0.03"""
        ).fetchall()
        assert not bad, f"BOLL 中轨 ≠ (上轨+下轨)/2: {bad[:5]}"


# ==================== 生产库全量校验（realdata） ====================


@pytest.fixture(scope="module")
def prod_conn():
    """生产库只读连接（module 级，避免每个用例重连）"""
    conn = sqlite3.connect(PROD_DB)
    conn.execute("PRAGMA busy_timeout=30000;")
    yield conn
    conn.close()


@pytest.mark.realdata
@pytest.mark.slow
@pytest.mark.skipif(
    not (_RUN_REALDATA and PROD_DB.exists()),
    reason=f"需设置 RUN_REALDATA=true 且生产库存在（{PROD_DB}）",
)
class TestProductionCacheIntegrity:
    """生产库全量校验：5562 只是否都算完且合法

    对应人工排查结论（docs/TODO.md P0）：修复前约 582 只因写锁漏算。
    """

    def test_all_stocks_covered(self, prod_conn):
        """stock_basic 全市场股票都应已有指标缓存"""
        missing = prod_conn.execute(
            """SELECT COUNT(*) FROM stock_basic s
               WHERE NOT EXISTS (
                   SELECT 1 FROM indicator_cache c WHERE c.ts_code = s.ts_code)"""
        ).fetchone()[0]
        assert missing == 0, f"仍有 {missing} 只股票缺指标缓存"

    def test_no_empty_cache(self, prod_conn):
        """不应存在只有 0 行的股票记录"""
        empty = prod_conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT ts_code FROM indicator_cache GROUP BY ts_code HAVING COUNT(*) = 0)"""
        ).fetchone()[0]
        assert empty == 0

    def test_rsi_bounds_production(self, prod_conn):
        """全量数据 RSI 均在 0-100"""
        for field in ("rsi6", "rsi12", "rsi24"):
            bad = prod_conn.execute(
                f"SELECT COUNT(*) FROM indicator_cache WHERE {field} IS NOT NULL AND ({field} < 0 OR {field} > 100)"
            ).fetchone()[0]
            assert bad == 0, f"{field} 越界 {bad} 行"

    def test_bollinger_ordered_production(self, prod_conn):
        """全量数据 BOLL 三轨有序"""
        bad = prod_conn.execute(
            """SELECT COUNT(*) FROM indicator_cache
               WHERE boll_upper < boll_mid OR boll_mid < boll_lower"""
        ).fetchone()[0]
        assert bad == 0, f"BOLL 倒挂 {bad} 行"

    def test_cache_never_exceeds_kline(self, prod_conn):
        """不变量：指标缓存条数不得超过该股票 K 线条数

        （缓存由 K 线派生，条数必然 ≤ K 线）
        """
        bad = prod_conn.execute(
            """SELECT c.ts_code, COUNT(*) cache_n,
                      (SELECT COUNT(*) FROM daily_kline k WHERE k.ts_code = c.ts_code) kline_n
               FROM indicator_cache c
               GROUP BY c.ts_code HAVING cache_n > kline_n"""
        ).fetchall()
        assert not bad, f"缓存条数超过 K 线: {bad[:5]}"

    def test_typical_row_count_is_sync_window(self, prod_conn):
        """绝大多数股票应为同步窗口 120 条

        少数例外属历史遗留：早期手动同步用了不同窗口（如 600487.SH 为 485 条），
        以及上市不足 120 天的新股。此处只要求「典型值」占比 > 95%，
        避免把无害的历史数据判为失败。
        """
        total = prod_conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT ts_code FROM indicator_cache)").fetchone()[0]
        typical = prod_conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT ts_code FROM indicator_cache
                   GROUP BY ts_code HAVING COUNT(*) = ?)""",
            (SYNC_DAYS,),
        ).fetchone()[0]
        ratio = typical / total if total else 0
        assert ratio > 0.95, (
            f"仅 {ratio:.1%} 的股票为 {SYNC_DAYS} 条（{typical}/{total}），可能批量同步未跑完或窗口被改动"
        )

    @pytest.mark.parametrize(
        "name,expr,tol",
        [
            ("J=3K-2D", "abs(j - (3 * k - 2 * d))", 0.03),
            ("MACD柱=2*(DIF-DEA)", "abs(macd_hist - 2 * (dif - dea))", 0.001),
            ("BOLL中轨=(上+下)/2", "abs(boll_mid - (boll_upper + boll_lower) / 2.0)", 0.03),
        ],
    )
    def test_math_identities_production(self, prod_conn, name, expr, tol):
        """全量数据满足指标定义式（容差说明见合成数据同名用例）"""
        bad = prod_conn.execute(
            f"""SELECT COUNT(*) FROM indicator_cache
                WHERE k IS NOT NULL AND d IS NOT NULL AND j IS NOT NULL
                  AND dif IS NOT NULL AND dea IS NOT NULL AND macd_hist IS NOT NULL
                  AND boll_upper IS NOT NULL AND boll_lower IS NOT NULL
                  AND boll_mid IS NOT NULL
                  AND {expr} > {tol}"""
        ).fetchone()[0]
        assert bad == 0, f"恒等式 {name} 违反 {bad} 行"
