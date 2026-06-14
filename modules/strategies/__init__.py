from typing import Any, Optional

from .core import (
    StrategyType,
    Priority,
    Action,
    StrategySignal,
    get_kline_data,
    get_db_connection,  # noqa: F401  re-export
    _klines_dict_to_daily,  # noqa: F401  re-export
    _dict_to_daily,
    _calc_kdj,
    _calc_bbi,
)

from .base_strategies import detect_b1, detect_b2, detect_b3, detect_sb1
from .compound_strategies import (
    detect_changan,
    detect_sifen_zhiyi_sanyin,
    detect_nana,
    detect_yidong_dilian,
    detect_pinghang,
    detect_kengqi,
    detect_duichen_va,
)
from .sell_signals import (
    detect_s1,
    detect_s2,
    detect_s3,
    detect_brick_signals,
    detect_buy_exhaustion,
    detect_green_fat_red_thin,
    detect_staircase_distribution,
    detect_top_pinwheel,
)


def _post_process_signals(signals: list[StrategySignal]) -> list[StrategySignal]:
    """
    信号后处理：
    1. 按日期+策略类型去重（同一天同一类型只保留置信度最高的）
    2. 按优先级和日期排序
    3. 截断：最多保留最近30个信号，且每个类型最多保留最近3个
    """
    if not signals:
        return []

    # 1. 去重：同一天同一策略类型，保留置信度最高的
    key_map: dict[tuple[str, str], StrategySignal] = {}
    for s in signals:
        key = (s.trade_date, s.strategy.value)
        if key not in key_map or s.confidence > key_map[key].confidence:
            key_map[key] = s

    deduped = list(key_map.values())

    # 2. 按优先级降序、日期降序排序
    deduped.sort(key=lambda x: (x.priority.value, x.confidence, x.trade_date), reverse=True)

    # 3. 截断：每个策略类型最多保留3个最新信号，总体最多30个
    type_counts: dict[str, int] = {}
    filtered: list[StrategySignal] = []
    for s in deduped:
        type_key = s.strategy.value
        if type_counts.get(type_key, 0) >= 3:
            continue
        if len(filtered) >= 30:
            break
        type_counts[type_key] = type_counts.get(type_key, 0) + 1
        filtered.append(s)

    # 最终按日期降序输出（用户看时间线最自然）
    filtered.sort(key=lambda x: x.trade_date, reverse=True)
    return filtered


