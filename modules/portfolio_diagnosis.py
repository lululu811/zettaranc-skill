"""
持股检查诊断模块
输入持仓代码，自动输出诊断报告

诊断维度：
1. 当前状态扫描（BBI/白线/黄线、KDJ、MACD）
2. 防卖飞评分（V1.4）
3. 出货信号扫描（S1/S2）
4. 战法匹配（B1/B2/B3/SB1 可买区间）
5. 止损/止盈位提示
"""

from typing import Any, Optional
from dataclasses import dataclass, field

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）

from .indicators import (
    analyze_stock,
    get_kline_data,
    calculate_sell_score,
    IndicatorResult,
    DailyData,
    detect_centipede_pattern,
    detect_bull_rope,
    calculate_sandglass_score,
    detect_kirin_stage,
)
from .strategies import detect_all_strategies, StrategyType


@dataclass
class DiagnosisReport:
    """持股诊断报告"""

    ts_code: str
    name: str = ""

    # 当前状态
    price: float = 0
    price_position: str = ""  # 相对BBI/白线/黄线的位置描述
    trend_status: str = ""  # 趋势状态

    # 指标快照
    kdj_j: float = 0
    macd_dif: float = 0
    macd_veto: bool = False
    bbi: float = 0
    white_line: float = 0
    yellow_line: float = 0
    is_gold_cross: bool = False
    is_dead_cross: bool = False

    # 防卖飞评分
    sell_score: int = 0  # 0-5
    sell_score_desc: str = ""
    sell_score_details: dict[str, bool] = field(default_factory=dict)

    # 出货信号
    exit_signals: list[dict[str, Any]] = field(default_factory=list)

    # 战法匹配（当前可买区间）
    buy_signals: list[dict[str, Any]] = field(default_factory=list)

    # 主力阶段
    kirin_phase: str = "UNKNOWN"
    kirin_confidence: float = 0

    # 蜈蚣图检测
    is_centipede: bool = False
    centipede_score: float = 0

    # 牛绳理论
    bull_rope_status: str = ""  # "牵牛" | "牛绳断" | "金叉" | "死叉"
    bull_rope_gap_pct: float = 0
    bull_rope_white_trend: str = ""

    # 沙漏评分
    sandglass_score: float = 0
    sandglass_is_perfect: bool = False

    # 止损/止盈建议
    stop_loss: float | None = None
    target_price: float | None = None

    # 综合建议
    recommendation: str = ""
    risk_level: str = "UNKNOWN"  # LOW/MEDIUM/HIGH/CRITICAL


def diagnose_stock(ts_code: str, days: int = 100) -> DiagnosisReport:
    """
    对单只股票进行完整持股诊断

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        DiagnosisReport 诊断报告
    """
    # 获取股票名称
    stock_info = get_stock_info_db(ts_code)
    name = stock_info.get("name", ts_code) if stock_info else ts_code

    # 指标分析
    indicators = analyze_stock(ts_code, days=days)

    # K线数据（用于防卖飞评分和麒麟会阶段）
    klines_daily = get_kline_data(ts_code, days=days)

    # 防卖飞评分
    sell_score, sell_desc, sell_details = calculate_sell_score(klines_daily)

    # 战法信号（最近30天内）
    all_signals = detect_all_strategies(ts_code, days=days)
    [s for s in all_signals if s.trade_date >= indicators.trade_date[:6] + "01" or True]

    # 分离买卖信号
    buy_signals = []
    exit_signals = []
    for s in all_signals[:20]:  # 只看最近20个
        sig_dict = {
            "strategy": s.strategy.value,
            "date": s.trade_date,
            "confidence": s.confidence,
            "description": s.description,
            "action": s.action,
        }
        if s.action == "SELL" or s.strategy in (StrategyType.S1, StrategyType.S2, StrategyType.S3):
            exit_signals.append(sig_dict)
        elif s.action == "BUY":
            buy_signals.append(sig_dict)

    # 麒麟会阶段
    kirin = detect_kirin_stage(klines_daily)

    # 蜈蚣图 / 牛绳 / 沙漏
    centipede = detect_centipede_pattern(klines_daily)
    bull_rope = detect_bull_rope(klines_daily)
    sandglass = calculate_sandglass_score(klines_daily)

    # 价格位置判断
    price_position = _judge_price_position(indicators, price=klines_daily[-1].close if klines_daily else 0)
    trend_status = _judge_trend(indicators)

    # 止损/止盈
    stop_loss, target = _calc_stop_target(indicators, buy_signals, exit_signals)

    # 综合建议
    recommendation, risk_level = _make_recommendation(
        indicators, sell_score, exit_signals, buy_signals, kirin, centipede, bull_rope, sandglass
    )

    return DiagnosisReport(
        ts_code=ts_code,
        name=name,
        price=klines_daily[-1].close if klines_daily else 0,
        price_position=price_position,
        trend_status=trend_status,
        kdj_j=indicators.j,
        macd_dif=indicators.dif,
        macd_veto=indicators.macd_veto,
        bbi=indicators.bbi,
        white_line=indicators.zg_white,
        yellow_line=indicators.dg_yellow,
        is_gold_cross=indicators.is_gold_cross,
        is_dead_cross=indicators.is_dead_cross,
        sell_score=sell_score,
        sell_score_desc=sell_desc,
        sell_score_details=sell_details,
        exit_signals=exit_signals[:5],
        buy_signals=buy_signals[:5],
        kirin_phase=kirin.get("stage", "UNKNOWN"),
        kirin_confidence=kirin.get("confidence", 0),
        is_centipede=centipede.get("is_centipede", False),
        centipede_score=centipede.get("score", 0),
        bull_rope_status=bull_rope.get("status", ""),
        bull_rope_gap_pct=bull_rope.get("gap_pct", 0),
        bull_rope_white_trend=bull_rope.get("white_trend", ""),
        sandglass_score=sandglass.get("score", 0),
        sandglass_is_perfect=sandglass.get("is_perfect", False),
        stop_loss=stop_loss,
        target_price=target,
        recommendation=recommendation,
        risk_level=risk_level,
    )


