"""
选股与择时系统
实现 Z哥 的"三最原则"和每日五步工作流
"""

import sqlite3
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import os

from .database import get_connection, get_db_path, get_db_connection
from .indicators import DailyData, calculate_ma

# 并行化阈值：小于此数量不启用多进程（启动开销不值得）
_PARALLEL_THRESHOLD = 50


@dataclass
class StockScore:
    """股票评分"""

    ts_code: str
    name: str = ""
    score: float = 0  # 综合评分 0-100
    b1_score: float = 0  # B1买点评分
    trend_score: float = 0  # 趋势评分
    volume_score: float = 0  # 量价评分
    risk_score: float = 0  # 风险评分
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rating(self) -> str:
        """评级"""
        if self.score >= 80:
            return "★★★★★ 强烈推荐"
        elif self.score >= 65:
            return "★★★★☆ 推荐"
        elif self.score >= 50:
            return "★★★☆☆ 可关注"
        elif self.score >= 35:
            return "★★☆☆☆ 谨慎"
        else:
            return "★☆☆☆☆ 不推荐"


@dataclass
class MarketStatus:
    """大盘状态"""

    trade_date: str
    is_trading: bool = True  # 是否可交易
    market_direction: str = "NEUTRAL"  # LONG/NEUTRAL/SHORT
    market_strength: float = 0  # 0-100
    reasons: list[str] = field(default_factory=list)


def get_all_stocks() -> list[dict]:
    """获取所有股票基本信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ts_code, name, industry, market
        FROM stock_basic
        WHERE market IN ('主板', '创业板', '科创板')
        ORDER BY ts_code
    """)
    stocks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stocks


def get_recent_klines(ts_code: str, days: int = 60) -> list[DailyData]:
    """获取近期K线数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
        FROM daily_kline
        WHERE ts_code = ?
        ORDER BY trade_date DESC
        LIMIT ?
    """,
        (ts_code, days),
    )

    rows = cursor.fetchall()
    conn.close()

    # 转换为升序
    data_list = []
    for i, row in enumerate(reversed(rows)):
        prev_close = rows[len(rows) - i - 2]["close"] if i < len(rows) - 1 else row["close"]
        data_list.append(
            DailyData(
                ts_code=row["ts_code"],
                trade_date=row["trade_date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                vol=row["vol"],
                amount=row["close"] * row["vol"],
                pct_chg=row["pct_chg"],
                prev_close=prev_close,
            )
        )

    return data_list


def calculate_vol_ma(vols: list[float], period: int) -> float:
    """计算量能均线（复用 calculate_ma 逻辑）"""
    return calculate_ma(vols, period)


def calculate_kdj(klines: list, period: int = 9) -> tuple[float, float, float]:
    """计算 KDJ 指标，支持 DailyData 列表或 dict 列表"""
    from .indicators import calculate_kdj as canonical_kdj

    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)
    return canonical_kdj(klines, period)


def calculate_bbi(klines: list) -> float:
    """计算 BBI 指标，支持 DailyData 列表或 dict 列表"""
    from .indicators import calculate_bbi as canonical_bbi

    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)
    return canonical_bbi(klines)


def _dict_to_daily(klines: list[dict]) -> list[DailyData]:
    """将 dict 格式 K 线转为 DailyData 列表"""
    result = []
    for i, k in enumerate(klines):
        prev_close = klines[i - 1]["close"] if i > 0 else k["close"]
        result.append(
            DailyData(
                ts_code=k["ts_code"],
                trade_date=k["trade_date"],
                open=k["open"],
                high=k["high"],
                low=k["low"],
                close=k["close"],
                vol=k["vol"],
                amount=k.get("amount", k["close"] * k["vol"]),
                pct_chg=k.get("pct_chg", 0),
                prev_close=prev_close,
            )
        )
    return result


