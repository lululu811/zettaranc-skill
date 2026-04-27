"""
选股与择时系统
实现 Z哥 的"三最原则"和每日五步工作流
"""

import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import os

# 数据库路径
DB_PATH = "data/stock_data.db"


@dataclass
class StockScore:
    """股票评分"""
    ts_code: str
    name: str = ""
    score: float = 0           # 综合评分 0-100
    b1_score: float = 0        # B1买点评分
    trend_score: float = 0     # 趋势评分
    volume_score: float = 0     # 量价评分
    risk_score: float = 0      # 风险评分
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

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
    is_trading: bool = True           # 是否可交易
    market_direction: str = "NEUTRAL"  # LONG/NEUTRAL/SHORT
    market_strength: float = 0        # 0-100
    reasons: List[str] = field(default_factory=list)


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_stocks() -> List[Dict]:
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


def get_recent_klines(ts_code: str, days: int = 60) -> List[Dict]:
    """获取近期K线数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
        FROM daily_kline
        WHERE ts_code = ?
        ORDER BY trade_date DESC
        LIMIT ?
    """, (ts_code, days))

    rows = cursor.fetchall()
    conn.close()

    # 转换为升序
    data_list = []
    for i, row in enumerate(reversed(rows)):
        prev_close = rows[len(rows)-i-2]['close'] if i < len(rows)-1 else row['close']
        data_list.append({
            'ts_code': row['ts_code'],
            'trade_date': row['trade_date'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'vol': row['vol'],
            'pct_chg': row['pct_chg'],
            'prev_close': prev_close,
        })

    return data_list


def calculate_ma(prices: List[float], period: int) -> float:
    """计算均线"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calculate_vol_ma(vols: List[float], period: int) -> float:
    """计算量能均线"""
    if len(vols) < period:
        return 0
    return sum(vols[-period:]) / period


def calculate_kdj(klines: List[Dict], period: int = 9) -> Tuple[float, float, float]:
    """计算KDJ"""
    if len(klines) < period:
        return 50, 50, 50

    rsv_list = []
    for i in range(period - 1, len(klines)):
        low_list = [klines[j]['low'] for j in range(i - period + 1, i + 1)]
        high_list = [klines[j]['high'] for j in range(i - period + 1, i + 1)]
        low_min = min(low_list)
        high_max = max(high_list)

        if high_max == low_min:
            rsv = 50
        else:
            rsv = (klines[i]['close'] - low_min) / (high_max - low_min) * 100
        rsv_list.append(rsv)

    k = d = 50.0
    for rsv in rsv_list:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k

    j = 3 * k - 2 * d
    return round(k, 2), round(d, 2), round(j, 2)


def calculate_bbi(klines: List[Dict]) -> float:
    """计算BBI"""
    if len(klines) < 24:
        return 0
    closes = [k['close'] for k in klines]
    return round((calculate_ma(closes, 3) + calculate_ma(closes, 6) +
                 calculate_ma(closes, 12) + calculate_ma(closes, 24)) / 4, 2)


def is_perfect_pattern(klines: List[Dict]) -> Tuple[bool, List[str]]:
    """
    判断是否完美图形

    完美图形条件:
    1. BBI之上
    2. 缩量整理
    3. 均线多头（可选）
    4. 非高位
    """
    if len(klines) < 30:
        return False, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]
    vols = [k['vol'] for k in klines]

    reasons = []
    warnings = []

    # 1. BBI之上
    if today['close'] > bbi:
        reasons.append("价格在BBI之上")
    else:
        warnings.append("价格在BBI下方")

    # 2. 缩量整理
    ma5_vol = calculate_vol_ma(vols, 5)
    today_vol = today['vol']
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
    max_high = max(k['high'] for k in klines[-60:])
    drop_ratio = (max_high - today['close']) / max_high
    if drop_ratio > 0.3:
        reasons.append(f"相对高点回调{drop_ratio*100:.0f}%")
    elif drop_ratio < 0.1:
        warnings.append("接近历史高位")

    # 综合判断
    is_perfect = len(reasons) >= 2 and len(warnings) == 0

    return is_perfect, reasons


def score_b1_opportunity(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估B1买点机会

    返回: (评分0-100, 原因列表)
    """
    if len(klines) < 20:
        return 0, ["数据不足"]

    today = klines[-1]
    k, d, j = calculate_kdj(klines)
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]
    vols = [k['vol'] for k in klines]

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
    if today['vol'] < calculate_vol_ma(vols, 5) * 0.6:
        score += 20
        reasons.append("缩量回调")

    # BBI下方（低位）
    if today['close'] < bbi:
        score += 15
        reasons.append("BBI下方低位")

    # 价格在合理区间
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)
    if ma20 < today['close'] < ma60:
        score += 15
        reasons.append("中期均线区间")

    # 风险提示
    if j > 0:
        score -= 10
    if today['close'] > bbi * 1.05:
        score -= 15

    return max(0, min(100, score)), reasons


