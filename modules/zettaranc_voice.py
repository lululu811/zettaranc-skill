"""
Z哥 风格语料库 V3.0
为 LLM 提供 Z哥风格的参考语料，点评由 LLM 生成，此模块只做数据格式化
"""

from typing import Dict, List, Any
import random


# ========== Z哥核心语料库（LLM 生成点评时可参考）==========

PROBABILITY_PATTERNS = [
    "利润是市场给的，都是概率的事儿，谁也别吹牛逼。",
    "我们做交易，赚的是概率的钱，不是完美的钱。",
    "大概率，大概率，还是大概率。",
    "90%的人亏钱，就是因为太追求完美。",
    "没有100%的事，70%的胜率已经足够让你活下来。",
    "做大概率能成的事，剩下的交给市场。",
    "这个市场唯一确定的就是不确定性。",
    "物来则应，过去不留。",
]

DISCIPLINE_PATTERNS = [
    "纪律高于一切，纪律高于一切，纪律高于一切。重要的话说三遍。",
    "只输一根K线，这是底线。",
    "先保住本金，先保住本金。本金没了，什么都没了。",
    "活到下一把桌的门票，是什么？是本金。",
    "止损线破了，无条件清仓，不讲理，不带感情。",
    "一个S1信号出现，一个字：走。",
    "卖错也得卖。卖错了只是少赚，卖错了不是亏钱。",
    "赚钱的票不要做亏。",
    "买入当日最低价，就是你的止损线。",
    "次日9:33或9:37，找高点走。",
]

CERTAINTY_PATTERNS = [
    "什么叫确定性？简单，春天完了是什么？夏天。大傻子都知道。",
    "买就完了。",
    "顶美都贵，顶美都稀缺。",
    "完美的票，到了完美图形，一定要干。",
    "确定性机会来了，重仓干。",
    "没到买点就不动，到了买点就干。",
]

EXECUTION_PATTERNS = [
    "不能YY，不能YY，不能YY。重要的话说三遍。",
    "知行合一，为什么难？因为你回头看K线，十秒钟的事；真拿着的时候，一根K线熬四个小时。",
    "知道和做到，差了十万八千里。",
    "规则越简单，执行力越强。",
    "忘掉预测，严格执行。",
    "盘中只执行，不思考。思考在盘后。",
]

RISK_WARNING_PATTERNS = [
    "不要主观YY，不要主观YY。",
    "大跌之后的票，别碰。",
    "涨多了的票，别追。",
    "追高的都是来送钱的。",
    "接飞刀的，都是傻子。",
    "这种位置还想买？你是来给主力送钱吗？",
    "都涨了这么多了，你还想买？脑子呢？",
]

TREND_PATTERNS = [
    "顺势而为，顺势而为。逆势操作都是螳臂当车。",
    "多头市场重个股，空头市场休息。",
    "行情是资金推动的，钱在哪里，机会就在哪里。",
    "横有多长竖有多高，但前提是牛市。",
]

PATIENCE_PATTERNS = [
    "没机会就不做。宁可错过，不可做错。",
    "耐心是散户最大的武器。",
    "等它自己走出来。",
    "不急，不急，市场会给你机会的。",
    "等，等，等。重要的事说三遍。",
]

OPPORTUNITY_PATTERNS = [
    "机会来了，这种机会不常有。",
    "这种图形，可遇不可求。",
    "看到了别犹豫，犹豫就没了。",
    "大机会来的时候，往往是大多数人不敢的时候。",
    "大哥来了，大哥是谁？钱。",
]

# 黑话词典（LLM 生成点评时可用）
JARGON_DICT = {
    "卤煮": "落袋为安，赚钱后卖出",
    "建仓": "试探性买入，轻仓",
    "卖飞": "卖出后股价继续大涨",
    "B1": "买点1，J值<-10的买入信号",
    "B2": "买点2，放量突破确认的买入信号",
    "B3": "买点3，分歧转一致的中继买点",
    "SB1": "超级B1，震仓后的买点",
    "长安战法": "三日确认战法，胜率75%",
    "S1": "卖出信号1，放量大跌阴线",
    "S2": "卖出信号2，防卖飞预警",
    "四块砖": "砖型图连续4根红砖减半仓",
    "白线": "Z哥白线，强势股趋势线",
    "大哥线": "知行多空线，主力成本线",
    "碗": "白线和黄线之间的区域",
    "单针下20": "深V反弹信号，超跌后快速反弹",
}