def is_perfect_pattern(klines: list) -> tuple[bool, list[str]]:
    """
    判断是否完美图形

    完美图形条件:
    1. BBI之上
    2. 缩量整理
    3. 均线多头（可选）
    4. 非高位
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)

    if len(klines) < 30:
        return False, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)
    closes = [k.close for k in klines]
    vols = [k.vol for k in klines]

    reasons = []
    warnings = []

    # 1. BBI之上
    if today.close > bbi:
        reasons.append("价格在BBI之上")
    else:
        warnings.append("价格在BBI下方")

    # 2. 缩量整理
    ma5_vol = calculate_vol_ma(vols, 5)
    today_vol = today.vol
    if today_vol < ma5_vol * 0.7:
        reasons.append("缩量整理")
    elif today_vol > ma5_vol * 1.5:
        warnings.append("放量突破，需观察")

    # 3. 均线多头
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    if ma5 > ma10 > ma20:
        reasons.append("均线多头排列")
    elif ma5 < ma10:
        warnings.append("均线空头")

    # 4. 非高位（距历史高点跌幅充分）
    max_high = max(k.high for k in klines[-60:])
    drop_ratio = (max_high - today.close) / max_high
    if drop_ratio > 0.3:
        reasons.append(f"相对高点回调{drop_ratio * 100:.0f}%")
    elif drop_ratio < 0.1:
        warnings.append("接近历史高位")

    # 综合判断
    is_perfect = len(reasons) >= 2 and len(warnings) == 0

    return is_perfect, reasons


def score_b1_opportunity(klines: list) -> tuple[float, list[str]]:
    """
    评估B1买点机会

    返回: (评分0-100, 原因列表)
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)

    if len(klines) < 20:
        return 0, ["数据不足"]

    today = klines[-1]
    k, d, j = calculate_kdj(klines)
    bbi = calculate_bbi(klines)
    closes = [k.close for k in klines]
    vols = [k.vol for k in klines]

    score = 0
    reasons = []

    # J值评分（核心）
    if j < -15:
        score += 35
        reasons.append(f"J值极低: {j:.2f}")
    elif j < -10:
        score += 25
        reasons.append(f"J值低位: {j:.2f}")
    elif j < 0:
        score += 15
        reasons.append(f"J值: {j:.2f}")

    # 缩量回调加分
    if today.vol < calculate_vol_ma(vols, 5) * 0.6:
        score += 20
        reasons.append("缩量回调")

    # BBI下方（低位）
    if today.close < bbi:
        score += 15
        reasons.append("BBI下方低位")

    # 价格在合理区间
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)
    if ma20 < today.close < ma60:
        score += 15
        reasons.append("中期均线区间")

    # 风险提示
    if j > 0:
        score -= 10
    if today.close > bbi * 1.05:
        score -= 15

    return max(0, min(100, score)), reasons


def score_trend(klines: list) -> tuple[float, str]:
    """
    评估趋势

    返回: (评分0-100, 趋势方向)
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)

    if len(klines) < 20:
        return 50, "震荡"

    closes = [k.close for k in klines]
    today = klines[-1]
    bbi = calculate_bbi(klines)

    ma5 = calculate_ma(closes, 5)
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)

    # 趋势判断
    if ma5 > ma20 > ma60 and today.close > bbi:
        direction = "上升"
        score = 80 if today.pct_chg > 0 else 70
    elif ma5 < ma20 < ma60 and today.close < bbi:
        direction = "下降"
        score = 30
    else:
        direction = "震荡"
        score = 50

    # 短期动能
    if len(klines) >= 5:
        recent_pct = sum(k.pct_chg for k in klines[-5:])
        if recent_pct > 10:
            score += 10
        elif recent_pct < -10:
            score -= 10

    # 牛绳理论
    try:
        from .indicators import detect_bull_rope

        rope = detect_bull_rope(klines)
        if rope.get("status") == "牵牛":
            score = min(100, score + 10)
            direction += " 牵牛"
        elif rope.get("status") == "牛绳断":
            score = max(0, score - 20)
            direction += " 牛绳断"
        elif rope.get("status") == "金叉":
            score = min(100, score + 15)
            direction += " 牛绳金叉"
        elif rope.get("status") == "死叉":
            score = max(0, score - 25)
            direction += " 牛绳死叉"
    except Exception:
        pass

    return max(0, min(100, score)), direction


def score_volume_pattern(klines: list) -> tuple[float, list[str]]:
    """
    评估量价形态
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)

    if len(klines) < 10:
        return 50, ["数据不足"]

    today = klines[-1]
    vols = [k.vol for k in klines]
    vol_ma5 = calculate_vol_ma(vols, 5)

    score = 50
    reasons = []

    # 量比
    vol_ratio = today.vol / vol_ma5
    if vol_ratio >= 2:
        score += 20
        reasons.append(f"倍量(量比{vol_ratio:.1f}x)")
    elif vol_ratio >= 1.5:
        score += 10
        reasons.append("放量")
    elif vol_ratio <= 0.5:
        score += 10
        reasons.append("缩量")
    else:
        score -= 5
        reasons.append("量能正常")

    # 涨跌配合
    if today.pct_chg > 3 and vol_ratio > 1.2:
        score += 15
        reasons.append("价涨量增(攻击形态)")
    elif today.pct_chg < -3 and vol_ratio > 1.2:
        score -= 15
        reasons.append("价跌量增(出货嫌疑)")

    return max(0, min(100, score)), reasons