def score_trend(klines: List[Dict]) -> Tuple[float, str]:
    """
    评估趋势

    返回: (评分0-100, 趋势方向)
    """
    if len(klines) < 20:
        return 50, "震荡"

    closes = [k['close'] for k in klines]
    today = klines[-1]
    bbi = calculate_bbi(klines)

    ma5 = calculate_ma(closes, 5)
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)

    # 趋势判断
    if ma5 > ma20 > ma60 and today['close'] > bbi:
        direction = "上升"
        score = 80 if today['pct_chg'] > 0 else 70
    elif ma5 < ma20 < ma60 and today['close'] < bbi:
        direction = "下降"
        score = 30
    else:
        direction = "震荡"
        score = 50

    # 短期动能
    if len(klines) >= 5:
        recent_pct = sum(k['pct_chg'] for k in klines[-5:])
        if recent_pct > 10:
            score += 10
        elif recent_pct < -10:
            score -= 10

    return max(0, min(100, score)), direction


def score_volume_pattern(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估量价形态
    """
    if len(klines) < 10:
        return 50, ["数据不足"]

    today = klines[-1]
    vols = [k['vol'] for k in klines]
    vol_ma5 = calculate_vol_ma(vols, 5)
    vol_ma10 = calculate_vol_ma(vols, 10)

    score = 50
    reasons = []

    # 量比
    vol_ratio = today['vol'] / vol_ma5
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
    if today['pct_chg'] > 3 and vol_ratio > 1.2:
        score += 15
        reasons.append("价涨量增(攻击形态)")
    elif today['pct_chg'] < -3 and vol_ratio > 1.2:
        score -= 15
        reasons.append("价跌量增(出货嫌疑)")

    return max(0, min(100, score)), reasons


def score_risk(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估风险
    """
    if len(klines) < 20:
        return 50, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]

    score = 100  # 初始100分，越高越安全
    warnings = []

    # 高位风险
    max_high = max(k['high'] for k in klines[-60:])
    drop_ratio = (max_high - today['close']) / max_high
    if drop_ratio < 0.1:
        score -= 30
        warnings.append("接近历史高位")
    elif drop_ratio < 0.2:
        score -= 15
        warnings.append("相对高位")

    # 跌破BBI风险
    if today['close'] < bbi:
        score -= 20
        warnings.append("跌破BBI")

    # 放量阴线风险
    for i in range(min(5, len(klines)-1)):
        k = klines[-(i+1)]
        prev = klines[-(i+2)] if i < len(klines)-2 else None
        if prev and k['close'] < prev['close'] and k['vol'] > prev['vol'] * 1.5:
            score -= 10
            warnings.append("近期有放量阴线")
            break

    # 连续下跌
    recent_3_drop = sum(1 for k in klines[-3:] if k['close'] < k['prev_close'])
    if recent_3_drop >= 3:
        score -= 15
        warnings.append("连续3天下跌")

    return max(0, min(100, score)), warnings


def analyze_stock(ts_code: str, klines: List[Dict] = None) -> StockScore:
    """
    综合评分单只股票
    """
    if klines is None:
        klines = get_recent_klines(ts_code)

    if not klines:
        return StockScore(ts_code=ts_code)

    today = klines[-1]

    # 获取股票名称
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM stock_basic WHERE ts_code = ?", (ts_code,))
    row = cursor.fetchone()
    name = row['name'] if row else ts_code
    conn.close()

    # 计算各项评分
    b1_score, b1_reasons = score_b1_opportunity(klines)
    trend_score, trend_dir = score_trend(klines)
    volume_score, volume_reasons = score_volume_pattern(klines)
    risk_score, risk_warnings = score_risk(klines)

    # 综合评分（加权平均）
    # B1机会 30% + 趋势 25% + 量价 25% + 风险 20%
    total_score = b1_score * 0.3 + trend_score * 0.25 + volume_score * 0.25 + risk_score * 0.2

    # 完美图形额外加分
    is_perfect, perfect_reasons = is_perfect_pattern(klines)
    if is_perfect:
        total_score = min(100, total_score * 1.1)
        b1_reasons.extend(perfect_reasons)

    score = StockScore(
        ts_code=ts_code,
        name=name,
        score=round(total_score, 1),
        b1_score=round(b1_score, 1),
        trend_score=round(trend_score, 1),
        volume_score=round(volume_score, 1),
        risk_score=round(risk_score, 1),
        reasons=b1_reasons + volume_reasons,
        warnings=risk_warnings
    )

    return score


