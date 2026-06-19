from typing import Any, Optional
from collections.abc import Callable

"""
技术指标数据层模块
"""

try:
    from .core import (
        DB_PATH,  # noqa: F401  可能被外部引用
        get_db_connection,
        DailyData,
        TradeSignal,
        IndicatorResult,
        calculate_ma,
        calculate_ema,  # noqa: F401  可能被外部引用
        calculate_kdj,
        calculate_bbi,
        calculate_rsi_multi,
        calculate_wr_multi,
        calculate_bollinger,
        calculate_vol_ratio,
        calculate_macd,
        get_data_mode,  # noqa: F401  可能被外部引用
    )
    from .price_patterns import (
        calculate_zg_white,
        calculate_dg_yellow,
        detect_double_line_cross,
        detect_needle_20,
        detect_needle_30,
        calculate_brick_value,
        calculate_brick_history,
        detect_brick_trend,
        detect_fanbao,
        detect_b1_today,
        detect_b2_today,
        detect_key_k,
        detect_violence_k,
        check_two_30_rule,
        detect_nana_chart,
        detect_golden_bowl,
        detect_breathing_structure,
        detect_sb1,
        detect_sb1_detailed,
        detect_b3,
        detect_double_gun,
        detect_four_brick_system,
        detect_volume_pattern,
        detect_macd_signals,
        calculate_dmi,
    )
    from .volume_patterns import (
        detect_volume_anomaly,
        calculate_sell_score,
        detect_trade_signal,
    )
except ImportError:
    # 已废弃：仅在直接运行 `python modules/indicators/data_layer.py` 时生效
    # 安装包后（pip install -e .）统一走相对导入，此分支不再需要
    raise ImportError(
        "请使用 'pip install -e .' 安装包后通过 'zt' 命令调用，或通过 'python -m modules.indicators.data_layer' 运行"
    )

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）

# 指标缓存层（内存 + SQLite）
_indicator_memory_cache: dict[tuple[str, str], IndicatorResult] = {}

# ==================== 字段映射注册表（v3.x 重构：统一 load/save/analyze 三处字段管理） ====================

# IndicatorResult 属性 <-> DB 列名的映射
# 新增字段只需在此添加一行，load/save 自动同步
_FLOAT_FIELDS: list[str] = [
    "k",
    "d",
    "j",
    "dif",
    "dea",
    "macd_hist",
    "bbi",
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "rsi6",
    "rsi12",
    "rsi24",
    "wr5",
    "wr10",
    "boll_mid",
    "boll_upper",
    "boll_lower",
    "boll_width",
    "boll_position",
    "vol_ratio",
    "zg_white",
    "dg_yellow",
    "rsl_short",
    "rsl_long",
    "brick_value",
    "brick_count",
    "prev_high",
    "prev_low",
    "dmi_plus",
    "dmi_minus",
    "adx",
    "net_lg_mf",
    "net_elg_mf",
    "last_b1_price",
]

_BOOL_FIELDS: list[str] = [
    "is_gold_cross",
    "is_dead_cross",
    "is_needle_20",
    "brick_trend_up",
    "is_fanbao",
    "is_beidou",
    "is_suoliang",
    "is_jiayin_zhenyang",
    "is_jiayang_zhenyin",
    "is_fangliang_yinxian",
]

_INT_FIELDS: list[str] = ["sell_score"]

_STR_FIELDS: list[str] = ["brick_trend", "last_b1_date"]


def _load_from_row(row) -> IndicatorResult:
    """从数据库行构建 IndicatorResult（统一字段映射，消除手工逐字段赋值）"""
    kw: dict = {
        "ts_code": row["ts_code"],
        "trade_date": row["trade_date"],
    }
    for f in _FLOAT_FIELDS:
        kw[f] = row[f] or 0
    for f in _BOOL_FIELDS:
        kw[f] = bool(row[f])
    for f in _INT_FIELDS:
        kw[f] = row[f] or 0
    for f in _STR_FIELDS:
        kw[f] = row[f] or ""
    sig_val = row["signal"]
    kw["signal"] = TradeSignal(sig_val) if sig_val and sig_val in [e.value for e in TradeSignal] else TradeSignal.WATCH
    return IndicatorResult(**kw)