def score_risk(klines: list) -> tuple[float, list[str]]:
    """
    评估风险
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)

    if len(klines) < 20:
        return 50, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)

    score = 100  # 初始100分，越高越安全
    warnings = []

    # 高位风险
    max_high = max(k.high for k in klines[-60:])
    drop_ratio = (max_high - today.close) / max_high
    if drop_ratio < 0.1:
        score -= 30
        warnings.append("接近历史高位")
    elif drop_ratio < 0.2:
        score -= 15
        warnings.append("相对高位")

    # 跌破BBI风险
    if today.close < bbi:
        score -= 20
        warnings.append("跌破BBI")

    # 放量阴线风险
    for i in range(min(5, len(klines) - 1)):
        k = klines[-(i + 1)]
        prev = klines[-(i + 2)] if i < len(klines) - 2 else None
        if prev and k.close < prev.close and k.vol > prev.vol * 1.5:
            score -= 10
            warnings.append("近期有放量阴线")
            break

    # 连续下跌
    recent_3_drop = sum(1 for k in klines[-3:] if k.close < k.prev_close)
    if recent_3_drop >= 3:
        score -= 15
        warnings.append("连续3天下跌")

    # 蜈蚣图检测（呼吸紊乱 = 高风险）
    try:
        from .indicators import detect_centipede_pattern

        centipede = detect_centipede_pattern(klines)
        if centipede.get("is_centipede"):
            score -= 30
            warnings.append(f"蜈蚣图({centipede['score']:.0f}分)")
            warnings.append("检测到蜈蚣图风险，建议观望")
    except Exception:
        pass

    return max(0, min(100, score)), warnings


def analyze_stock(ts_code: str, klines: list[DailyData] | None = None) -> StockScore:
    """
    综合评分单只股票
    """
    if klines is None:
        klines = get_recent_klines(ts_code, 150)

    if not klines:
        return StockScore(ts_code=ts_code)

    klines[-1]

    # 获取股票名称
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM stock_basic WHERE ts_code = ?", (ts_code,))
    row = cursor.fetchone()
    name = row["name"] if row else ts_code
    conn.close()

    # 计算各项评分
    b1_score, b1_reasons = score_b1_opportunity(klines)
    trend_score, trend_dir = score_trend(klines)
    volume_score, volume_reasons = score_volume_pattern(klines)
    risk_score, risk_warnings = score_risk(klines)

    # ========== P2 指标：三波理论 + 麒麟会 ==========
    wave_stage = "未知"
    kirin_stage = "未知"
    try:
        from .indicators import detect_three_waves, detect_kirin_stage

        wave = detect_three_waves(klines)
        wave_stage = wave["wave"]
        if wave_stage == "建仓波" and wave["confidence"] >= 0.5:
            b1_reasons.append(f"三波·建仓波(conf={wave['confidence']})")
        elif wave_stage == "拉升波":
            b1_reasons.append(f"三波·拉升波(conf={wave['confidence']})→等回调")
        elif wave_stage == "冲刺波":
            risk_warnings.append(f"三波·冲刺波(conf={wave['confidence']})→不看")
            risk_score = max(0, risk_score - 20)

        kirin = detect_kirin_stage(klines)
        kirin_stage = kirin["stage"]
        if kirin_stage == "吸筹" and kirin["confidence"] >= 0.5:
            b1_reasons.append(f"麒麟会·吸筹({kirin['sub_type']}, conf={kirin['confidence']})")
        elif kirin_stage == "拉升":
            b1_reasons.append(f"麒麟会·拉升({kirin['sub_type']})→不追")
        elif kirin_stage == "派发":
            risk_warnings.append(f"麒麟会·派发({kirin['sub_type']})→准备走人")
            risk_score = max(0, risk_score - 30)
        elif kirin_stage == "回落":
            risk_warnings.append(f"麒麟会·回落({kirin['sub_type']})→不抄底")
            risk_score = max(0, risk_score - 15)
    except Exception:
        pass

    # ========== P3 指标：沙漏评分 ==========
    sandglass_score = 0
    sandglass_is_perfect = False
    try:
        from .indicators import calculate_sandglass_score

        sg = calculate_sandglass_score(klines)
        sandglass_score = sg.get("score", 0)
        sandglass_is_perfect = sg.get("is_perfect", False)
        if sandglass_is_perfect:
            b1_reasons.append(f"沙漏完美图形({sandglass_score:.0f}分)")
    except Exception:
        pass

    # 综合评分（加权平均）
    # B1机会 30% + 趋势 25% + 量价 25% + 风险 20%
    total_score = b1_score * 0.3 + trend_score * 0.25 + volume_score * 0.25 + risk_score * 0.2

    # 完美图形额外加分
    is_perfect, perfect_reasons = is_perfect_pattern(klines)
    if is_perfect:
        total_score = min(100, total_score * 1.1)
        b1_reasons.extend(perfect_reasons)

    # 三波/麒麟会加权调整
    if wave_stage == "建仓波":
        total_score = min(100, total_score * 1.05)
    elif wave_stage == "冲刺波" or kirin_stage == "派发":
        total_score = max(0, total_score * 0.7)
    elif kirin_stage == "吸筹":
        total_score = min(100, total_score * 1.08)

    # 沙漏完美图形加分
    if sandglass_is_perfect:
        total_score = min(100, total_score + 10)

    score = StockScore(
        ts_code=ts_code,
        name=name,
        score=round(total_score, 1),
        b1_score=round(b1_score, 1),
        trend_score=round(trend_score, 1),
        volume_score=round(volume_score, 1),
        risk_score=round(risk_score, 1),
        reasons=b1_reasons + volume_reasons,
        warnings=risk_warnings,
    )

    return score


# ==================== 并行化 Worker ====================


def _daily_to_dict(klines: list[DailyData]) -> list[dict]:
    """将 DailyData 列表转为符合战法检测需要的 dict 格式列表"""
    result = []
    for i, k in enumerate(klines):
        prev_close = klines[i - 1].close if i > 0 else k.close
        prev_vol = klines[i - 1].vol if i > 0 else k.vol

        result.append(
            {
                "ts_code": k.ts_code,
                "trade_date": k.trade_date,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "vol": k.vol,
                "amount": k.amount,
                "pct_chg": k.pct_chg,
                "prev_close": prev_close,
                "prev_vol": prev_vol,
                "is_rise": k.close > prev_close,
                "is_beidou": k.vol >= prev_vol * 2,
                "is_suoliang": k.vol <= prev_vol * 0.5 if prev_vol > 0 else False,
                "is_yinxian": k.close < prev_close,
                "is_fangliang_yinxian": k.close < prev_close and k.vol > prev_vol * 1.5,
            }
        )
    return result


def _analyze_worker(ts_code: str) -> tuple[str, list[DailyData], StockScore] | None:
    """
    并行 worker：评分单只股票
    必须在模块顶层定义，以便 ProcessPoolExecutor 可以 pickle
    返回: (ts_code, klines, score) 或 None
    """
    klines = get_recent_klines(ts_code, 150)
    if not klines or len(klines) < 30:
        return None
    score = analyze_stock(ts_code, klines)
    return ts_code, klines, score


def _filter_stock(result: tuple[str, list[DailyData], StockScore], criteria: str) -> bool:
    """
    判断单只股票是否满足选股条件
    在主进程串行执行（筛选逻辑快，不需要并行）
    """
    ts_code, klines, score = result

    # 蜈蚣图硬过滤：呼吸紊乱的票直接排除
    try:
        from .indicators import detect_centipede_pattern

        cp = detect_centipede_pattern(klines)
        if cp.get("is_centipede"):
            return False
    except Exception:
        pass

    # 沙漏评分硬过滤：< 50 分的票质量太差（回测验证：沙漏≥69 的票胜率显著更高）
    try:
        from .indicators import calculate_sandglass_score

        sg = calculate_sandglass_score(klines)
        if sg.get("score", 0) < 50:
            return False
    except Exception:
        pass

    # 基础选股策略
    if criteria == "b1" and score.b1_score >= 50:
        return True
    elif criteria == "perfect" and score.score >= 65:
        return True
    elif criteria == "oversold" and score.trend_score <= 40:
        return True
    elif criteria == "breakout" and score.volume_score >= 70:
        return True

    # 高级选股策略（基于战法检测）
    elif criteria == "super_b1":
        from .strategies import detect_sb1

        for i in range(max(10, len(klines) - 5), len(klines)):
            sig = detect_sb1(klines, i)
            if sig:
                score.warnings.append(f"超级B1 J={sig.details.get('j', 0):.1f}")
                return True
    elif criteria == "changan":
        from .strategies import detect_changan

        for i in range(max(3, len(klines) - 5), len(klines)):
            sig = detect_changan(klines, i)
            if sig:
                score.reasons.append("长安战法 胜率75%")
                return True
    elif criteria == "b2_breakout":
        from .strategies import detect_b2

        for i in range(max(15, len(klines) - 5), len(klines)):
            sig = detect_b2(klines, i)
            if sig:
                score.reasons.append(f"B2突破 涨{sig.details.get('pct_chg', 0):.1f}%")
                return True
    elif criteria == "b3_consensus":
        from .strategies import detect_b3

        for i in range(max(20, len(klines) - 5), len(klines)):
            sig = detect_b3(klines, i)
            if sig:
                score.reasons.append("B3分歧转一致")
                return True

    # P2 指标选股策略
    elif criteria in ("build_wave", "xishou", "safe"):
        from .indicators import detect_three_waves, detect_kirin_stage

        wave = detect_three_waves(klines)
        kirin = detect_kirin_stage(klines)

        if criteria == "build_wave" and wave["wave"] == "建仓波" and wave["confidence"] >= 0.5:
            score.reasons.append(f"建仓波(conf={wave['confidence']})")
            return True
        elif criteria == "xishou" and kirin["stage"] == "吸筹" and kirin["confidence"] >= 0.5:
            score.reasons.append(f"吸筹({kirin['sub_type']}, conf={kirin['confidence']})")
            return True
        elif criteria == "safe":
            is_safe = wave["wave"] != "冲刺波" and kirin["stage"] not in ("派发", "回落")
            if is_safe:
                score.reasons.append(f"安全：{wave['wave']}+{kirin['stage']}")
                return True

    # P3 指标选股策略
    elif criteria in ("bull_rope", "sandglass_perfect", "volume_ratio_super"):
        if criteria == "bull_rope":
            from .indicators import detect_bull_rope

            daily_klines = _dict_to_daily(klines)
            rope = detect_bull_rope(daily_klines)
            if rope.get("status") == "牵牛" and rope.get("is_bullish"):
                score.reasons.append(f"牛绳·牵牛(gap={rope['gap_pct']}%)")
                return True
        elif criteria == "sandglass_perfect":
            from .indicators import calculate_sandglass_score

            daily_klines = _dict_to_daily(klines)
            sg = calculate_sandglass_score(daily_klines)
            if sg.get("is_perfect") or sg.get("score", 0) >= 80:
                score.reasons.append(f"沙漏完美图形({sg['score']}分)")
                return True
        elif criteria == "volume_ratio_super":
            from .indicators import detect_volume_ratio_strategy

            daily_klines = _dict_to_daily(klines)
            vr = detect_volume_ratio_strategy(daily_klines)
            if vr.get("action") == "立即买" or vr.get("scenario") in ("超级攻击", "攻击日", "单向拉升"):
                score.reasons.append(f"量比战法·{vr['scenario']}(量比={vr['vol_ratio']})")
                return True

    return False


def screen_stocks(
    criteria: str = "b1", max_stocks: int = 0, max_workers: int = 0, use_parallel: bool = True
) -> list[StockScore]:
    """
    选股筛选（支持多进程并行）

    criteria:
    - "b1": B1买点机会
    - "perfect": 完美图形
    - "breakout": 突破形态
    - "oversold": 超跌反弹
    - "super_b1": 超级B1（放量下跌+缩量企稳+J负值）
    - "changan": 长安战法（B1+放量长阳+缩半量）
    - "b2_breakout": B2突破（涨幅≥4%+放量+J<55+无上影线）
    - "b3_consensus": B3分歧转一致
    - "build_wave": 建仓波（三波理论·建仓波）
    - "xishou": 吸筹阶段（麒麟会·吸筹）
    - "safe": 安全选股（非冲刺波 + 非派发/回落）
    - "bull_rope": 牛绳牵牛形态（白在黄上，且白线向上）
    - "sandglass_perfect": 沙漏完美图形（评分>=80）
    - "volume_ratio_super": 量比战法（立即买或强势攻击场景）

    max_stocks: 最大扫描数量，0=全量（默认500只性能保护）
    max_workers: 并行进程数，0=自动（CPU核心数）
    use_parallel: 是否启用多进程并行（<50只时自动关闭）

    返回：满足条件的 StockScore 列表（按评分降序）
    """
    stocks = get_all_stocks()
    limit = max_stocks if max_stocks > 0 else 500
    stocks = stocks[:limit]

    results: list[StockScore] = []

    # 小数据量时禁用并行（启动开销不值得）
    if not use_parallel or len(stocks) < _PARALLEL_THRESHOLD:
        # 串行模式
        for stock in stocks:
            result = _analyze_worker(stock["ts_code"])
            if result and _filter_stock(result, criteria):
                results.append(result[2])
    else:
        # 并行模式：只并行 analyze_stock，筛选在主进程串行
        workers = max_workers or os.cpu_count() or 4
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            ts_codes = [s["ts_code"] for s in stocks]

            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_map = {executor.submit(_analyze_worker, ts_code): ts_code for ts_code in ts_codes}
                for future in as_completed(future_map):
                    result = future.result()
                    if result and _filter_stock(result, criteria):
                        results.append(result[2])
        except Exception:
            # 并行失败回退到串行
            for stock in stocks:
                result = _analyze_worker(stock["ts_code"])
                if result and _filter_stock(result, criteria):
                    results.append(result[2])

    # 按评分排序
    results.sort(key=lambda x: x.score, reverse=True)
    return results


def get_market_status() -> MarketStatus:
    """
    获取大盘状态（简化版，用主要指数代替）
    """
    today = datetime.now().strftime("%Y%m%d")

    # 获取沪深300成分股简单评估
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ts_code FROM stock_basic
        WHERE market IN ('主板')
        LIMIT 100
    """)
    stocks = [row["ts_code"] for row in cursor.fetchall()]

    rise_count = 0
    total_count = 0

    for ts_code in stocks[:20]:
        cursor.execute(
            """
            SELECT pct_chg FROM daily_kline
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT 1
        """,
            (ts_code,),
        )
        row = cursor.fetchone()
        if row:
            total_count += 1
            if row["pct_chg"] > 0:
                rise_count += 1

    conn.close()

    # 计算涨跌家数比
    if total_count > 0:
        rise_ratio = rise_count / total_count
    else:
        rise_ratio = 0.5

    # 大盘状态判断
    if rise_ratio >= 0.6:
        direction = "LONG"
        strength = 75
        reasons = ["上涨家数占优", "市场活跃"]
    elif rise_ratio <= 0.4:
        direction = "SHORT"
        strength = 25
        reasons = ["下跌家数较多", "注意风险"]
    else:
        direction = "NEUTRAL"
        strength = 50
        reasons = ["多空均衡", "观望为主"]

    return MarketStatus(
        trade_date=today, is_trading=True, market_direction=direction, market_strength=strength, reasons=reasons
    )