def screen_stocks(criteria: str = "b1") -> List[StockScore]:
    """
    选股筛选

    criteria:
    - "b1": B1买点机会
    - "perfect": 完美图形
    - "breakout": 突破形态
    - "oversold": 超跌反弹
    """
    stocks = get_all_stocks()
    results = []

    for stock in stocks[:50]:  # 限制数量避免超时
        ts_code = stock['ts_code']
        klines = get_recent_klines(ts_code, 60)

        if not klines or len(klines) < 30:
            continue

        score = analyze_stock(ts_code, klines)

        # 根据条件筛选
        if criteria == "b1" and score.b1_score >= 50:
            results.append(score)
        elif criteria == "perfect" and score.score >= 65:
            results.append(score)
        elif criteria == "oversold" and score.trend_score <= 40:
            results.append(score)
        elif criteria == "breakout" and score.volume_score >= 70:
            results.append(score)

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
    stocks = [row['ts_code'] for row in cursor.fetchall()]

    rise_count = 0
    total_count = 0

    for ts_code in stocks[:20]:
        cursor.execute("""
            SELECT pct_chg FROM daily_kline
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT 1
        """, (ts_code,))
        row = cursor.fetchone()
        if row:
            total_count += 1
            if row['pct_chg'] > 0:
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
        trade_date=today,
        is_trading=True,
        market_direction=direction,
        market_strength=strength,
        reasons=reasons
    )


def format_stock_score(score: StockScore) -> str:
    """格式化股票评分"""
    return f"""
{score.ts_code} {score.name}
{'='*50}
综合评分: {score.score:.1f}/100 {score.rating}
{'='*50}
B1买点评分: {score.b1_score:.1f}
趋势评分: {score.trend_score:.1f}
量价评分: {score.volume_score:.1f}
风险评分: {score.risk_score:.1f}

利好因素:
{chr(10).join(f"  + {r}" for r in score.reasons) if score.reasons else "  无"}

风险提示:
{chr(10).join(f"  ! {w}" for w in score.warnings) if score.warnings else "  无"}
"""


def daily_workflow() -> Dict[str, Any]:
    """
    每日五步工作流

    返回分析结果
    """
    print("="*60)
    print("Z哥 每日五步工作流")
    print("="*60)

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

    print(f"B1买点机会 (TOP 5):")
    for i, s in enumerate(b1_stocks[:5], 1):
        print(f"  {i}. {s.ts_code} {s.name} 评分:{s.score:.0f}")

    print(f"\n完美图形 (TOP 5):")
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
    parser.add_argument("action", choices=["score", "screen", "workflow"],
                        help="操作: score=单股评分, screen=选股, workflow=每日工作流")
    parser.add_argument("--ts_code", help="股票代码")
    parser.add_argument("--criteria", default="b1",
                       choices=["b1", "perfect", "breakout", "oversold"],
                       help="选股条件")
    parser.add_argument("--limit", type=int, default=10, help="返回数量")

    args = parser.parse_args()

    if args.action == "score":
        if not args.ts_code:
            print("请指定股票代码: --ts_code 000001.SZ")
            return
        score = analyze_stock(args.ts_code)
        print(format_stock_score(score))

    elif args.action == "screen":
        results = screen_stocks(args.criteria)
        print(f"\n{'='*60}")
        print(f"选股结果 ({args.criteria}) 共{len(results)}只")
        print(f"{'='*60}")
        for i, s in enumerate(results[:args.limit], 1):
            print(f"{i:2}. {s.ts_code} {s.name:<8} 评分:{s.score:5.1f}  B1:{s.b1_score:5.1f}")
            if s.reasons:
                print(f"    利好: {', '.join(s.reasons[:2])}")
            if s.warnings:
                print(f"    风险: {', '.join(s.warnings[:1])}")

    elif args.action == "workflow":
        daily_workflow()


if __name__ == "__main__":
    main()