def _build_save_tuple(result: IndicatorResult, today) -> tuple:
    """构建 INSERT 行 tuple（统一字段→位置映射，与 _load_from_row 保持一致）"""
    sig_val = result.signal.value if hasattr(result.signal, "value") else str(result.signal)
    return (
        result.ts_code,
        result.trade_date,
        today.close,
        today.open,
        today.high,
        today.low,
        today.vol,
        today.pct_chg,
        result.k,
        result.d,
        result.j,
        result.dif,
        result.dea,
        result.macd_hist,
        result.bbi,
        result.ma5,
        result.ma10,
        result.ma20,
        result.ma60,
        result.rsi6,
        result.rsi12,
        result.rsi24,
        result.wr5,
        result.wr10,
        result.boll_mid,
        result.boll_upper,
        result.boll_lower,
        result.boll_width,
        result.boll_position,
        result.vol_ratio,
        result.zg_white,
        result.dg_yellow,
        int(result.is_gold_cross),
        int(result.is_dead_cross),
        result.rsl_short,
        result.rsl_long,
        int(result.is_needle_20),
        result.brick_value,
        result.brick_trend,
        result.brick_count,
        int(result.brick_trend_up),
        int(result.is_fanbao),
        int(result.is_beidou),
        int(result.is_suoliang),
        int(result.is_jiayin_zhenyang),
        int(result.is_jiayang_zhenyin),
        int(result.is_fangliang_yinxian),
        result.sell_score,
        "",
        sig_val,
        sig_val,
        result.prev_high,
        result.prev_low,
        result.dmi_plus,
        result.dmi_minus,
        result.adx,
        result.net_lg_mf,
        result.net_elg_mf,
        result.last_b1_date,
        result.last_b1_price,
        "",
        0,
        "NEUTRAL",
        None,
    )


_SAVE_SQL = (
    """
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
    VALUES ("""
    + ",".join(["?"] * 64)
    + """)
"""
)


def _load_indicator_cache(ts_code: str, trade_date: str) -> IndicatorResult | None:
    """从 indicator_cache 表加载指标结果（内存 → DB）"""
    mem_key = (ts_code, trade_date)
    if mem_key in _indicator_memory_cache:
        return _indicator_memory_cache[mem_key]

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM indicator_cache WHERE ts_code = ? AND trade_date = ?",
            (ts_code, trade_date),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        result = _load_from_row(row)
        _indicator_memory_cache[mem_key] = result
        return result
    except Exception:
        return None


def _save_indicator_cache(result: IndicatorResult, klines: list[DailyData]) -> bool:
    """将指标结果写入 indicator_cache 表"""
    if not klines:
        return False

    today = klines[-1]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(_SAVE_SQL, _build_save_tuple(result, today))
        conn.commit()
        conn.close()
        _indicator_memory_cache[(result.ts_code, result.trade_date)] = result
        return True
    except Exception:
        return False


def clear_indicator_memory_cache():
    """清空内存缓存（用于测试或数据更新后）"""
    _indicator_memory_cache.clear()