def format_stock_score(score: StockScore) -> str:
    """格式化股票评分"""
    return f"""
{score.ts_code} {score.name}
{"=" * 50}
综合评分: {score.score:.1f}/100 {score.rating}
{"=" * 50}
B1买点评分: {score.b1_score:.1f}
趋势评分: {score.trend_score:.1f}
量价评分: {score.volume_score:.1f}
风险评分: {score.risk_score:.1f}

利好因素:
{chr(10).join(f"  + {r}" for r in score.reasons) if score.reasons else "  无"}

风险提示:
{chr(10).join(f"  ! {w}" for w in score.warnings) if score.warnings else "  无"}
"""


def daily_workflow() -> dict[str, Any]:
    """
    每日五步工作流

    返回分析结果
    """
    print("=" * 60)
    print("Z哥 每日五步工作流")
    print("=" * 60)

    # Step 1: 择时（1分钟）
    print("\n[Step 1] 择时判断")
    market = get_market_status()
    print(f"大盘状态: {market.market_direction}")
    print(f"市场强度: {market.market_strength}/100")
    for reason in market.reasons:
        print(f"  - {reason}")

    if market.market_direction == "SHORT":
        print("  => 建议: 轻仓或空仓观望")

    # Step 2: 定策略（2分钟）
    print("\n[Step 2] 策略制定")
    if market.market_direction == "LONG":
        print("  => 多头策略: 主攻")
    elif market.market_direction == "SHORT":
        print("  => 空头策略: 防守")
    else:
        print("  => 中性策略: 观望/底仓不动")

    # Step 3: 选股（5分钟）
    print("\n[Step 3] 选股")
    b1_stocks = screen_stocks("b1")[:5]
    perfect_stocks = screen_stocks("perfect")[:5]

    print("B1买点机会 (TOP 5):")
    for i, s in enumerate(b1_stocks[:5], 1):
        print(f"  {i}. {s.ts_code} {s.name} 评分:{s.score:.0f}")

    print("\n完美图形 (TOP 5):")
    for i, s in enumerate(perfect_stocks[:5], 1):
        print(f"  {i}. {s.ts_code} {s.name} 评分:{s.score:.0f}")

    # Step 4: 执行计划
    print("\n[Step 4] 执行计划")
    print("  - 严格按条件执行，不临时改变")
    print("  - 量比战法/B1/滴滴战法对应触发条件")

    # Step 5: 复盘准备
    print("\n[Step 5] 复盘准备")
    print("  - 记录今日操作")
    print("  - 明日重点关注股票")

    return {
        "market": market,
        "b1_opportunities": b1_stocks[:5],
        "perfect_patterns": perfect_stocks[:5],
    }