def detect_all_strategies(ts_code: str, days: int = 120) -> list[StrategySignal]:
    """
    检测所有战法信号

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        战法信号列表
    """
    klines = get_kline_data(ts_code, days)

    if not klines:
        return []

    signals = []

    # ===== 预计算指标序列（避免 daily loop 内重复计算）=====
    daily_klines = _dict_to_daily(klines)

    from ..indicators import (
        precompute_kdj_sequence,
        precompute_bbi_sequence,
        calculate_macd,
        detect_didi,
        detect_macd_trap,
        detect_chuhuo_wushi,
        detect_zaihou_chongjian,
        detect_yueyueyushi,
        detect_key_candle,
        detect_volume_attack,
    )

    kdj_sequence = precompute_kdj_sequence(daily_klines)
    bbi_sequence = precompute_bbi_sequence(daily_klines)
    dif_list, _, _ = calculate_macd(daily_klines)

    # 一次性预计算所有指标并挂载到 DailyData 属性上，消除策略循环检测内的重复计算开销
    dif_len = len(dif_list) if dif_list else 0
    for idx, k in enumerate(daily_klines):
        k.kdj_k, k.kdj_d, k.kdj_j = kdj_sequence[idx]
        k.bbi = bbi_sequence[idx]
        k.macd_dif = dif_list[idx] if idx < dif_len else 0.0

    # 遍历每一天检测战法
    from ..indicators import detect_kirin_stage

    for i in range(20, len(klines)):
        # 获取当前切片的麒麟阶段 (Context)
        kirin_context = detect_kirin_stage(daily_klines[: i + 1])

        # B1 检测
        signal = detect_b1(daily_klines, i, kirin_context=kirin_context)
        if signal:
            signals.append(signal)

        # B2 检测
        signal = detect_b2(daily_klines, i, kirin_context=kirin_context)
        if signal:
            signals.append(signal)

        # B3 检测
        signal = detect_b3(daily_klines, i)
        if signal:
            signals.append(signal)

        # 超级B1 检测
        signal = detect_sb1(daily_klines, i)
        if signal:
            signals.append(signal)

        # 长安战法
        signal = detect_changan(daily_klines, i, kirin_context=kirin_context)
        if signal:
            signals.append(signal)

        # 四分之三阴量
        signal = detect_sifen_zhiyi_sanyin(daily_klines, i)
        if signal:
            signals.append(signal)

        # 娜娜图形
        signal = detect_nana(daily_klines, i, kirin_context=kirin_context)
        if signal:
            signals.append(signal)

        # 异动+地量地价
        signal = detect_yidong_dilian(daily_klines, i)
        if signal:
            signals.append(signal)

        # 平行重炮
        signal = detect_pinghang(daily_klines, i)
        if signal:
            signals.append(signal)

        # 坑里起好货
        signal = detect_kengqi(daily_klines, i)
        if signal:
            signals.append(signal)

        # 对称 VA
        signal = detect_duichen_va(daily_klines, i)
        if signal:
            signals.append(signal)

        # S1 逃顶
        signal = detect_s1(daily_klines, i, kirin_context=kirin_context)
        if signal:
            signals.append(signal)

        # S2 确认逃顶（MACD顶背离）
        signal = detect_s2(daily_klines, i)
        if signal:
            signals.append(signal)

        # S3 最后逃生
        signal = detect_s3(daily_klines, i)
        if signal:
            signals.append(signal)

        # 砖形图信号
        signal = detect_brick_signals(daily_klines, i)
        if signal:
            signals.append(signal)

        # 买盘枯竭
        signal = detect_buy_exhaustion(daily_klines, i)
        if signal:
            signals.append(signal)

        # 绿肥红瘦出货
        signal = detect_green_fat_red_thin(daily_klines, i)
        if signal:
            signals.append(signal)

        # 阶梯放量下跌
        signal = detect_staircase_distribution(daily_klines, i)
        if signal:
            signals.append(signal)

        # 顶部大风车
        signal = detect_top_pinwheel(daily_klines, i)
        if signal:
            signals.append(signal)

    # ===== P1 指标全局检测（只针对最新一天）======
    if daily_klines:
        # 滴滴战法
        didi_result = detect_didi(daily_klines)
        if didi_result.get("is_didi"):
            signals.append(
                StrategySignal(
                    ts_code=ts_code,
                    trade_date=daily_klines[-1].trade_date,
                    strategy=StrategyType.S1,
                    action=Action.SELL.value,
                    confidence=0.95,
                    description=f"滴滴战法：高位连续两根阴线下台阶，第二根收盘{didi_result['second_close']} < 第一根最低{didi_result['first_low']}，量未缩{didi_result['volume_ratio']}倍",
                    price=daily_klines[-1].close,
                    reason=f"滴滴战法：高位连续两根阴线下台阶，第二根收盘({didi_result['second_close']}) < 第一根最低({didi_result['first_low']})，量未缩({didi_result['volume_ratio']}倍)",
                )
            )

        # MACD 金叉空 / 死叉多
        dif_list_all, dea_list_all, _ = calculate_macd(daily_klines)
        if dif_list_all and dea_list_all:
            trap = detect_macd_trap(dif_list_all, dea_list_all)
            if trap.get("is_gold_trap"):
                signals.append(
                    StrategySignal(
                        ts_code=ts_code,
                        trade_date=daily_klines[-1].trade_date,
                        strategy=StrategyType.S1,
                        action=Action.SELL.value,
                        confidence=0.85,
                        description="MACD 金叉空：眼看金叉未成，白线拐头向下，诱多陷阱",
                        price=daily_klines[-1].close,
                        reason="MACD 金叉空：眼看金叉未成，白线拐头向下，诱多陷阱",
                    )
                )
            if trap.get("is_dead_trap"):
                signals.append(
                    StrategySignal(
                        ts_code=ts_code,
                        trade_date=daily_klines[-1].trade_date,
                        strategy=StrategyType.B1,
                        action=Action.BUY.value,
                        confidence=0.85,
                        description="MACD 死叉多：眼看死叉未成，白线拐头向上，空中加油",
                        price=daily_klines[-1].close,
                        reason="MACD 死叉多：眼看死叉未成，白线拐头向上，空中加油",
                    )
                )

        # 主力出货五式
        chuhuo = detect_chuhuo_wushi(daily_klines)
        if chuhuo.get("is_selling") and chuhuo.get("patterns"):
            top = chuhuo["patterns"][0]
            signals.append(
                StrategySignal(
                    ts_code=ts_code,
                    trade_date=daily_klines[-1].trade_date,
                    strategy=StrategyType.S1,
                    action=Action.SELL.value,
                    confidence=top["confidence"],
                    description=f"出货五式：{top['type']} - {top['desc']}",
                    price=daily_klines[-1].close,
                    reason=f"出货五式：{top['type']} - {top['desc']}",
                )
            )

        # 量比攻击信号
        vol_attack = detect_volume_attack(daily_klines)
        if vol_attack.get("is_attack"):
            signals.append(
                StrategySignal(
                    ts_code=ts_code,
                    trade_date=daily_klines[-1].trade_date,
                    strategy=StrategyType.WATCH,
                    action=Action.WATCH.value,
                    confidence=vol_attack["confidence"],
                    description=vol_attack["desc"],
                    price=daily_klines[-1].close,
                    reason=vol_attack["desc"],
                    priority=Priority.OPPORTUNITY,
                )
            )

        # 灾后重建
        rebuild = detect_zaihou_chongjian(daily_klines)
        if rebuild.get("is_rebuild"):
            signals.append(
                StrategySignal(
                    ts_code=ts_code,
                    trade_date=daily_klines[-1].trade_date,
                    strategy=StrategyType.B1,
                    action=Action.BUY.value,
                    confidence=rebuild["confidence"],
                    description=rebuild["desc"],
                    price=daily_klines[-1].close,
                    reason=rebuild["desc"],
                )
            )

        # 跃跃欲试
        ready = detect_yueyueyushi(daily_klines)
        if ready.get("is_ready"):
            signals.append(
                StrategySignal(
                    ts_code=ts_code,
                    trade_date=daily_klines[-1].trade_date,
                    strategy=StrategyType.B2,
                    action=Action.BUY.value,
                    confidence=ready["confidence"],
                    description=ready["desc"],
                    price=daily_klines[-1].close,
                    reason=ready["desc"],
                )
            )

        # 关键K
        key_k = detect_key_candle(daily_klines)
        if key_k.get("is_key"):
            sig_type = StrategyType.S1 if "阴破位" in key_k.get("type", "") else StrategyType.B1
            signals.append(
                StrategySignal(
                    ts_code=ts_code,
                    trade_date=daily_klines[-1].trade_date,
                    strategy=sig_type,
                    action=Action.SELL.value if sig_type == StrategyType.S1 else Action.BUY.value,
                    confidence=key_k["confidence"],
                    description=f"关键K：{key_k['type']} - {key_k['direction']}",
                    price=daily_klines[-1].close,
                    reason=f"关键K：{key_k['type']} - {key_k['direction']}",
                )
            )

        # ========== P2 指标：三波理论 ==========
        from ..indicators import detect_three_waves

        wave = detect_three_waves(daily_klines)
        if wave["wave"] != "未知" and wave["confidence"] >= 0.5:
            wave_map = {
                "建仓波": (
                    StrategyType.B1,
                    Action.BUY,
                    f"三波理论·建仓波：{wave['stats']['gain_pct']}% 涨幅，B1可干",
                ),
                "拉升波": (
                    StrategyType.WATCH,
                    Action.HOLD,
                    f"三波理论·拉升波：{wave['stats']['gain_pct']}% 涨幅，等回调",
                ),
                "冲刺波": (
                    StrategyType.S1,
                    Action.SELL,
                    f"三波理论·冲刺波：{wave['stats']['gain_pct']}% 涨幅，不看",
                ),
            }
            if wave["wave"] in wave_map:
                st, act, desc = wave_map[wave["wave"]]
                signals.append(
                    StrategySignal(
                        ts_code=ts_code,
                        trade_date=daily_klines[-1].trade_date,
                        strategy=st,
                        action=act.value,
                        confidence=wave["confidence"],
                        description=desc,
                        details={"price": daily_klines[-1].close},
                        priority=Priority.OPPORTUNITY if st in (StrategyType.B1, StrategyType.B2) else Priority.OBSERVE,
                    )
                )

        # ========== P2 指标：麒麟会四阶段 ==========
        from ..indicators import detect_kirin_stage

        kirin = detect_kirin_stage(daily_klines)
        if kirin["stage"] != "未知" and kirin["confidence"] >= 0.4:
            kirin_map = {
                "吸筹": (StrategyType.XISHOU, Action.WATCH, f"麒麟会·吸筹：{kirin['sub_type']}，关注等B1"),
                "拉升": (StrategyType.LASHENG, Action.HOLD, f"麒麟会·拉升：{kirin['sub_type']}，不追等回调"),
                "派发": (StrategyType.PAIFA, Action.SELL, f"麒麟会·派发：{kirin['sub_type']}，准备走人"),
                "回落": (StrategyType.LUOLUO, Action.SELL, f"麒麟会·回落：{kirin['sub_type']}，不抄底"),
            }
            if kirin["stage"] in kirin_map:
                st, act, desc = kirin_map[kirin["stage"]]
                signals.append(
                    StrategySignal(
                        ts_code=ts_code,
                        trade_date=daily_klines[-1].trade_date,
                        strategy=st,
                        action=act.value,
                        confidence=kirin["confidence"],
                        description=desc,
                        details={"price": daily_klines[-1].close},
                        priority=Priority.OBSERVE,
                    )
                )

    # ===== 信号后处理：去重 + 截断 + 排序 =====
    signals = _post_process_signals(signals)

    return signals


