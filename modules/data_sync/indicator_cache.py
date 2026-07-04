"""Indicator cache computation helpers."""

from __future__ import annotations
from types import SimpleNamespace
from typing import Any, Optional

_INDICATOR_FUNCS: SimpleNamespace | None = None


def _get_indicator_funcs() -> SimpleNamespace:
    """延迟导入技术指标函数，模块级单例（避免每次 sync_indicator_cache 重复 import）"""
    global _INDICATOR_FUNCS
    if _INDICATOR_FUNCS is None:
        from ..indicators import (
            get_kline_data,
            precompute_kdj_sequence,
            precompute_macd_sequence,
            calculate_bbi,
            calculate_ma,
            calculate_rsi_multi,
            calculate_wr_multi,
            calculate_bollinger,
            calculate_vol_ratio,
            calculate_zg_white,
            calculate_dg_yellow,
            detect_double_line_cross,
            detect_needle_20,
            calculate_brick_value,
            calculate_brick_history,
            detect_brick_trend,
            detect_fanbao,
            detect_volume_pattern,
            calculate_sell_score,
            detect_trade_signal,
            calculate_dmi,
        )

        _INDICATOR_FUNCS = SimpleNamespace(
            get_kline_data=get_kline_data,
            precompute_kdj_sequence=precompute_kdj_sequence,
            precompute_macd_sequence=precompute_macd_sequence,
            calculate_bbi=calculate_bbi,
            calculate_ma=calculate_ma,
            calculate_rsi_multi=calculate_rsi_multi,
            calculate_wr_multi=calculate_wr_multi,
            calculate_bollinger=calculate_bollinger,
            calculate_vol_ratio=calculate_vol_ratio,
            calculate_zg_white=calculate_zg_white,
            calculate_dg_yellow=calculate_dg_yellow,
            detect_double_line_cross=detect_double_line_cross,
            detect_needle_20=detect_needle_20,
            calculate_brick_value=calculate_brick_value,
            calculate_brick_history=calculate_brick_history,
            detect_brick_trend=detect_brick_trend,
            detect_fanbao=detect_fanbao,
            detect_volume_pattern=detect_volume_pattern,
            calculate_sell_score=calculate_sell_score,
            detect_trade_signal=detect_trade_signal,
            calculate_dmi=calculate_dmi,
        )
    return _INDICATOR_FUNCS