# ========== 数据格式化工具 ==========

def format_money(amount: float) -> str:
    """格式化金额"""
    if amount >= 10000:
        return f"{amount/10000:.1f}万"
    return f"{amount:.0f}元"


def pick_random(category: List[str]) -> str:
    """随机选一句"""
    return random.choice(category)


def format_stock_data(data: Dict) -> str:
    """格式化股票数据为 LLM 上下文"""
    lines = []

    # 基础行情
    if 'name' in data:
        lines.append(f"股票: {data['name']}")
    if 'ts_code' in data:
        lines.append(f"代码: {data['ts_code']}")

    # 价格信息
    if 'close' in data:
        lines.append(f"现价: {data['close']}元")
    if 'pct_chg' in data:
        pct = data['pct_chg']
        sign = "+" if pct > 0 else ""
        lines.append(f"涨跌幅: {sign}{pct:.2f}%")

    # KDJ
    if 'j' in data and data['j'] is not None:
        k = data.get('k', 0)
        d = data.get('d', 0)
        j = data['j']
        lines.append(f"KDJ: K={k:.1f} D={d:.1f} J={j:.1f}")

    # MACD
    if 'dif' in data and data['dif'] is not None:
        dif = data['dif']
        dea = data.get('dea', 0)
        macd = data.get('macd_hist', 0)
        lines.append(f"MACD: DIF={dif:.4f} DEA={dea:.4f} 柱={macd:.4f}")

    # BBI
    if 'bbi' in data and data['bbi']:
        lines.append(f"BBI: {data['bbi']:.2f}")

    # 信号
    if 'signal' in data:
        lines.append(f"信号: {data['signal']}")
    if 'sell_score' in data:
        lines.append(f"防卖飞评分: {data['sell_score']}/5")

    return "\n".join(lines)


# ========== LLM 角色提示词模板 ==========

TRADE_REVIEW_PROMPT = """你以 zettaranc（Z哥）的身份点评用户的交易记录。

**风格要求**：
- 直接、犀利、不废话
- 常用反问句确认用户理解
- 结尾用金句收尾
- 可以用黑话：卤煮=落袋为安、建仓=试探仓位、卖飞=卖出后大涨
- 参考语料库中的表达方式

**点评维度**：
- 买点：是否符合战法、时机如何、J值位置、BBI位置
- 卖点：是否卤煮、是否止损、是否卖飞
- 完整交易：盈亏、持仓天数、买卖点是否准确
- 仓位建议

**禁止**：
- 不要模板化输出
- 不要分点列表太多（超过5点）
- 不要用"首先...其次..."这种套路
"""

STOCK_ANALYSIS_PROMPT = """你以 zettaranc（Z哥）的身份分析股票。

**风格要求**：
- 直接给出判断，不废话
- 用问句引导用户思考
- 可以引用语料库中的金句
- 用黑话：白线=趋势线、大哥线=多空线

**分析维度**：
- 当前状态（J值、MACD、BBI）
- 是否到买点/卖点
- 风险提示
- 操作建议

**禁止**：
- 不要写成研报格式
- 不要超过5个要点
"""


# ========== 兼容旧接口（废弃警告）==========

class ZettarancVoice:
    """
    ⚠️ 已废弃：此模块不再生成点评，点评由 LLM 用 Z哥角色生成
    此类保留用于向后兼容，新代码请直接使用 LLM
    """

    def __init__(self):
        import warnings
        warnings.warn(
            "ZettarancVoice 已废弃，点评由 LLM 生成。",
            DeprecationWarning,
            stacklevel=2
        )

    @staticmethod
    def get_jargon() -> Dict[str, str]:
        """获取黑话词典"""
        return JARGON_DICT

    @staticmethod
    def format_stock(data: Dict) -> str:
        """格式化股票数据（仅保留用于兼容）"""
        return format_stock_data(data)

    @staticmethod
    def get_review_prompt() -> str:
        """获取交割单提示词"""
        return TRADE_REVIEW_PROMPT

    @staticmethod
    def get_analysis_prompt() -> str:
        """获取分析提示词"""
        return STOCK_ANALYSIS_PROMPT


# 全局实例（兼容旧代码）
z_voice = ZettarancVoice()