def get_latest_signal(ts_code: str, days: int = 120) -> StrategySignal | None:
    """
    获取最新战法信号

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        最新战法信号
    """
    signals = detect_all_strategies(ts_code, days)
    return signals[0] if signals else None


def format_signal(signal: StrategySignal) -> str:
    """格式化输出信号"""
    action_emoji = {
        "BUY": "[买入]",
        "SELL": "[卖出]",
        "HOLD": "[持有]",
        "WATCH": "[观望]",
    }

    return f"""
{"=" * 60}
{signal.strategy.value} 信号
{"=" * 60}
股票: {signal.ts_code}
日期: {signal.trade_date}
置信度: {signal.confidence * 100:.0f}%
描述: {signal.description}

交易建议: {action_emoji.get(signal.action, signal.action)}
{f"目标价: {signal.target_price:.2f}" if signal.target_price else ""}
{f"止损价: {signal.stop_loss:.2f}" if signal.stop_loss else ""}

详细: {signal.details}
{"=" * 60}
"""


def analyze_with_strategies(ts_code: str, days: int = 120) -> dict[str, Any]:
    """
    综合战法分析

    Returns:
        分析结果字典
    """
    signals = detect_all_strategies(ts_code, days)

    # 按战法类型分组统计
    strategy_stats: dict[str, dict[str, Any]] = {}
    for s in signals:
        name = s.strategy.value
        if name not in strategy_stats:
            strategy_stats[name] = {"count": 0, "signals": []}
        strategy_stats[name]["count"] += 1
        strategy_stats[name]["signals"].append(s)

    # 最新信号
    latest = signals[0] if signals else None

    return {
        "ts_code": ts_code,
        "total_signals": len(signals),
        "strategy_stats": strategy_stats,
        "latest_signal": latest,
        "all_signals": signals[:20],  # 最近20个信号
    }