def get_kline_data(ts_code: str, days: int = 100) -> list[DailyData]:
    """
    获取K线数据

    Args:
        ts_code: 股票代码
        days: 获取天数

    Returns:
        K线数据列表（按日期升序）
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
        FROM (
            SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
            FROM daily_kline
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
        )
        ORDER BY trade_date ASC
    """,
        (ts_code, days),
    )

    rows = cursor.fetchall()
    conn.close()

    data_list = []
    for i, row in enumerate(rows):
        prev_close = rows[i - 1]["close"] if i > 0 else row["close"]
        data_list.append(
            DailyData(
                ts_code=row["ts_code"],
                trade_date=row["trade_date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                vol=row["vol"],
                amount=row["amount"],
                pct_chg=row["pct_chg"],
                prev_close=prev_close,
            )
        )

    return data_list


def get_realtime_data(ts_code: str) -> DailyData | None:
    """
    获取实时/最新行情数据
    需要外部传入实时数据，这里仅作为数据结构定义
    """
    # 实际使用时由 tushare_client 获取实时数据
    pass


# ==================== 指标计算管道（v3.x 重构：替换 254 行上帝函数） ====================
#
# 每个管道步骤 = (min_klines, fn(klines, result) -> None)
# 新增指标只需写一个函数 + 在 _PIPELINE 中注册


def _step_kdj(klines, result):
    k, d, j = calculate_kdj(klines)
    result.k, result.d, result.j = k, d, j


def _step_macd(klines, result):
    dif_list, dea_list, macd_list = calculate_macd(klines)
    if not (dif_list and dea_list and macd_list):
        return
    result.dif = round(dif_list[-1], 4)
    result.dea = round(dea_list[-1], 4)
    result.macd_hist = round(macd_list[-1], 4)
    sig = detect_macd_signals(klines, dif_list, dea_list, macd_list)
    result.is_dif_positive = sig["is_dif_positive"]
    result.is_dif_cross_zero = sig["is_dif_cross_zero"]
    result.is_dif_cross_zero_down = sig["is_dif_cross_zero_down"]
    result.macd_gold_cross = sig["is_gold_cross"]
    result.macd_dead_cross = sig["is_dead_cross"]
    result.is_gold_fake = sig["is_gold_fake"]
    result.is_dead_fake = sig["is_dead_fake"]
    result.is_top_divergence = sig["is_top_divergence"]
    result.is_bottom_divergence = sig["is_bottom_divergence"]
    result.macd_veto = sig["macd_veto"]


def _step_bbi(klines, result):
    result.bbi = calculate_bbi(klines)


def _step_moving_averages(klines, result):
    closes = [k.close for k in klines]
    if len(closes) >= 5:
        result.ma5 = calculate_ma(closes, 5)
    if len(closes) >= 10:
        result.ma10 = calculate_ma(closes, 10)
    if len(closes) >= 20:
        result.ma20 = calculate_ma(closes, 20)
    if len(closes) >= 60:
        result.ma60 = calculate_ma(closes, 60)
    if len(klines) >= 240:
        highs = [k.high for k in klines[-240:]]
        result.high_52w = max(highs)
        result.high_52w_dist = (result.high_52w - klines[-1].close) / klines[-1].close * 100


def _step_rsi(klines, result):
    rsi6, rsi12, rsi24 = calculate_rsi_multi(klines)
    result.rsi6, result.rsi12, result.rsi24 = rsi6, rsi12, rsi24


def _step_wr(klines, result):
    wr5, wr10 = calculate_wr_multi(klines)
    result.wr5, result.wr10 = wr5, wr10


def _step_bollinger(klines, result):
    mid, upper, lower, width, pos = calculate_bollinger(klines)
    result.boll_mid, result.boll_upper = mid, upper
    result.boll_lower, result.boll_width, result.boll_position = lower, width, pos


def _step_vol_ratio(klines, result):
    result.vol_ratio = calculate_vol_ratio(klines)


def _step_double_line(klines, result):
    result.zg_white = calculate_zg_white(klines)
    result.dg_yellow = calculate_dg_yellow(klines)
    gc, dc = detect_double_line_cross(klines)
    result.is_gold_cross, result.is_dead_cross = gc, dc


def _step_needle_20(klines, result):
    rsl_s, rsl_l, is_needle = detect_needle_20(klines)
    result.rsl_short, result.rsl_long, result.is_needle_20 = rsl_s, rsl_l, is_needle


def _step_needle_30(klines, result):
    result.is_needle_30 = detect_needle_30(klines)


def _step_brick(klines, result):
    result.brick_value = calculate_brick_value(klines)
    trend, count = calculate_brick_history(klines)
    result.brick_trend, result.brick_count = trend, count
    result.brick_trend_up = detect_brick_trend(klines)
    result.is_fanbao = detect_fanbao(klines)


def _step_prev_high_low(klines, result):
    result.prev_high = klines[-2].high
    result.prev_low = klines[-2].low


def _step_dmi(klines, result):
    plus, minus, adx = calculate_dmi(klines)
    result.dmi_plus, result.dmi_minus, result.adx = plus, minus, adx


def _step_volume_pattern(klines, result):
    today = klines[-1]
    yesterday = klines[-2] if len(klines) > 1 else None
    vp = detect_volume_pattern(today, yesterday)
    result.is_beidou = vp["is_beidou"]
    result.is_suoliang = vp["is_suoliang"]
    result.is_jiayin_zhenyang = vp["is_jiayin_zhenyang"]
    result.is_jiayang_zhenyin = vp["is_jiayang_zhenyin"]
    result.is_fangliang_yinxian = vp["is_fangliang_yinxian"]


def _step_b1(klines, result):
    b1 = detect_b1_today(klines)
    result.is_b1 = b1["is_b1"]
    result.b1_j_value = b1["b1_j_value"]
    result.b1_amplitude = b1["b1_amplitude"]
    result.b1_pct_chg = b1["b1_pct_chg"]
    result.b1_volume_shrink = b1["b1_volume_shrink"]
    result.b1_score = b1["b1_score"]


def _step_b2(klines, result):
    b2 = detect_b2_today(klines)
    result.is_b2 = b2["is_b2"]
    result.b2_follows_b1 = b2["b2_follows_b1"]
    result.b2_pct_chg = b2["b2_pct_chg"]
    result.b2_j_value = b2["b2_j_value"]
    result.b2_volume_up = b2["b2_volume_up"]
    result.b2_score = b2["b2_score"]


def _step_key_k(klines, result):
    result.key_k_list = detect_key_k(klines)


def _step_violence_k(klines, result):
    vk_list = detect_violence_k(klines)
    if vk_list:
        latest_vk = [v for v in vk_list if v.get("is_latest", False)]
        if latest_vk:
            vk = latest_vk[0]
            result.is_violence_k = True
            result.violence_k_type = vk["type"]
            result.violence_k_body = vk["body_pct"]


def _step_two_30(klines, result):
    rule30 = check_two_30_rule(klines)
    result.b1_rally_pct = rule30["b1_rally_pct"]
    result.b1_pass_30 = rule30["b1_pass_30"]


def _step_nana(klines, result):
    result.is_nana = detect_nana_chart(klines)["is_nana"]


def _step_golden_bowl(klines, result):
    bowl = detect_golden_bowl(klines)
    result.is_in_bowl = bowl["is_in_bowl"]
    result.bowl_upper = bowl["bowl_upper"]
    result.bowl_lower = bowl["bowl_lower"]


def _step_breathing(klines, result):
    breath = detect_breathing_structure(klines)
    result.breath_phase = breath["breath_phase"]
    result.breath_n_type = breath["breath_n_type"]


def _step_sb1(klines, result):
    result.is_sb1 = detect_sb1(klines)["is_sb1"]


def _step_sb1_detailed(klines, result):
    result.is_sb1_detailed = detect_sb1_detailed(klines)["is_sb1_detailed"]


def _step_double_gun(klines, result):
    dg = detect_double_gun(klines)
    result.is_double_gun = dg["is_double_gun"]
    result.double_gun_vol1 = dg["double_gun_vol1"]
    result.double_gun_vol2 = dg["double_gun_vol2"]
    result.double_gun_gap_days = dg["double_gun_gap_days"]


def _step_yidong(klines, result):
    yd = detect_volume_anomaly(klines)
    result.is_yidong = yd["is_yidong"]
    result.yidong_type = yd["yidong_type"]
    result.yidong_vol_ratio = yd["yidong_vol_ratio"]
    result.yidong_above_60d = yd["yidong_above_60d"]


def _step_b3(klines, result):
    result.is_b3 = detect_b3(klines)["is_b3"]


def _step_four_brick(klines, result):
    bs = detect_four_brick_system(klines)
    result.brick_consecutive = bs["brick_consecutive"]
    result.brick_action = bs["brick_action"]
    result.brick_action_desc = bs["brick_action_desc"]
    result.is_brick_flip_green = bs["is_brick_flip_green"]


def _step_sell_score(klines, result):
    score, _, items = calculate_sell_score(klines)
    result.sell_score = score
    result.sell_items = items


# 计算管道：(最小K线数, 计算函数)
_PIPELINE: list[tuple[int, Callable[[Any, Any], None]]] = [
    (0, _step_kdj),
    (30, _step_macd),
    (24, _step_bbi),
    (0, _step_moving_averages),
    (25, _step_rsi),
    (10, _step_wr),
    (20, _step_bollinger),
    (0, _step_vol_ratio),
    (115, _step_double_line),
    (22, _step_needle_20),
    (22, _step_needle_30),
    (10, _step_brick),
    (2, _step_prev_high_low),
    (30, _step_dmi),
    (0, _step_volume_pattern),
    (10, _step_b1),
    (10, _step_b2),
    (10, _step_key_k),
    (10, _step_violence_k),
    (10, _step_two_30),
    (20, _step_nana),
    (120, _step_golden_bowl),
    (10, _step_breathing),
    (6, _step_sb1),
    (15, _step_sb1_detailed),
    (15, _step_double_gun),
    (65, _step_yidong),
    (15, _step_b3),
    (10, _step_four_brick),
    (0, _step_sell_score),
]


def analyze_stock(ts_code: str, days: int = 100) -> IndicatorResult:
    """综合分析单只股票（管道模式）

    Args:
        ts_code: 股票代码
        days: 分析数据天数

    Returns:
        指标计算结果
    """
    klines = get_kline_data(ts_code, days)
    if not klines:
        return IndicatorResult(ts_code=ts_code, trade_date="")

    today = klines[-1]
    cached = _load_indicator_cache(ts_code, today.trade_date)
    if cached:
        return cached

    result = IndicatorResult(ts_code=ts_code, trade_date=today.trade_date)

    # 执行计算管道
    n = len(klines)
    for min_klines, step_fn in _PIPELINE:
        if n >= min_klines:
            step_fn(klines, result)

    # 交易信号（依赖前面计算的部分指标）
    result.signal = detect_trade_signal(klines)

    return result


def visualize_brick_chart(klines: list[DailyData], lookback: int = 20) -> str:
    """
    生成砖型图可视化（文本版）

    用汉字+个数显示砖型图，红*N/绿*N，不表示强弱
    """
    if len(klines) < 10:
        return "数据不足"

    # 计算全量历史砖值序列
    brick_history = []
    dates = []
    closes = []
    pcts = []

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)
        brick_history.append(brick_val)
        day = klines[i - 1]
        dates.append(day.trade_date)
        closes.append(day.close)
        pcts.append(day.pct_chg)

    if len(brick_history) < 3:
        return "数据不足"

    # 只取最近 lookback 天
    brick_history = brick_history[-lookback:]
    dates = dates[-lookback:]
    closes = closes[-lookback:]
    pcts = pcts[-lookback:]

    # 计算红绿砖：当日砖值 >= 昨日砖值 = 红砖
    colors = []  # 1=红, -1=绿
    for i in range(1, len(brick_history)):
        if brick_history[i] >= brick_history[i - 1]:
            colors.append(1)
        else:
            colors.append(-1)

    if not colors:
        return "无砖型数据"

    lines = []
    lines.append(f"  {'日期':<10} {'收盘':>7} {'涨跌%':>7} {'砖值':>6}  砖型图")
    lines.append("  " + "-" * 45)

    # 计算连续同色砖
    i = 0
    while i < len(colors):
        idx = i + 1
        color = colors[i]
        count = 1
        while i + count < len(colors) and colors[i + count] == color:
            count += 1

        brick = brick_history[idx]
        if color == 1:
            bar = f"红 * {count}"
        else:
            bar = f"绿 * {count}"

        pct_str = f"{pcts[idx]:+6.2f}%"
        line = f"  {dates[idx]}  {closes[idx]:7.2f}  {pct_str}  {brick:6.1f}  {bar}"
        lines.append(line)

        i += count

    lines.append("  " + "-" * 45)
    trend_text = "红砖(上涨动量)" if colors[-1] == 1 else "绿砖(下跌动量)"
    lines.append(f"  趋势: {trend_text}")
    lines.append(f"  砖值范围: {min(brick_history):.1f} ~ {max(brick_history):.1f}")

    return "\n".join(lines)