# ==================== 命令行工具 ====================


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Z哥 选股系统")
    parser.add_argument(
        "action", choices=["score", "screen", "workflow"], help="操作: score=单股评分, screen=选股, workflow=每日工作流"
    )
    parser.add_argument("--ts_code", help="股票代码")
    parser.add_argument(
        "--criteria",
        default="b1",
        choices=[
            "b1",
            "perfect",
            "breakout",
            "oversold",
            "super_b1",
            "changan",
            "b2_breakout",
            "b3_consensus",
            "build_wave",
            "xishou",
            "safe",
        ],
        help="选股条件",
    )
    parser.add_argument("--limit", type=int, default=10, help="返回数量")
    parser.add_argument("--max-stocks", type=int, default=0, help="最大扫描数量(0=全量)")
    parser.add_argument("--workers", type=int, default=0, help="并行进程数，0=自动（CPU核心数）")
    parser.add_argument("--no-parallel", action="store_true", help="禁用多进程并行")

    args = parser.parse_args()

    if args.action == "score":
        if not args.ts_code:
            print("请指定股票代码: --ts_code 000001.SZ")
            return
        score = analyze_stock(args.ts_code)
        print(format_stock_score(score))

    elif args.action == "screen":
        import time

        start = time.time()
        results = screen_stocks(
            criteria=args.criteria,
            max_stocks=args.max_stocks,
            max_workers=args.workers,
            use_parallel=not args.no_parallel,
        )
        elapsed = time.time() - start
        mode = "并行" if not args.no_parallel and len(results) >= _PARALLEL_THRESHOLD else "串行"
        print(f"\n{'=' * 60}")
        print(f"选股结果 ({args.criteria}) 共{len(results)}只 | {mode}模式 | 耗时{elapsed:.1f}s")
        print(f"{'=' * 60}")
        for i, s in enumerate(results[: args.limit], 1):
            print(f"{i:2}. {s.ts_code} {s.name:<8} 评分:{s.score:5.1f}  B1:{s.b1_score:5.1f}")
            if s.reasons:
                print(f"    利好: {', '.join(s.reasons[:2])}")
            if s.warnings:
                print(f"    风险: {', '.join(s.warnings[:1])}")

    elif args.action == "workflow":
        daily_workflow()


if __name__ == "__main__":
    main()