def get_stock_info_db(ts_code: str) -> dict[str, Any] | None:
    """获取股票基本信息（兼容直接运行）"""
    from .database import get_connection

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stock_basic WHERE ts_code = ?", (ts_code,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _daily_to_dict(klines: list[DailyData]) -> list[dict[str, Any]]:
    """将 DailyData 列表转为 strategies 模块需要的 dict 列表"""
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
                "is_beidou": k.vol >= prev_vol * 2 if prev_vol > 0 else False,
                "is_suoliang": k.vol <= prev_vol * 0.5 if prev_vol > 0 else False,
                "is_jiayin": k.close < k.open and k.close > prev_close,
                "is_yinxian": k.close < prev_close,
                "is_fangliang_yinxian": k.close < prev_close and k.vol > prev_vol * 1.5 if prev_vol > 0 else False,
            }
        )
    return result


def _judge_price_position(ind: IndicatorResult, price: float = 0) -> str:
    """判断价格相对位置"""
    parts = []
    if ind.bbi > 0 and price > 0:
        if price > ind.bbi * 1.05:
            parts.append("BBI之上")
        elif price < ind.bbi * 0.95:
            parts.append("BBI之下")
        else:
            parts.append("BBI附近")

    if ind.zg_white > 0 and ind.dg_yellow > 0 and price > 0:
        if price > ind.zg_white:
            parts.append("白线之上")
        else:
            parts.append("跌破白线")
        if price > ind.dg_yellow:
            parts.append("黄线之上")
        else:
            parts.append("跌破黄线")

    return " | ".join(parts) if parts else "数据不足"


def _judge_trend(ind: IndicatorResult) -> str:
    """判断趋势状态"""
    if ind.is_dead_cross:
        return "死叉（白线跌破黄线），趋势转空"
    if ind.is_gold_cross:
        return "金叉（白线上穿黄线），趋势转多"
    if ind.macd_veto:
        return "MACD一票否决，不宜买入"
    if ind.is_dif_positive:
        return "MACD多头区间，趋势向上"
    return "震荡整理"


def _calc_stop_target(ind: IndicatorResult, buy_signals: list[dict], exit_signals: list[dict]) -> tuple:
    """计算止损/止盈位"""
    stop = None
    target = None

    # 止损：最近白线位置 或 BBI
    if ind.zg_white > 0:
        stop = round(ind.zg_white * 0.98, 2)
    elif ind.bbi > 0:
        stop = round(ind.bbi * 0.97, 2)

    # 止盈：52周高点 或 BBI上方15%
    if ind.high_52w > 0:
        target = round(ind.high_52w * 0.95, 2)
    elif ind.bbi > 0:
        target = round(ind.bbi * 1.15, 2)

    return stop, target


