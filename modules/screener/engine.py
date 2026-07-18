"""选股分析引擎（单股分析与批量筛选）。"""

import logging
import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed

from ..database import get_db_connection
from ..datasource import DataSource, daily_to_dict
from ..indicators import DailyData

from .criteria import _CRITERIA_REGISTRY, _check_centipede, _check_sandglass_min
from .data import get_all_stocks, get_recent_klines
from .models import StockScore
from .scoring import (
    is_perfect_pattern,
    score_b1_opportunity,
    score_risk,
    score_trend,
    score_volume_pattern,
)

# 向后兼容别名
_daily_to_dict = daily_to_dict

logger = logging.getLogger(__name__)


# 并行化阈值：小于此数量不启用多进程（启动开销不值得）
_PARALLEL_THRESHOLD = 50


def _is_picklable(obj) -> bool:
    """检查对象是否可被 pickle 序列化（用于多进程传参预检）。"""
    try:
        pickle.dumps(obj)
        return True
    except Exception:
        return False


def analyze_stock(
    ts_code: str, klines: list[DailyData] | None = None, datasource: DataSource | None = None
) -> StockScore:
    """
    综合评分单只股票
    """
    if klines is None:
        klines = get_recent_klines(ts_code, 150, datasource=datasource)

    if not klines:
        return StockScore(ts_code=ts_code)

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
        from ..indicators import detect_kirin_stage, detect_three_waves

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
        from ..indicators import calculate_sandglass_score

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


def _analyze_worker(
    ts_code: str, datasource: DataSource | None = None
) -> tuple[str, list[DailyData], StockScore] | None:
    """
    并行 worker：评分单只股票
    必须在模块顶层定义，以便 ProcessPoolExecutor 可以 pickle
    返回: (ts_code, klines, score) 或 None
    """
    klines = get_recent_klines(ts_code, 150, datasource=datasource)
    if not klines or len(klines) < 30:
        return None
    score = analyze_stock(ts_code, klines, datasource=datasource)
    return ts_code, klines, score


def _filter_stock(result: tuple[str, list, StockScore], criteria: str) -> bool:
    """判断单只股票是否满足选股条件（注册表分发模式）"""
    ts_code, klines, score = result

    # 硬过滤：蜈蚣图
    if _check_centipede(klines):
        return False
    # 硬过滤：沙漏最低分
    if _check_sandglass_min(klines):
        return False

    # 从注册表查找并执行
    handler = _CRITERIA_REGISTRY.get(criteria)
    if handler:
        return handler(klines, score)
    return False


def screen_stocks(
    criteria: str = "b1",
    max_stocks: int = 0,
    max_workers: int = 0,
    use_parallel: bool = True,
    datasource: DataSource | None = None,
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
    use_parallel: 是否启用多进程并行（<50只时自动关闭；注入的 datasource 需可 pickle）

    返回：满足条件的 StockScore 列表（按评分降序）
    """
    stocks = get_all_stocks(datasource=datasource)
    limit = max_stocks if max_stocks > 0 else 500
    stocks = stocks[:limit]

    results: list[StockScore] = []

    # 小数据量时禁用并行（启动开销不值得）
    use_parallel = use_parallel and len(stocks) >= _PARALLEL_THRESHOLD

    # 注入的 datasource 必须可 pickle 才能在多进程间传递
    if use_parallel and datasource is not None and not _is_picklable(datasource):
        logger.warning("注入的 datasource 无法被 pickle 序列化，screen_stocks 将回退到串行模式")
        use_parallel = False

    if not use_parallel:
        # 串行模式
        for stock in stocks:
            result = _analyze_worker(stock["ts_code"], datasource=datasource)
            if result and _filter_stock(result, criteria):
                results.append(result[2])
    else:
        # 并行模式：只并行 analyze_stock，筛选在主进程串行
        workers = max_workers or os.cpu_count() or 4
        try:
            ts_codes = [s["ts_code"] for s in stocks]

            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_map = {executor.submit(_analyze_worker, ts_code, datasource): ts_code for ts_code in ts_codes}
                for future in as_completed(future_map):
                    result = future.result()
                    if result and _filter_stock(result, criteria):
                        results.append(result[2])
        except Exception:
            # 并行失败回退到串行
            for stock in stocks:
                result = _analyze_worker(stock["ts_code"], datasource=datasource)
                if result and _filter_stock(result, criteria):
                    results.append(result[2])

    # 按评分排序
    results.sort(key=lambda x: x.score, reverse=True)
    return results