def format_result(result: IndicatorResult) -> str:
    """格式化输出结果"""
    lines = [
        f"{'=' * 60}",
        f"股票: {result.ts_code}  日期: {result.trade_date}",
        f"{'=' * 60}",
        f"[KDJ]  K={result.k:.2f}  D={result.d:.2f}  J={result.j:.2f}",
        "",
        f"[MACD] DIF={result.dif:.4f}  DEA={result.dea:.4f}  柱={result.macd_hist:.4f}",
    ]

    # MACD 语料判断
    macd_lines = []
    zone = "多头区间(DIF>0)" if result.is_dif_positive else "空头区间(DIF<0)"
    macd_lines.append(f"  0轴位置: {zone}")

    if result.is_dif_cross_zero:
        macd_lines.append("  * DIF 上穿0轴（红点标记）")
    if result.is_dif_cross_zero_down:
        macd_lines.append("  * DIF 下穿0轴（绿点标记）")

    if result.macd_gold_cross:
        macd_lines.append("  金叉: DIF 上穿 DEA")
    if result.macd_dead_cross:
        macd_lines.append("  死叉: DIF 下穿 DEA")

    if result.is_gold_fake:
        macd_lines.append("  !!! 金叉空（诱多陷阱，快跑）")
    if result.is_dead_fake:
        macd_lines.append("  !!! 死叉多（空中加油，强多）")

    if result.is_top_divergence:
        macd_lines.append("  !!! 顶背离，见顶减仓")
    if result.is_bottom_divergence:
        macd_lines.append("  !!! 底背离，反转建仓")

    if result.macd_veto:
        macd_lines.append("  XXX MACD一票否决：不能买！")
    else:
        macd_lines.append("  MACD未否决")

    lines.append("\n".join(macd_lines))
    lines.append("")
    lines.append(f"[BBI]  {result.bbi:.2f}")
    lines.append(f"[均线] MA5={result.ma5:.2f}  MA10={result.ma10:.2f}  MA20={result.ma20:.2f}  MA60={result.ma60:.2f}")
    if result.high_52w > 0:
        lines.append(f"[52周最高] {result.high_52w:.2f}  (距现价 +{result.high_52w_dist:.1f}%)")
    lines.append(f"[RSI]  RSI6={result.rsi6:.2f}  RSI12={result.rsi12:.2f}  RSI24={result.rsi24:.2f}")
    lines.append(f"[WR]   WR5={result.wr5:.2f}  WR10={result.wr10:.2f}")
    lines.append(
        f"[布林带] 中={result.boll_mid:.2f}  上={result.boll_upper:.2f}  下={result.boll_lower:.2f}  宽={result.boll_width:.2f}%  位置={result.boll_position:.1f}%"
    )
    lines.append(f"[量比] {result.vol_ratio:.2f}x")
    lines.append("")
    lines.append(
        f"[双线战法] 白线={result.zg_white:.2f}  大哥线={result.dg_yellow:.2f}  Gold:{result.is_gold_cross}  Dead:{result.is_dead_cross}"
    )
    lines.append(f"[单针下20] RSL_S={result.rsl_short:.2f}  RSL_L={result.rsl_long:.2f}  Signal:{result.is_needle_20}")
    if result.is_needle_30:
        lines.append("[单针下30] *** 信号触发 (红>85, 白<30)")
    lines.append("")

    # B1/B2 战法检测
    if result.b1_score > 0 or result.b2_score > 0:
        lines.append("[B1建仓波]")
        if result.is_b1:
            lines.append(
                f"  *** B1信号触发! J={result.b1_j_value}  振幅={result.b1_amplitude:.1f}%  涨幅={result.b1_pct_chg:.1f}%  缩量:{result.b1_volume_shrink}  评分:{result.b1_score}/4"
            )
        else:
            lines.append(
                f"  J={result.b1_j_value}  振幅={result.b1_amplitude:.1f}%  涨幅={result.b1_pct_chg:.1f}%  评分:{result.b1_score}/4 (未触发)"
            )
        lines.append("")

        lines.append("[B2突破]")
        if result.is_b2:
            lines.append(
                f"  *** B2信号触发! 涨幅={result.b2_pct_chg:.1f}%  J={result.b2_j_value}  放量:{result.b2_volume_up}  评分:{result.b2_score}/4"
            )
        else:
            lines.append(
                f"  涨幅={result.b2_pct_chg:.1f}%  J={result.b2_j_value}  跟随B1:{result.b2_follows_b1}  评分:{result.b2_score}/4 (未触发)"
            )
        lines.append("")

    # 砖型图可视化
    try:
        klines = get_kline_data(result.ts_code, days=120)
        if len(klines) >= 10:
            brick_vis = visualize_brick_chart(klines, lookback=15)
            lines.append("[砖型图可视化]")
            lines.append(brick_vis)
            lines.append("")
    except Exception:
        pass

    lines.append(f"[砖型图] Brick={result.brick_value:.2f}  TrendUp:{result.brick_trend_up}  Fanbao:{result.is_fanbao}")
    lines.append("")
    lines.append("[量价形态]")
    lines.append(f"  倍量: {'OK' if result.is_beidou else '--'}  缩量: {'OK' if result.is_suoliang else '--'}")
    lines.append(
        f"  假阴真阳: {'OK' if result.is_jiayin_zhenyang else '--'}  放量阴线: {'OK' if result.is_fangliang_yinxian else '--'}"
    )
    lines.append("")

    # 关键K / 暴力K（显示60日内找到的关键K）
    if result.key_k_list:
        lines.append(f"[关键K] 60日内找到 {len(result.key_k_list)} 根关键K:")
        for kk in result.key_k_list[-5:]:  # 最多显示最近5根
            marker = " <<< 今日" if kk.get("is_latest", False) else ""
            lines.append(
                f"  {kk['date']}  {kk['type']}  收{kk['close']:.2f}({kk['pct']:+.1f}%)  实体{kk['body_pct']:.1f}%  量比{kk['vol_ratio']:.1f}x{marker}"
            )
        lines.append("")
    if result.is_violence_k:
        lines.append(f"[暴力K] *** {result.violence_k_type}  实体={result.violence_k_body:.1f}%")
        lines.append("")

    # 两个30%原则
    if result.b1_rally_pct != 0 or result.b1_pass_30:
        lines.append(f"[两个30%原则] B1涨幅={result.b1_rally_pct:.1f}%  通过:{result.b1_pass_30}")
        lines.append("")

    # 娜娜图/黄金碗/呼吸结构/SB1/B3
    if result.is_nana:
        lines.append("[娜娜图] *** 完美建仓信号")
        lines.append("")
    if result.is_in_bowl:
        lines.append(f"[黄金碗] *** 价格在碗内  上沿={result.bowl_upper:.2f}  下沿={result.bowl_lower:.2f}")
        lines.append("")
    if result.breath_phase and result.breath_phase != "none":
        n_type = " N型结构" if result.breath_n_type else ""
        phase_label = "呼气" if result.breath_phase == "exhale" else "吸气"
        lines.append(f"[呼吸结构] {phase_label}{n_type}")
        lines.append("")
    if result.is_sb1:
        lines.append("[SB1假摔] *** 假摔信号触发")
        lines.append("")
    if result.is_sb1_detailed:
        lines.append("[超级B1] *** 超级B1信号触发")
        lines.append("")
    if result.is_double_gun:
        lines.append(
            f"[双枪战法] *** 第一枪量比{result.double_gun_vol1:.1f}x 第二枪{result.double_gun_vol2:.1f}x 间隔{result.double_gun_gap_days}天"
        )
        lines.append("")
    if result.is_yidong:
        lines.append(
            f"[异动选股] *** {result.yidong_type} 量比{result.yidong_vol_ratio:.1f}x 60日线={'上方' if result.yidong_above_60d else '下方'}"
        )
        lines.append("")
    if result.is_b3:
        lines.append("[B3买点] *** B3信号触发")
        lines.append("")

    # 四块砖交易体系
    if result.brick_action:
        flip_marker = " *** 红翻绿止损" if result.is_brick_flip_green else ""
        lines.append(f"[四块砖体系] 连续{result.brick_consecutive}砖 | 操作: {result.brick_action}{flip_marker}")
        lines.append(f"  {result.brick_action_desc}")
        lines.append("")

    lines.append(f"[防卖飞评分] {result.sell_score}/5")
    if result.sell_items:
        for item_name, passed in result.sell_items.items():
            lines.append(f"  {item_name}: {'[Y]' if passed else '[N]'}")
    else:
        lines.append("  (数据不足)")
    lines.append("")
    lines.append(f"[交易信号] {result.signal.value}")
    lines.append(f"{'=' * 60}")
    return "\n".join(lines)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Z哥 技术指标分析")
    parser.add_argument("ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=100, help="分析天数")

    args = parser.parse_args()

    result = analyze_stock(args.ts_code, args.days)
    print(format_result(result))


if __name__ == "__main__":
    main()