def _make_recommendation(
    ind: IndicatorResult,
    sell_score: int,
    exit_signals: list[dict],
    buy_signals: list[dict],
    kirin: dict[str, Any],
    centipede: dict[str, Any] | None = None,
    bull_rope: dict[str, Any] | None = None,
    sandglass: dict[str, Any] | None = None,
) -> tuple:
    """生成综合建议和风险等级"""
    # 蜈蚣图：直接排除
    if centipede and centipede.get("is_centipede"):
        return f"蜈蚣图（{centipede['score']:.0f}分），呼吸紊乱，直接排除不碰", "CRITICAL"

    # 最高优先级：S1/S2/S3 出货信号
    if exit_signals:
        first_exit = exit_signals[0]
        if first_exit["strategy"] == "S1":
            return "S1逃顶信号出现，建议减仓或清仓", "CRITICAL"
        if first_exit["strategy"] == "S2":
            return "S2顶背离确认，建议无条件减仓", "CRITICAL"
        if first_exit["strategy"] == "S3":
            return "S3最后逃生窗口，建议离场", "HIGH"

    # MACD 一票否决
    if ind.macd_veto:
        return "MACD一票否决，当前不宜持有或加仓", "HIGH"

    # 死叉
    if ind.is_dead_cross:
        return "白线死叉黄线，趋势走坏，建议减仓", "HIGH"

    # 牛绳理论：牛绳断了
    if bull_rope and bull_rope.get("status") == "牛绳断":
        return "牛绳断了（白线跌破黄线），任何上涨都是反弹，建议减仓", "HIGH"

    # 防卖飞评分
    if sell_score >= 4:
        # 沙漏高分：额外确认
        if sandglass and sandglass.get("is_perfect"):
            return f"防卖飞评分{sell_score}/5 + 沙漏完美图形（{sandglass['score']:.0f}分），持股让利润飞", "LOW"
        return f"防卖飞评分{sell_score}/5，持股让利润飞", "LOW"
    elif sell_score >= 2:
        return f"防卖飞评分{sell_score}/5，关注破位信号", "MEDIUM"
    else:
        return f"防卖飞评分{sell_score}/5，弱势信号，考虑减仓", "HIGH"


def format_report(report: DiagnosisReport) -> str:
    """格式化诊断报告为文本"""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"持股诊断报告: {report.ts_code} {report.name}")
    lines.append(f"{'=' * 60}")
    lines.append(f"当前价格: {report.price:.2f}")
    lines.append(f"价格位置: {report.price_position}")
    lines.append(f"趋势状态: {report.trend_status}")
    lines.append("")
    lines.append(f"KDJ: J={report.kdj_j:.2f}")
    lines.append(f"MACD: DIF={report.macd_dif:.4f} {'(一票否决)' if report.macd_veto else ''}")
    lines.append(f"双线: 白线={report.white_line:.2f} 黄线={report.yellow_line:.2f}")
    lines.append("")
    lines.append(f"防卖飞评分: {report.sell_score}/5 — {report.sell_score_desc}")
    lines.append("")
    lines.append(f"麒麟会阶段: {report.kirin_phase} (置信度{report.kirin_confidence * 100:.0f}%)")
    lines.append("")
    lines.append(
        f"牛绳理论: {report.bull_rope_status} (缺口{report.bull_rope_gap_pct:+.1f}%, 白线{report.bull_rope_white_trend})"
    )
    lines.append(f"沙漏评分: {report.sandglass_score:.0f}/100 {'✨ 完美图形' if report.sandglass_is_perfect else ''}")
    if report.is_centipede:
        lines.append(f"⚠️ 蜈蚣图: {report.centipede_score:.0f}分 — 呼吸紊乱，直接排除不碰")
    lines.append("")

    if report.exit_signals:
        lines.append("⚠️ 出货信号:")
        for s in report.exit_signals:
            lines.append(f"  [{s['strategy']}] {s['date']} {s['description']}")
        lines.append("")

    if report.buy_signals:
        lines.append("✅ 可买信号:")
        for s in report.buy_signals:
            lines.append(f"  [{s['strategy']}] {s['date']} {s['description']}")
        lines.append("")

    if report.stop_loss:
        lines.append(f"建议止损: {report.stop_loss:.2f}")
    if report.target_price:
        lines.append(f"建议止盈: {report.target_price:.2f}")
    lines.append("")
    lines.append(f"风险等级: {report.risk_level}")
    lines.append(f"综合建议: {report.recommendation}")
    lines.append(f"{'=' * 60}")

    return "\n".join(lines)


# ==================== 命令行工具 ====================


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Z哥 持股诊断")
    parser.add_argument("ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=100, help="分析天数")
    args = parser.parse_args()

    report = diagnose_stock(args.ts_code, days=args.days)
    print(format_report(report))


if __name__ == "__main__":
    main()