def _compute_day_indicators(
    f: SimpleNamespace,
    sub_klines: list,
    today,
    yesterday,
    kdj_seq,
    macd_dif_seq,
    macd_dea_seq,
    macd_hist_seq,
    idx: int,
) -> dict[str, Any]:
    """计算单日全部技术指标，返回 dict。

    从 sync_indicator_cache 循环体抽出，使计算逻辑与 SQL 行构建分离。
    """
    n = len(sub_klines)
    closes = [k.close for k in sub_klines]

    # KDJ / MACD（从预计算序列取，O(1)）
    k, d, j = kdj_seq[idx] if kdj_seq else (50, 50, 50)
    if macd_dif_seq is not None:
        dif, dea, macd_hist = macd_dif_seq[idx], macd_dea_seq[idx], macd_hist_seq[idx]
    else:
        dif, dea, macd_hist = 0.0, 0.0, 0.0

    # 均线
    bbi = f.calculate_bbi(sub_klines) if n >= 24 else 0
    ma5 = f.calculate_ma(closes, 5) if n >= 5 else 0
    ma10 = f.calculate_ma(closes, 10) if n >= 10 else 0
    ma20 = f.calculate_ma(closes, 20) if n >= 20 else 0
    ma60 = f.calculate_ma(closes, 60) if n >= 60 else 0

    # RSI / WR
    rsi6, rsi12, rsi24 = f.calculate_rsi_multi(sub_klines) if n >= 25 else (50, 50, 50)
    wr5, wr10 = f.calculate_wr_multi(sub_klines) if n >= 10 else (-50, -50)

    # 布林带
    boll_vals = f.calculate_bollinger(sub_klines) if n >= 20 else (0, 0, 0, 0, 50)
    boll_mid, boll_upper, boll_lower, boll_width, boll_pos = boll_vals

    # 量比
    vol_ratio = f.calculate_vol_ratio(sub_klines)

    # 双线战法
    zg_white = f.calculate_zg_white(sub_klines) if n >= 115 else 0
    dg_yellow = f.calculate_dg_yellow(sub_klines) if n >= 115 else 0
    gold_cross, dead_cross = f.detect_double_line_cross(sub_klines) if n >= 115 else (False, False)

    # 单针下20
    rsl_short, rsl_long, is_needle = f.detect_needle_20(sub_klines) if n >= 22 else (50, 50, False)

    # 砖型图
    brick_value = f.calculate_brick_value(sub_klines) if n >= 8 else 0
    brick_trend, brick_count = f.calculate_brick_history(sub_klines) if n >= 10 else ("NEUTRAL", 0)
    brick_trend_up = f.detect_brick_trend(sub_klines) if n >= 115 else False
    is_fanbao = f.detect_fanbao(sub_klines) if n >= 4 else False

    # 量价形态
    vol_pattern = f.detect_volume_pattern(today, yesterday) if yesterday else {}
    is_beidou = vol_pattern.get("is_beidou", 0)
    is_suoliang = vol_pattern.get("is_suoliang", 0)
    is_jiayin_zhenyang = vol_pattern.get("is_jiayin_zhenyang", 0)
    is_jiayang_zhenyin = vol_pattern.get("is_jiayang_zhenyin", 0)
    is_fangliang_yinxian = vol_pattern.get("is_fangliang_yinxian", 0)

    # 卖出评分
    sell_result = f.calculate_sell_score(sub_klines) if n >= 5 else (3, {})
    sell_score = sell_result[0]
    sell_items = sell_result[1] if isinstance(sell_result[1], dict) else {}
    sell_reason = ",".join([k for k, v in sell_items.items() if not v]) if sell_items else "数据不足"

    # 交易信号
    signal = f.detect_trade_signal(sub_klines) if n >= 30 else "WATCH"
    signal_desc = signal.value if hasattr(signal, "value") else str(signal)

    # DMI
    dmi_plus, dmi_minus, adx = f.calculate_dmi(sub_klines) if n >= 30 else (0, 0, 0)

    # 昨高昨低
    prev_high = sub_klines[-2].high if n > 1 else 0
    prev_low = sub_klines[-2].low if n > 1 else 0

    return {
        # 基础行情
        "close": today.close,
        "open": today.open,
        "high": today.high,
        "low": today.low,
        "vol": today.vol,
        "pct_chg": today.pct_chg,
        # KDJ
        "k": k,
        "d": d,
        "j": j,
        # MACD
        "dif": dif,
        "dea": dea,
        "macd_hist": macd_hist,
        # 均线
        "bbi": bbi,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        # RSI / WR
        "rsi6": rsi6,
        "rsi12": rsi12,
        "rsi24": rsi24,
        "wr5": wr5,
        "wr10": wr10,
        # 布林带
        "boll_mid": boll_mid,
        "boll_upper": boll_upper,
        "boll_lower": boll_lower,
        "boll_width": boll_width,
        "boll_position": boll_pos,
        # 量比
        "vol_ratio": vol_ratio,
        # 双线
        "zg_white": zg_white,
        "dg_yellow": dg_yellow,
        "gold_cross": gold_cross,
        "dead_cross": dead_cross,
        # 单针
        "rsl_short": rsl_short,
        "rsl_long": rsl_long,
        "is_needle": is_needle,
        # 砖型
        "brick_value": brick_value,
        "brick_trend": brick_trend,
        "brick_count": brick_count,
        "brick_trend_up": brick_trend_up,
        "is_fanbao": is_fanbao,
        # 量价信号
        "is_beidou": is_beidou,
        "is_suoliang": is_suoliang,
        "is_jiayin_zhenyang": is_jiayin_zhenyang,
        "is_jiayang_zhenyin": is_jiayang_zhenyin,
        "is_fangliang_yinxian": is_fangliang_yinxian,
        # 卖出
        "sell_score": sell_score,
        "sell_reason": sell_reason,
        "signal_desc": signal_desc,
        # 关键价位
        "prev_high": prev_high,
        "prev_low": prev_low,
        # DMI
        "dmi_plus": dmi_plus,
        "dmi_minus": dmi_minus,
        "adx": adx,
    }


