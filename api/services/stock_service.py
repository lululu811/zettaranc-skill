"""股票分析服务 — 封装 modules 层的分析逻辑"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_full_analysis(ts_code: str, days: int = 120) -> dict[str, Any]:
    """
    全量分析：指标 + 三波 + 麒麟会 + 战法信号 + 诊断 + 评分
    复刻 modules/cli.py 的 _analyze_core() 逻辑，返回结构化 dict
    """
    from modules.indicators import analyze_stock, detect_three_waves, detect_kirin_stage
    from modules.indicators.data_layer import get_kline_data, DailyData
    from modules.strategies import detect_all_strategies
    from modules.portfolio_diagnosis import diagnose_stock
    from modules.screener import analyze_stock as screener_analyze

    # 1. 指标分析
    result = analyze_stock(ts_code, days=days)

    # 1.1 取最近 K 线，计算真实的 prev_close 和当日涨跌幅
    prev_close = 0.0
    pct_chg = 0.0
    try:
        from modules.indicators.data_layer import get_kline_data as _gl

        klines_for_pct = _gl(ts_code, days=5)
        if klines_for_pct and len(klines_for_pct) >= 2:
            prev_close = klines_for_pct[-2].close
            pct_chg = getattr(klines_for_pct[-1], "pct_chg", 0.0) or 0.0
        elif klines_for_pct:
            prev_close = klines_for_pct[-1].close
    except Exception:
        logger.warning("获取 prev_close 失败: %s", ts_code, exc_info=True)

    # 2. 三波 + 麒麟会
    wave_data = None
    kirin_data = None
    try:
        klines = get_kline_data(ts_code, days=days)
        if klines:
            daily_klines = []
            for i, k in enumerate(klines):
                prev_close = klines[i - 1].close if i > 0 else k.close
                daily_klines.append(
                    DailyData(
                        ts_code=k.ts_code,
                        trade_date=k.trade_date,
                        open=k.open,
                        high=k.high,
                        low=k.low,
                        close=k.close,
                        vol=k.vol,
                        amount=k.amount,
                        pct_chg=k.pct_chg,
                        prev_close=prev_close,
                    )
                )
            wave_data = detect_three_waves(daily_klines)
            kirin_data = detect_kirin_stage(daily_klines)
    except Exception:
        logger.warning("三波/麒麟会分析失败: %s", ts_code, exc_info=True)

    # 3. 策略信号
    signals = detect_all_strategies(ts_code, days=days)

    # 4. 诊断
    diagnosis = diagnose_stock(ts_code, days=days)

    # 5. 评分
    score = screener_analyze(ts_code)

    # ── 组装响应 ──
    return {
        "ts_code": ts_code,
        "name": getattr(diagnosis, "name", ts_code),
        "price": getattr(diagnosis, "price", 0),
        "prev_close": prev_close,
        "pct_chg": pct_chg,
        "trade_date": result.trade_date,
        "indicators": _build_indicators(result, diagnosis),
        "waves": _build_waves(wave_data),
        "kirin": _build_kirin(kirin_data),
        "signals": _build_signals(signals),
        "score": _build_score(score),
        "diagnosis": _build_diagnosis(diagnosis),
    }


def get_kline_chart_data(ts_code: str, days: int = 120) -> dict[str, Any]:
    """获取 K 线图表数据（ECharts 列式格式）"""
    from modules.indicators.data_layer import get_kline_data
    from modules.indicators.core import (
        calculate_ma, calculate_ma_series, calculate_ema_series,
        calculate_bbi, calculate_bollinger,
        calculate_kdj, calculate_macd,
    )
    from modules.indicators.price_patterns import (
        calculate_zg_white,
        calculate_dg_yellow,
    )
    from modules.strategies import detect_all_strategies

    # 多取历史数据用于指标计算（黄线需要 114 天 MA114）
    # 展示最近 days 天，但用更多历史数据计算指标
    extra_days = max(days + 130, 250)
    all_klines = get_kline_data(ts_code, days=extra_days)
    if not all_klines:
        return {
            "ts_code": ts_code,
            "dates": [],
            "ohlc": [],
            "volumes": [],
            "pct_chgs": [],
            "overlays": {},
            "signal_markers": [],
            "kdj": {"k": [], "d": [], "j": []},
            "macd": {"dif": [], "dea": [], "hist": []},
        }

    # 只取最近 days 天用于展示
    klines = all_klines[-days:]
    if not klines:
        return {
            "ts_code": ts_code,
            "dates": [],
            "ohlc": [],
            "volumes": [],
            "pct_chgs": [],
            "overlays": {},
            "signal_markers": [],
            "kdj": {"k": [], "d": [], "j": []},
            "macd": {"dif": [], "dea": [], "hist": []},
        }

    # 获取股票名称
    name = _get_stock_name(ts_code)

    dates = []
    ohlc = []
    volumes = []
    pct_chgs = []
    closes = []
    highs = []
    lows = []
    opens = []

    for k in klines:
        dates.append(k.trade_date)
        ohlc.append([k.open, k.close, k.low, k.high])
        volumes.append(k.vol)
        pct_chgs.append(k.pct_chg)
        closes.append(k.close)
        highs.append(k.high)
        lows.append(k.low)
        opens.append(k.open)

    # 计算叠加指标
    n = len(closes)
    overlays: dict[str, list[float | None]] = {}

    # MA
    for period, key in [(5, "ma5"), (10, "ma10"), (20, "ma20"), (60, "ma60")]:
        ma_vals: list[float | None] = [None] * n
        for i in range(period - 1, n):
            ma_vals[i] = round(sum(closes[i - period + 1 : i + 1]) / period, 2)
        overlays[key] = ma_vals

    # BBI
    bbi_vals: list[float | None] = [None] * n
    for i in range(23, n):  # BBI 需要 MA3/MA6/MA12/MA24
        ma3 = sum(closes[i - 2 : i + 1]) / 3
        ma6 = sum(closes[i - 5 : i + 1]) / 6
        ma12 = sum(closes[i - 11 : i + 1]) / 12
        ma24 = sum(closes[i - 23 : i + 1]) / 24
        bbi_vals[i] = round((ma3 + ma6 + ma12 + ma24) / 4, 2)
    overlays["bbi"] = bbi_vals

    # 布林带
    boll_mid: list[float | None] = [None] * n
    boll_upper: list[float | None] = [None] * n
    boll_lower: list[float | None] = [None] * n
    for i in range(19, n):
        window = closes[i - 19 : i + 1]
        mid = sum(window) / 20
        std = (sum((x - mid) ** 2 for x in window) / 20) ** 0.5
        boll_mid[i] = round(mid, 2)
        boll_upper[i] = round(mid + 2 * std, 2)
        boll_lower[i] = round(mid - 2 * std, 2)
    overlays["boll_mid"] = boll_mid
    overlays["boll_upper"] = boll_upper
    overlays["boll_lower"] = boll_lower

    # 白线 / 黄线（双线战法）
    # 注意：calculate_zg_white / calculate_dg_yellow 的签名是 (klines) 而非 (klines, index)，
    # 历史上这里误传了 index 导致每天抛 TypeError 被吞掉 → 序列全为 None、图上从不出线。
    # 现改为整段序列计算（O(n)），与逐日切片结果一致。
    try:
        closes_all = [k.close for k in all_klines]
        white_series = calculate_ema_series(calculate_ema_series(closes_all, 10), 10)
        ma14 = calculate_ma_series(closes_all, 14)
        ma28 = calculate_ma_series(closes_all, 28)
        ma57 = calculate_ma_series(closes_all, 57)
        ma114 = calculate_ma_series(closes_all, 114)
        yellow_series: list[float | None] = []
        for a, b, c, d in zip(ma14, ma28, ma57, ma114):
            yellow_series.append((a + b + c + d) / 4 if None not in (a, b, c, d) else None)

        start = max(0, len(all_klines) - days)
        overlays["white_line"] = [round(v, 2) if v else None for v in white_series[start:]]
        overlays["yellow_line"] = [round(v, 2) if v else None for v in yellow_series[start:]]
    except (IndexError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.warning("白线/黄线计算失败: %s: %s", ts_code, e)
        overlays["white_line"] = [None] * days
        overlays["yellow_line"] = [None] * days

    # ── KDJ 时间序列 ── 用全量历史数据计算
    kdj_k: list[float | None] = [None] * n
    kdj_d: list[float | None] = [None] * n
    kdj_j: list[float | None] = [None] * n
    try:
        from modules.indicators.core import precompute_kdj_sequence

        kdj_full = precompute_kdj_sequence(all_klines)
        # 截取最后 days 天
        for i, (k_val, d_val, j_val) in enumerate(kdj_full[-days:]):
            kdj_k[i] = round(k_val, 2)
            kdj_d[i] = round(d_val, 2)
            kdj_j[i] = round(j_val, 2)
    except Exception:
        for i in range(8, n):
            low9 = min(lows[i - 8 : i + 1])
            high9 = max(highs[i - 8 : i + 1])
            rsv = 50 if high9 == low9 else (closes[i] - low9) / (high9 - low9) * 100
            k_val = 50 if i == 8 else (kdj_k[i - 1] or 50) * 2 / 3 + rsv / 3
            d_val = 50 if i == 8 else (kdj_d[i - 1] or 50) * 2 / 3 + k_val / 3
            j_val = 3 * k_val - 2 * d_val
            kdj_k[i] = round(k_val, 2)
            kdj_d[i] = round(d_val, 2)
            kdj_j[i] = round(j_val, 2)

    # ── MACD 时间序列 ── 用全量历史数据计算
    macd_dif: list[float | None] = [None] * n
    macd_dea: list[float | None] = [None] * n
    macd_hist: list[float | None] = [None] * n
    try:
        from modules.indicators.core import precompute_macd_sequence

        dif_full, dea_full, macd_full = precompute_macd_sequence(all_klines)
        for i in range(n):
            idx = len(all_klines) - days + i
            if dif_full[idx] is not None:
                macd_dif[i] = round(dif_full[idx], 4)
            if dea_full[idx] is not None:
                macd_dea[i] = round(dea_full[idx], 4)
            if macd_full[idx] is not None:
                macd_hist[i] = round(macd_full[idx] * 2, 4)
    except Exception:
        pass

    # ─ 砖型图时间序列
    brick_values: list[float | None] = [None] * n
    brick_colors: list[int | None] = [None] * n
    try:
        from modules.indicators.price_patterns import calculate_brick_value

        for i in range(n):
            idx = len(all_klines) - days + i
            sub_klines = all_klines[: idx + 1]
            try:
                val = calculate_brick_value(sub_klines)
                brick_values[i] = round(val, 2) if val else None
                # 判断红绿：大于等于前一天为红(1)，小于为绿(-1)
                if i > 0 and brick_values[i] is not None and brick_values[i - 1] is not None:
                    brick_colors[i] = 1 if brick_values[i] >= brick_values[i - 1] else -1
                else:
                    brick_colors[i] = 1  # 默认红色
            except Exception:
                pass
    except Exception:
        logger.warning("砖型图计算失败: %s", ts_code, exc_info=True)

    # 信号标注
    signal_markers = []
    try:
        signals = detect_all_strategies(ts_code, days=days)
        date_set = set(dates)
        for s in signals[:30]:  # 最多取 30 个信号
            if s.trade_date in date_set:
                signal_markers.append(
                    {
                        "date": s.trade_date,
                        "type": s.strategy.value,
                        "price": s.price or 0,
                        "action": s.action,
                    }
                )
    except Exception:
        logger.warning("信号标注获取失败: %s", ts_code, exc_info=True)

    # ── 计算主力阶段序列与多空呼吸波 ──
    waves_sequence = []
    kirin_sequence = []
    raw_breathing = []

    try:
        from modules.indicators.wave_theory import detect_three_waves
        from modules.indicators.kirin_detector import detect_kirin_stage

        for i in range(days):
            idx = len(all_klines) - days + i
            sub_klines = all_klines[: idx + 1]

            # 1. 三波理论阶段
            try:
                w_res = detect_three_waves(sub_klines)
                waves_sequence.append(w_res.get("wave", "未知"))
            except Exception:
                waves_sequence.append("未知")

            # 2. 麒麟会阶段
            try:
                k_res = detect_kirin_stage(sub_klines)
                kirin_sequence.append(k_res.get("stage", "未知"))
            except Exception:
                kirin_sequence.append("未知")

            # 3. 呼吸波原始分值
            if len(sub_klines) < 2:
                raw_breathing.append(0.0)
                continue

            today_bar = sub_klines[-1]
            prev_bar = sub_klines[-2]

            if prev_bar.vol <= 0:
                raw_breathing.append(0.0)
                continue

            vol_ratio = today_bar.vol / prev_bar.vol
            pct = today_bar.pct_chg if today_bar.pct_chg is not None else 0.0

            if pct > 0 and vol_ratio > 1:
                # 放量涨：呼气
                raw_breathing.append(min(vol_ratio - 1.0, 3.0))
            elif pct < 0 and vol_ratio < 1:
                # 缩量跌：吸气
                raw_breathing.append(-min((1.0 / vol_ratio) - 1.0, 3.0))
            elif pct < 0 and vol_ratio >= 1:
                # 放量跌：派发/恐慌
                raw_breathing.append(-0.5 * min(vol_ratio, 2.0))
            else:
                # 缩量涨（量价背离）
                raw_breathing.append(0.1)
    except Exception:
        logger.exception("计算主力阶段序列与多空呼吸波失败: %s", ts_code)
        waves_sequence = ["未知"] * days
        kirin_sequence = ["未知"] * days
        raw_breathing = [0.0] * days

    # 4. 对呼吸原始分值做 5 日平滑
    breathing_wave = []
    for i in range(len(raw_breathing)):
        start = max(0, i - 4)
        window = raw_breathing[start : i + 1]
        avg = sum(window) / len(window)
        breathing_wave.append(round(avg, 2))

    return {
        "ts_code": ts_code,
        "name": name,
        "dates": dates,
        "ohlc": ohlc,
        "volumes": volumes,
        "pct_chgs": pct_chgs,
        "overlays": overlays,
        "signal_markers": signal_markers,
        "kdj": {"k": kdj_k, "d": kdj_d, "j": kdj_j},
        "macd": {"dif": macd_dif, "dea": macd_dea, "hist": macd_hist},
        "brick": {"values": brick_values, "colors": brick_colors},
        "waves_sequence": waves_sequence,
        "kirin_sequence": kirin_sequence,
        "breathing_wave": breathing_wave,
    }


def get_signals(ts_code: str, days: int = 120) -> list[dict]:
    """获取战法信号列表"""
    from modules.strategies import detect_all_strategies

    signals = detect_all_strategies(ts_code, days=days)
    return _build_signals(signals)


def get_score(ts_code: str) -> dict:
    """获取综合评分"""
    from modules.screener import analyze_stock

    score = analyze_stock(ts_code)
    return _build_score(score)


# ── 内部辅助 ──


def _get_stock_name(ts_code: str) -> str:
    try:
        from modules.database import get_connection

        with get_connection() as conn:
            row = conn.execute("SELECT name FROM stock_basic WHERE ts_code=?", (ts_code,)).fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return ts_code


def _build_indicators(result, diagnosis) -> dict:
    return {
        "kdj": {"k": result.k, "d": result.d, "j": result.j},
        "macd": {
            "dif": result.dif,
            "dea": result.dea,
            "hist": result.macd_hist,
            "veto": getattr(result, "macd_veto", False),
            "gold_cross": getattr(result, "macd_gold_cross", False),
            "dead_cross": getattr(result, "macd_dead_cross", False),
            "top_divergence": getattr(result, "is_top_divergence", False),
            "bottom_divergence": getattr(result, "is_bottom_divergence", False),
        },
        "bbi": result.bbi,
        "rsi": {"rsi6": result.rsi6, "rsi12": result.rsi12, "rsi24": result.rsi24},
        "bollinger": {
            "mid": result.boll_mid,
            "upper": result.boll_upper,
            "lower": result.boll_lower,
            "width": result.boll_width,
            "position": result.boll_position,
        },
        "ma": {
            "ma5": result.ma5,
            "ma10": result.ma10,
            "ma20": result.ma20,
            "ma60": result.ma60,
            "high_52w": result.high_52w,
            "high_52w_dist": result.high_52w_dist,
        },
        "wr": {"wr5": result.wr5, "wr10": result.wr10},
        "vol_ratio": result.vol_ratio,
        "double_line": {
            "white": result.zg_white,
            "yellow": result.dg_yellow,
            "is_gold_cross": result.is_gold_cross,
            "is_dead_cross": result.is_dead_cross,
        },
        "brick": {
            "value": result.brick_value,
            "trend": result.brick_trend,
            "count": result.brick_count,
            "trend_up": result.brick_trend_up,
            "is_fanbao": result.is_fanbao,
        },
        "dmi": {"plus": result.dmi_plus, "minus": result.dmi_minus, "adx": result.adx},
        "signal": result.signal.value if hasattr(result.signal, "value") else str(result.signal),
        "sell_score": result.sell_score,
        "sell_items": result.sell_items or {},
    }


def _build_waves(wave_data) -> dict | None:
    if not wave_data:
        return None
    return {
        "wave": wave_data.get("wave", "未知"),
        "confidence": wave_data.get("confidence", 0),
        "suggestion": wave_data.get("b1_suggestion", ""),
    }


def _build_kirin(kirin_data) -> dict | None:
    if not kirin_data:
        return None
    return {
        "phase": kirin_data.get("stage", "未知"),
        "sub_type": kirin_data.get("sub_type", "未知"),
        "confidence": kirin_data.get("confidence", 0),
        "operation": kirin_data.get("operation", ""),
    }


def _build_signals(signals) -> list[dict]:
    result = []
    priority_map = {3: "CRITICAL", 2: "OPPORTUNITY", 1: "OBSERVE"}
    for s in signals[:20]:
        p = s.priority
        if isinstance(p, int):
            p_name = priority_map.get(p, "OBSERVE")
        elif hasattr(p, "name"):
            p_name = p.name
        else:
            p_name = str(p)
        result.append(
            {
                "strategy": s.strategy.value,
                "date": s.trade_date,
                "confidence": s.confidence,
                "action": s.action,
                "description": s.description,
                "priority": p_name,
                "target_price": s.target_price,
                "stop_loss": s.stop_loss,
            }
        )
    return result


def _build_score(score) -> dict:
    return {
        "total": score.score,
        "b1_score": score.b1_score,
        "trend_score": score.trend_score,
        "volume_score": score.volume_score,
        "risk_score": score.risk_score,
        "rating": score.rating,
        "reasons": score.reasons,
        "warnings": score.warnings,
    }


def _build_diagnosis(diagnosis) -> dict:
    return {
        "price_position": getattr(diagnosis, "price_position", ""),
        "trend_status": getattr(diagnosis, "trend_status", ""),
        "sell_score": getattr(diagnosis, "sell_score", 0),
        "sell_score_desc": getattr(diagnosis, "sell_score_desc", ""),
        "kirin_phase": getattr(diagnosis, "kirin_phase", ""),
        "bull_rope": getattr(diagnosis, "bull_rope_status", ""),
        "sandglass_score": getattr(diagnosis, "sandglass_score", 0),
        "is_centipede": getattr(diagnosis, "is_centipede", False),
        "risk_level": getattr(diagnosis, "risk_level", "UNKNOWN"),
        "recommendation": getattr(diagnosis, "recommendation", ""),
    }
# ── 股票搜索（代码 / 中文名称 / 拼音）──

# 索引缓存：首次搜索时懒构建，TTL 到期后自动重建
_SEARCH_INDEX: list[dict] | None = None
_SEARCH_INDEX_TS: float = 0.0
_SEARCH_INDEX_TTL = 30 * 60  # 30 分钟
_SEARCH_PY_ENABLED: bool | None = None


def _pinyin_fields(name: str) -> tuple[str, str]:
    """返回 (全拼, 首字母)；pypinyin 不可用时返回空串"""
    global _SEARCH_PY_ENABLED
    if _SEARCH_PY_ENABLED is False:
        return "", ""
    try:
        from pypinyin import Style, lazy_pinyin

        syllables = lazy_pinyin(name, style=Style.NORMAL)
        full = "".join(syllables).lower()
        initials = "".join(s[0] for s in syllables if s).lower()
        _SEARCH_PY_ENABLED = True
        return full, initials
    except Exception as e:
        _SEARCH_PY_ENABLED = False
        logger.warning("pypinyin 不可用，股票搜索降级为「代码 + 中文名称」匹配: %s", e)
        return "", ""


def _build_search_index() -> list[dict]:
    """从 stock_basic 构建搜索索引（代码 / 名称 / 全拼 / 首字母）"""
    from modules.database import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ts_code, name, industry, market FROM stock_basic WHERE name IS NOT NULL AND name != ''"
        ).fetchall()

    index: list[dict] = []
    for row in rows:
        ts_code = row["ts_code"] if "ts_code" in row.keys() else row[0]
        name = row["name"] if "name" in row.keys() else row[1]
        industry = row["industry"] if "industry" in row.keys() else row[2]
        market = row["market"] if "market" in row.keys() else row[3]
        full, initials = _pinyin_fields(name or "")
        index.append(
            {
                "ts_code": ts_code,
                "name": name or "",
                "industry": industry or "",
                "market": market or "",
                "code6": (ts_code or "").split(".")[0],
                "full": full,
                "initials": initials,
            }
        )
    return index


def _get_search_index() -> list[dict]:
    global _SEARCH_INDEX, _SEARCH_INDEX_TS
    import time

    now = time.time()
    if _SEARCH_INDEX is None or now - _SEARCH_INDEX_TS > _SEARCH_INDEX_TTL:
        _SEARCH_INDEX = _build_search_index()
        _SEARCH_INDEX_TS = now
        logger.info("股票搜索索引已构建: %d 条", len(_SEARCH_INDEX))
    return _SEARCH_INDEX


def invalidate_search_index() -> None:
    """外部（如 sync_stock_basic 之后）主动失效索引"""
    global _SEARCH_INDEX
    _SEARCH_INDEX = None


def search_stocks(q: str, limit: int = 10) -> list[dict]:
    """按关键词搜索股票

    匹配优先级：代码前缀 > 名称前缀 > 拼音首字母前缀 > 全拼前缀 > 名称子串 > 全拼子串
    """
    keyword = (q or "").strip().lower()
    if not keyword:
        return []

    limit = max(1, min(int(limit), 50))
    index = _get_search_index()

    buckets: dict[str, list[dict]] = {
        "code_prefix": [],
        "name_prefix": [],
        "initials_prefix": [],
        "full_prefix": [],
        "name_substr": [],
        "full_substr": [],
    }

    for item in index:
        code6 = item["code6"]
        name = item["name"].lower()
        full = item["full"]
        initials = item["initials"]

        if code6.startswith(keyword) or item["ts_code"].lower().startswith(keyword):
            buckets["code_prefix"].append(item)
        elif name.startswith(keyword):
            buckets["name_prefix"].append(item)
        elif initials and initials.startswith(keyword):
            buckets["initials_prefix"].append(item)
        elif full and full.startswith(keyword):
            buckets["full_prefix"].append(item)
        elif keyword in name:
            buckets["name_substr"].append(item)
        elif full and keyword in full:
            buckets["full_substr"].append(item)

    results: list[dict] = []
    for match_type, items in buckets.items():
        items.sort(key=lambda x: x["ts_code"])
        for item in items:
            if len(results) >= limit:
                break
            results.append(
                {
                    "ts_code": item["ts_code"],
                    "name": item["name"],
                    "industry": item["industry"],
                    "market": item["market"],
                    "match_type": match_type,
                }
            )
        if len(results) >= limit:
            break

    return results
