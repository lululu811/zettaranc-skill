from typing import List, Dict, Optional
from .core import StrategyType, StrategySignal, Priority, Action, _calc_kdj, _calc_bbi

def _safe_num(val, default=0):
    """Return val if it's a real number, otherwise default."""
    return val if val is not None else default

def detect_b1(klines: List[Dict], index: int, 
              kirin_context: Optional[Dict] = None) -> Optional[StrategySignal]:
    """
    检测 B1 买点（已升级 MDC 多维验证 + 麒麟阶段背景）

    B1 核心条件：
    1. J < -10
    2. 缩量回调（最佳）
    3. 非绿砖状态（连续下跌 < 4天）

    MDC 加分项：
    - 价格处于麒麟会“吸筹”阶段 (+20%)
    - 价格处于麒麟会“回落”阶段末期 (+10%)
    - 处于“派发”阶段 (-30%, 一票否决)
    - 价格触及或低于布林下轨 (+15%)
    - 主力大单净流入为正 (+10%)
    - RSI6 < 20 (极度超卖, +10%)
    - ADX 高位动能竭尽 (+10%)
    """
    if index < 10:
        return None

    today = klines[index]
    k, d, j = _calc_kdj(klines[:index+1])

    # 1. 核心条件判断
    if j >= -10:
        return None

    # 检查是否在连续下跌中（绿砖状态）
    recent_4 = klines[index-3:index+1]
    yin_count = sum(1 for k in recent_4 if k['is_yinxian'])
    if yin_count >= 4: # 强力绿砖，不建议入场
        return None

    # 2. 基础置信度
    is_suoliang = today['is_suoliang']
    confidence = 0.5 + (0.1 if is_suoliang else 0)
    
    mdc_details = []

    # 3. 麒麟阶段背景验证 (Contextual Validation)
    if kirin_context:
        stage = kirin_context.get('stage')
        if stage == '吸筹':
            confidence += 0.20
            mdc_details.append("处于主力吸筹期(高安全)")
        elif stage == '回落':
            confidence += 0.10
            mdc_details.append("处于回落寻底期")
        elif stage == '派发':
            confidence -= 0.30 # 处于派发阶段的 B1 极度危险
            mdc_details.append("处于主力派发期(高风险)")

    # 4. MDC 验证 - 布林带 (超跌验证)
    if today.get('boll_lower') and today['close'] <= today['boll_lower'] * 1.02:
        confidence += 0.15
        mdc_details.append("触及布林下轨(超跌)")

    # 5. MDC 验证 - 资金流 (主力意图)
    if _safe_num(today.get('large_inflow')) > _safe_num(today.get('large_outflow')):
        confidence += 0.10
        mdc_details.append("主力大单净流入")
        
    # 6. MDC 验证 - RSI (极端超卖)
    if (today.get('rsi6') or 50) < 25:
        confidence += 0.05
        mdc_details.append("RSI极端超卖")

    # 7. MDC 验证 - DMI (趋势动能)
    if _safe_num(today.get('adx')) > 40:
        confidence += 0.10
        mdc_details.append(f"ADX高位动能竭尽({_safe_num(today.get('adx')):.1f})")

    confidence = max(0.1, min(confidence, 0.98))

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B1,
        confidence=round(confidence, 2),
        description=f"B1买点 J={j:.2f} " + ", ".join(mdc_details),
        details={
            'j': j, 'k': k, 'd': d,
            'is_suoliang': is_suoliang,
            'yin_count_4': yin_count,
            'price': today['close'],
            'mdc': mdc_details,
            'kirin_stage': kirin_context.get('stage') if kirin_context else None
        },
        action=Action.BUY.value,
        stop_loss=today['low'],
        priority=Priority.OPPORTUNITY)