# _INDICATOR_INSERT_COLUMNS 与 _build_indicator_row 共用同一列序
_INDICATOR_INSERT_COLUMNS = (
    "ts_code, trade_date, close, open, high, low, vol, pct_chg, "
    "k, d, j, dif, dea, macd_hist, bbi, "
    "ma5, ma10, ma20, ma60, "
    "rsi6, rsi12, rsi24, wr5, wr10, "
    "boll_mid, boll_upper, boll_lower, boll_width, boll_position, "
    "vol_ratio, zg_white, dg_yellow, "
    "is_gold_cross, is_dead_cross, "
    "rsl_short, rsl_long, is_needle_20, "
    "brick_value, brick_trend, brick_count, brick_trend_up, is_fanbao, "
    "is_beidou, is_suoliang, is_jiayin_zhenyang, is_jiayang_zhenyin, is_fangliang_yinxian, "
    "sell_score, sell_reason, signal, signal_desc, "
    "prev_high, prev_low, dmi_plus, dmi_minus, adx, "
    "net_lg_mf, net_elg_mf, last_b1_date, last_b1_price, "
    "last_yidong_date, market_pct_chg, market_dir, updated_at"
)


def _build_indicator_row(ts_code: str, trade_date: str, ind: dict[str, Any]) -> tuple:
    """从 _compute_day_indicators 返回的 dict 构建 INSERT 行 tuple。

    列顺序与 _INDICATOR_INSERT_COLUMNS 保持一致。
    此函数是唯一的字段→位置映射点，新增字段只需在此修改。
    """
    return (
        ts_code,
        trade_date,
        ind["close"],
        ind["open"],
        ind["high"],
        ind["low"],
        ind["vol"],
        ind["pct_chg"],
        ind["k"],
        ind["d"],
        ind["j"],
        ind["dif"],
        ind["dea"],
        ind["macd_hist"],
        ind["bbi"],
        ind["ma5"],
        ind["ma10"],
        ind["ma20"],
        ind["ma60"],
        ind["rsi6"],
        ind["rsi12"],
        ind["rsi24"],
        ind["wr5"],
        ind["wr10"],
        ind["boll_mid"],
        ind["boll_upper"],
        ind["boll_lower"],
        ind["boll_width"],
        ind["boll_position"],
        ind["vol_ratio"],
        ind["zg_white"],
        ind["dg_yellow"],
        int(ind["gold_cross"]),
        int(ind["dead_cross"]),
        ind["rsl_short"],
        ind["rsl_long"],
        int(ind["is_needle"]),
        ind["brick_value"],
        ind["brick_trend"],
        ind["brick_count"],
        int(ind["brick_trend_up"]),
        int(ind["is_fanbao"]),
        int(ind["is_beidou"]),
        int(ind["is_suoliang"]),
        int(ind["is_jiayin_zhenyang"]),
        int(ind["is_jiayang_zhenyin"]),
        int(ind["is_fangliang_yinxian"]),
        ind["sell_score"],
        ind["sell_reason"],
        ind["signal_desc"],
        ind["signal_desc"],  # signal, signal_desc 当前复用同一值
        ind["prev_high"],
        ind["prev_low"],
        ind["dmi_plus"],
        ind["dmi_minus"],
        ind["adx"],
        0,  # net_lg_mf（暂未实现）
        0,  # net_elg_mf（暂未实现）
        None,  # last_b1_date（暂未实现）
        0,  # last_b1_price（暂未实现）
        None,  # last_yidong_date（暂未实现）
        0,  # market_pct_chg（暂未实现）
        "NEUTRAL",  # market_dir（暂未实现）
        None,  # updated_at（DEFAULT CURRENT_TIMESTAMP）
    )