def detect_b2(klines: List[Dict], index: int,
              kirin_context: Optional[Dict] = None) -> Optional[StrategySignal]:
    """
    检测 B2 买点（已升级 MDC 多维验证 + 麒麟阶段背景）

    B2 条件（B1后的确认信号）：
    1. 前几日有B1（J<-10）
    2. 放量长阳（涨幅>=4%）
    3. J值拐头（>-10）

    MDC 加分项：
    - 处于麒麟会“拉升”阶段 (+20%)
    - 处于麒麟会“吸筹”末期突破 (+10%)
    - 处于麒麟会“派发”阶段 (-40%, 高位诱多)
    - 有效突破布林中轨 (+15%)
    - 主力大单强力净流入比例高 (+15%)
    - DMI 趋势金叉 (+10%)
    - 布林开口向上 (+10%)
    """
    if index < 15:
        return None

    today = klines[index]
    yesterday = klines[index-1]

    # 1. 核心条件：检查是否有B1在前几日
    has_b1 = False
    for i in range(5, min(15, index)):
        pk, pd, pj = _calc_kdj(klines[:index-i+1])
        if pj < -10:
            has_b1 = True
            break

    if not has_b1:
        return None

    # 放量长阳
    is_beidou = today['is_beidou']
    pct_chg = today['pct_chg']
    is_long_yang = pct_chg >= 4

    if not (is_long_yang and is_beidou):
        return None

    # 2. 基础置信度
    k, d, j = _calc_kdj(klines[:index+1])
    confidence = 0.60
    mdc_details = []

    # 3. 麒麟阶段背景验证
    if kirin_context:
        stage = kirin_context.get('stage')
        if stage == '拉升':
            confidence += 0.20
            mdc_details.append("处于主力拉升期(顺势)")
        elif stage == '吸筹':
            confidence += 0.10
            mdc_details.append("处于吸筹突破期")
        elif stage == '派发':
            confidence -= 0.40 # 派发阶段的假突破非常多
            mdc_details.append("处于主力派发期(假突破风险)")

    # 4. MDC 验证 - 布林带 (突破验证)
    if today.get('boll_mid') and yesterday['close'] < yesterday['boll_mid'] and today['close'] > today['boll_mid']:
        confidence += 0.15
        mdc_details.append("突破布林中轨(走强)")
        
    if today.get('boll_upper') and today.get('boll_lower'):
        # 简单判断开口：width 增加
        today_width = (today['boll_upper'] - today['boll_lower']) / today['boll_mid'] if today['boll_mid'] else 0
        prev_width = (yesterday['boll_upper'] - yesterday['boll_lower']) / yesterday['boll_mid'] if yesterday['boll_mid'] else 0
        if today_width > prev_width * 1.05:
            confidence += 0.05
            mdc_details.append("布林开口向上")

    # 5. MDC 验证 - 资金流 (强力买入)
    total_amount = today['amount']
    net_inflow = today.get('large_inflow', 0) - today.get('large_outflow', 0)
    if net_inflow > 0 and total_amount > 0:
        inflow_ratio = net_inflow / total_amount
        if _safe_num(inflow_ratio, 0) > 0.05:
            confidence += 0.15
            mdc_details.append(f"主力大单强力净流入({inflow_ratio*100:.1f}%)")
            
    # 6. MDC 验证 - DMI (金叉验证)
    if today.get('dmi_plus') and yesterday.get('dmi_minus'):
        if (_safe_num(yesterday.get('dmi_plus')) < _safe_num(yesterday.get('dmi_minus'))
                and _safe_num(today.get('dmi_plus')) > _safe_num(today.get('dmi_minus'))):
            confidence += 0.10
            mdc_details.append("DMI趋势金叉")

    confidence = max(0.1, min(confidence, 0.98))

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B2,
        confidence=round(confidence, 2),
        description=f"B2确认 涨{pct_chg:.2f}% " + ", ".join(mdc_details),
        details={
            'j': j,
            'pct_chg': pct_chg,
            'is_beidou': is_beidou,
            'price': today['close'],
            'mdc': mdc_details,
            'kirin_stage': kirin_context.get('stage') if kirin_context else None
        },
        action=Action.BUY.value,
        stop_loss=today['low'],
        priority=Priority.OPPORTUNITY)


def detect_b3(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B3 中继买点

    B3 条件：
    1. B2后出现
    2. 分歧转一致（小阳线）
    3. 涨幅<2%
    4. 振幅<7%
    """
    if index < 20:
        return None

    today = klines[index]

    # 检查前几日是否有B2
    has_b2 = False
    for i in range(3, min(10, index)):
        if klines[index-i]['pct_chg'] >= 4 and klines[index-i]['is_beidou']:
            has_b2 = True
            break

    if not has_b2:
        return None

    # B3：小阳线，分歧转一致
    pct_chg = today['pct_chg']
    amplitude = (today['high'] - today['low']) / today['prev_close'] * 100

    if not (0 < pct_chg < 2 and amplitude < 7):
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B3,
        confidence=0.7,
        description=f"B3中继 涨{pct_chg:.2f}% 振幅{amplitude:.2f}%",
        details={
            'pct_chg': pct_chg,
            'amplitude': amplitude,
            'price': today['close'],
        },
        action=Action.BUY.value,
        stop_loss=today['low'],
        priority=Priority.OPPORTUNITY)


def detect_sb1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测超级B1

    超级B1条件：
    1. 缩量回调到极致
    2. 突然放量下跌（震仓）
    3. 继续缩量企稳
    4. J出现负值
    """
    if index < 10:
        return None

    today = klines[index]
    prev_1 = klines[index-1] if index >= 1 else None
    prev_2 = klines[index-2] if index >= 2 else None

    if not (prev_1 and prev_2):
        return None

    # 检查前2天是否有放量下跌
    is_drop_vol = prev_2['close'] < prev_2['open'] and prev_2['vol'] > klines[index-3]['vol'] * 1.5

    if not is_drop_vol:
        return None

    # 今日缩量企稳
    is_suoliang = today['is_suoliang']

    # J值
    k, d, j = _calc_kdj(klines[:index+1])

    if j >= -5:
        return None

    # 超级B1确认
    stop_loss = prev_2['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.SB1,
        confidence=0.9,
        description=f"超级B1 J={j:.2f} 放量跌后缩量企稳",
        details={
            'j': j,
            'drop_vol': prev_2['vol'],
            'is_suoliang': is_suoliang,
            'price': today['close'],
        },
        action=Action.BUY.value,
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)
