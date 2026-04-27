"""
Z哥 风格解读模块 V2.0
基于467篇语料提炼的Z哥人格化语言
"""

from typing import Dict, Any, Optional, List
import random


class ZettarancVoice:
    """Z哥 声音 - 用Z哥的语气解读指标"""

    # ========== 核心语料库 ==========

    # 概率思维类
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

    # 纪律止损类
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

    # 确定性类
    CERTAINTY_PATTERNS = [
        "什么叫确定性？简单，春天完了是什么？夏天。大傻子都知道。",
        "买就完了。",
        "顶美都贵，顶美都稀缺。",
        "完美的票，到了完美图形，一定要干。",
        "确定性机会来了，重仓干。",
        "没到买点就不动，到了买点就干。",
    ]

    # 执行力/知行合一类
    EXECUTION_PATTERNS = [
        "不能YY，不能YY，不能YY。重要的话说三遍。",
        "知行合一，为什么难？因为你回头看K线，十秒钟的事；真拿着的时候，一根K线熬四个小时。",
        "知道和做到，差了十万八千里。",
        "规则越简单，执行力越强。",
        "忘掉预测，严格执行。",
        "盘中只执行，不思考。思考在盘后。",
    ]

    # 风险警告类
    RISK_WARNING_PATTERNS = [
        "不要主观YY，不要主观YY。",
        "大跌之后的票，别碰。",
        "涨多了的票，别追。",
        "追高的都是来送钱的。",
        "接飞刀的，都是傻子。",
        "这种位置还想买？你是来给主力送钱吗？",
        "都涨了这么多了，你还想买？脑子呢？",
    ]

    # 趋势/周期类
    TREND_PATTERNS = [
        "顺势而为，顺势而为。逆势操作都是螳臂当车。",
        "多头市场重个股，空头市场休息。",
        "行情是资金推动的，钱在哪里，机会就在哪里。",
        "横有多长竖有多高，但前提是牛市。",
    ]

    # 新手劝退/谦虚类
    HUMILITY_PATTERNS = [
        "功力不够，别学这个。",
        "新人别碰，新人别碰。",
        "这个是给老手看的，新人先学基础。",
        "我也不敢说我是对的，只是分享我的经验。",
        "仅供参考，不构成投资建议。",
    ]

    # 机会识别类
    OPPORTUNITY_PATTERNS = [
        "机会来了，这种机会不常有。",
        "这种图形，可遇不可求。",
        "看到了别犹豫，犹豫就没了。",
        "大机会来的时候，往往是大多数人不敢的时候。",
        "大哥来了，大哥是谁？钱。",
    ]

    # 耐心等待类
    PATIENCE_PATTERNS = [
        "没机会就不做。宁可错过，不可做错。",
        "耐心是散户最大的武器。",
        "等它自己走出来。",
        "不急，不急，市场会给你机会的。",
        "等，等，等。重要的事说三遍。",
    ]

    # RSI类（从语料库提取）
    RSI_PATTERNS = [
        "RSI这玩意儿，就是给你一个参照，别当成圣旨。",
        "超买了不代表马上跌，超卖了不代表马上涨。",
        "RSI只是一种参考指标，不能单独用来做决策。",
        "这个位置用RSI结合其他指标一起看。",
    ]

    # WR类
    WR_PATTERNS = [
        "WR威廉指标，主要是看超买超卖区域。",
        "WR打到负值了，超卖了，但不代表一定反弹。",
        "WR和RSI是一对，配合起来看更准。",
    ]

    # 布林带类
    BOLL_PATTERNS = [
        "布林带是给股价画了个圈，绕来绕去总要回来的。",
        "上轨别追，下轨别怕，中间才是你家。",
        "布林带收口了，行情就要选择方向了。",
        "开口放大，趋势要来；开口缩小，行情睡觉。",
    ]

    # 双线战法类
    DOUBLE_LINE_PATTERNS = [
        "白线是大哥线的影子，走势一致但领先一步。",
        "白线上穿大哥线，这是多头的信号，但别激动。",
        "白线下穿大哥线，空头来了，管住手。",
        "两线纠缠的时候，观望是最好的选择。",
        "白线在黄线上方，可以稍微乐观一点。",
        "白线在黄线下方，那就等着看。",
        "顺大势逆小势，白线就是大势，黄线就是小势。",
    ]

    # 单针下20类
    NEEDLE_PATTERNS = [
        "单针下20，这是深V反弹的信号，但快进快出。",
        "这种位置是超跌反弹，别恋战，反弹就是给你跑的机会。",
        "单针下20，可遇不可求，看到了别犹豫。",
        "深V是好东西，但不是让你重仓的理由。",
    ]

    # 砖型图类
    BRICK_PATTERNS = [
        "四块砖法则，数砖比数K线重要。",
        "红砖持有，绿砖走人，规则简单执行难。",
        "绿砖出现了，绝不抄底，先数四块。",
        "四块红砖走完，至少减半仓。",
        "砖型图是给没时间盯盘的人准备的，数砖就行。",
        "数砖的时候，别数K线，一数就乱。",
        "砖形图和MACD配合起来，成功率更高。",
        "MACD多头区间+红砖，这才是安心持有的状态。",
    ]

    # 反包类
    FANBAO_PATTERNS = [
        "精准反包，这是主力在表态。",
        "反包成功意味着主力还在里面。",
        "反包失败，就别YY了。",
        "三分之二位置是多空分水岭。",
    ]

    # 复盘/总结类
    SUMMARY_PATTERNS = [
        "功夫在盘后，盘中只执行。",
        "每天复盘，每天总结。",
        "记录你的每一笔操作。",
        "交割单不会骗人。",
    ]

    # ========== 随机语料选择 ==========

    def _pick(self, category: List[str]) -> str:
        """随机选一句"""
        return random.choice(category)

    def _maybe(self, category: List[str], prob: float = 0.5) -> str:
        """按概率决定是否加一句"""
        if random.random() < prob:
            return " " + self._pick(category)
        return ""

    # ========== 各指标解读 ==========

    def explain_kdj(self, k: float, d: float, j: float) -> str:
        """解读 KDJ 指标"""
        if j < -20:
            text = f"J值打到了{j:.1f}，严重超卖。这种位置进去，是赌反弹，有风险。但如果你非想买，轻仓试错，设好止损。{self._pick(self.RISK_WARNING_PATTERNS)}"
        elif j < -15:
            text = f"J值{j:.1f}，超卖区域。大概率是买点区域，但别急，等确认。{self._pick(self.PATIENCE_PATTERNS)}"
        elif j < -10:
            text = f"J值{j:.1f}，进入B1区间了。Z哥说过，B1的核心条件就是J小于-10。现在这个位置，可以开始关注了。但记住，J低只是必要条件，不是充分条件。{self._maybe(self.EXECUTION_PATTERNS, 0.3)}"
        elif j < -5:
            text = f"J值{j:.1f}，偏低位。这个位置不用着急，等它自己走出来。{self._pick(self.PATIENCE_PATTERNS)}"
        elif j < 0:
            text = f"J值{j:.1f}，还在低位运行。没有到-10，但也不远了。这种位置观望为主。{self._pick(self.PATIENCE_PATTERNS)}"
        elif j < 20:
            text = f"J值{j:.1f}，偏低。这个位置比较中性，没啥意思。{self._pick(self.PATIENCE_PATTERNS)}"
        elif j < 30:
            text = f"J值{j:.1f}，正常偏低。不上不下，观望。{self._pick(self.PATIENCE_PATTERNS)}"
        elif j < 50:
            text = f"J值{j:.1f}，中位运行。没有明确方向，继续看。{self._pick(self.TREND_PATTERNS)}"
        elif j < 70:
            text = f"J值{j:.1f}，偏高了。不要追涨，不要追涨，不要追涨。{self._pick(self.RISK_WARNING_PATTERNS)}"
        elif j < 85:
            text = f"J值{j:.1f}，已经进入超买区域了。你要是现在想买，那就是在接飞刀。{self._pick(self.RISK_WARNING_PATTERNS)}"
        else:
            text = f"J值打到{j:.1f}了，严重超买。这个位置追进去的，都是来送钱的。{self._pick(self.RISK_WARNING_PATTERNS)} 大概率要调整，别当傻子。{self._pick(self.PROBABILITY_PATTERNS)}"

        return text

    def explain_macd(self, dif: float, dea: float, macd_hist: float) -> str:
        """解读 MACD 指标"""
        if dif > 0 and macd_hist > 0:
            return f"MACD在零轴上方，红柱子在放大。这是多头区间，可以重个股轻大盘。{self._pick(self.TREND_PATTERNS)} 白线上穿零轴就是多头格局，现在就是这个状态。{self._maybe(self.CERTAINTY_PATTERNS, 0.3)}"
        elif dif > 0 and macd_hist < 0:
            return f"MACD在零轴上方，但红柱子在缩小。这意味着上涨动能可能减弱，小心点。但还没破零轴，趋势还在。{self._maybe(self.PATIENCE_PATTERNS, 0.4)}"
        elif dif < 0 and macd_hist < 0:
            return f"MACD在零轴下方，绿柱子在放大。空头格局，什么都别做。{self._pick(self.TREND_PATTERNS)} 空头区间就是休息的时候，别想着抄底。{self._pick(self.RISK_WARNING_PATTERNS)}"
        elif dif < 0 and macd_hist > 0:
            return f"MACD在零轴下方，但红柱子开始出现。这可能是反弹，但别当真。反弹不是反转。{self._pick(self.PROBABILITY_PATTERNS)}"
        elif abs(dif) < 0.05:
            return f"DIF在零轴附近磨叽，MACD也没什么方向。这种震荡行情，不操作就是最好的操作。{self._pick(self.PATIENCE_PATTERNS)}"
        elif dif > 0 and abs(macd_hist) < 0.02:
            return f"MACD在零轴附近横着走，方向不明。这种时候不操作，等它自己选出方向。{self._pick(self.PATIENCE_PATTERNS)}"
        else:
            return f"DIF={dif:.4f}，DEA={dea:.4f}，柱={macd_hist:.4f}。你记住，MACD最大的价值是一票否决，不是用来预测的。{self._pick(self.DISCIPLINE_PATTERNS)}"

    def explain_bbi(self, price: float, bbi: float) -> str:
        """解读 BBI 多空指标"""
        ratio = (price - bbi) / bbi * 100

        if ratio > 10:
            return f"价格在BBI上面一大截了，偏离了{ratio:.1f}%。这个位置不追，等回调。{self._pick(self.CERTAINTY_PATTERNS)}"
        elif ratio > 5:
            return f"价格在BBI上面，偏离了{ratio:.1f}%。已经在多头格局，但涨了一段了，小心点。{self._maybe(self.RISK_WARNING_PATTERNS, 0.5)}"
        elif ratio > 2:
            return f"价格在BBI上方，偏离{ratio:.1f}%。还在多头，但有点远了。{self._maybe(self.PATIENCE_PATTERNS, 0.3)}"
        elif ratio > 0.5:
            return f"价格紧贴着BBI，比较纠结。没方向，等信号。{self._pick(self.PATIENCE_PATTERNS)}"
        elif ratio > -0.5:
            return f"价格紧贴着BBI，方向不明。这种位置观望为主。{self._pick(self.PATIENCE_PATTERNS)}"
        elif ratio > -2:
            return f"价格在BBI下方，偏离了{abs(ratio):.1f}%。还没破多少，但要注意了。{self._maybe(self.RISK_WARNING_PATTERNS, 0.4)}"
        elif ratio > -5:
            return f"价格跌破BBI了，偏离{abs(ratio):.1f}%。空头格局，别YY。{self._pick(self.RISK_WARNING_PATTERNS)}"
        else:
            return f"价格大幅跌破BBI了，偏离了{abs(ratio):.1f}%。空头确立，别想着抄底。{self._pick(self.RISK_WARNING_PATTERNS)}"

    def explain_ma(self, ma5: float, ma10: float, ma20: float, ma60: float, price: float) -> str:
        """解读均线系统"""
        # 多头排列
        if ma5 > ma10 > ma20 and price > ma5:
            return f"均线多头排列，5>10>20，价格在所有均线上方。这是强势形态，但越强势越要小心突然的回调。{self._pick(self.TREND_PATTERNS)}"
        # 空头排列
        elif ma5 < ma10 < ma20 and price < ma5:
            return f"均线空头排列，5<10<20，全部均线压制。这是弱势格局，别逆势操作。{self._pick(self.RISK_WARNING_PATTERNS)}"
        # 缠绕
        elif abs(ma5 - ma10) / ma10 < 0.01:
            return f"5日和10日均线绞在一起，方向不明。这种时候不操作，等它自己选出方向。{self._pick(self.PATIENCE_PATTERNS)}"
        # 价在均线之间
        elif ma10 < price < ma5:
            return f"价格在MA5和MA10之间，短期偏强，但没有完全多头。{self._pick(self.TREND_PATTERNS)}"
        elif ma20 < price < ma10:
            return f"价格在MA10和MA20之间，震荡格局。{self._pick(self.PATIENCE_PATTERNS)}"
        else:
            return f"MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}。均线只是参考，不是绝对的。{self._pick(self.PROBABILITY_PATTERNS)}"

    def explain_rsi(self, rsi6: float, rsi12: float, rsi24: float) -> str:
        """解读 RSI 指标"""
        text = f"RSI6={rsi6:.1f} RSI12={rsi12:.1f} RSI24={rsi24:.1f}。"

        if rsi6 < 20:
            text += f"RSI6={rsi6:.1f}，严重超卖。这种位置可以关注，但别急，等确认。{self._pick(self.RSI_PATTERNS)}"
        elif rsi6 < 30:
            text += f"RSI6={rsi6:.1f}，超卖区域。低位区域，但不代表马上涨。{self._pick(self.PATIENCE_PATTERNS)}"
        elif rsi6 > 80:
            text += f"RSI6={rsi6:.1f}，严重超买。别追了，别追了。{self._pick(self.RISK_WARNING_PATTERNS)}"
        elif rsi6 > 70:
            text += f"RSI6={rsi6:.1f}，进入超买区域。越涨越要小心。{self._maybe(self.RISK_WARNING_PATTERNS, 0.5)}"
        else:
            text += f"RSI在中性区域，没有明确方向。{self._pick(self.PATIENCE_PATTERNS)}"

        if rsi6 < rsi12 and rsi12 < rsi24:
            text += "短期弱于中期弱于长期，空头排列。观望。"
        elif rsi6 > rsi12 and rsi12 > rsi24:
            text += "多头排列，但涨多了。"

        return text

    def explain_wr(self, wr5: float, wr10: float) -> str:
        """解读 WR 威廉指标"""
        text = f"WR5={wr5:.1f} WR10={wr10:.1f}。"

        if wr5 < -90:
            text += f"WR5打到了{wr5:.1f}，严重超卖。但别激动，这不是买入信号。{self._pick(self.WR_PATTERNS)}"
        elif wr5 < -80:
            text += f"WR5={wr5:.1f}，超卖区域。这种位置可以观察，但别急着买。{self._pick(self.PATIENCE_PATTERNS)}"
        elif wr5 > -10:
            text += f"WR5={wr5:.1f}，超买区域。别追，别追。{self._pick(self.RISK_WARNING_PATTERNS)}"
        elif wr5 > -20:
            text += f"WR5={wr5:.1f}，偏高了。小心点。{self._maybe(self.RISK_WARNING_PATTERNS, 0.4)}"
        else:
            text += f"WR在中性区域。{self._pick(self.PATIENCE_PATTERNS)}"

        return text

    def explain_bollinger(self, price: float, boll_mid: float, boll_upper: float,
                        boll_lower: float, boll_width: float, boll_position: float) -> str:
        """解读布林带"""
        text = f"布林带中轨={boll_mid:.2f}，上轨={boll_upper:.2f}，下轨={boll_lower:.2f}。"

        if boll_width < 5:
            text += f"布林带开口极窄，只有{boll_width:.1f}%。行情要选择方向了，耐心等。{self._pick(self.BOLL_PATTERNS)}"
        elif boll_width < 10:
            text += f"布林带收口，宽度{boll_width:.1f}%。横盘整理中。{self._pick(self.PATIENCE_PATTERNS)}"
        elif boll_width > 25:
            text += f"布林带开口放大，宽度{boll_width:.1f}%。趋势行情来了。"

        if boll_position > 90:
            price_above = (price - boll_upper) / boll_upper * 100
            text += f"股价紧贴上轨，偏离{price_above:.1f}%。别追了，等回调。{self._pick(self.BOLL_PATTERNS)}"
        elif boll_position > 75:
            text += f"股价在上轨附近，偏强。但越涨越要小心。{self._maybe(self.RISK_WARNING_PATTERNS, 0.4)}"
        elif boll_position < 10:
            price_below = (boll_lower - price) / boll_lower * 100
            text += f"股价紧贴下轨，偏离{price_below:.1f}%。超卖了，但别急着买。{self._pick(self.BOLL_PATTERNS)}"
        elif boll_position < 25:
            text += f"股价在下轨附近，偏弱。但下轨有支撑。{self._maybe(self.PATIENCE_PATTERNS, 0.5)}"
        else:
            text += f"股价在布林带中间位置，位置={boll_position:.1f}%。正常波动。"

        return text

    def explain_double_line(self, white_line: float, yellow_line: float,
                          is_gold_cross: bool, is_dead_cross: bool) -> str:
        """解读双线战法"""
        ratio = (white_line - yellow_line) / yellow_line * 100

        text = f"白线={white_line:.2f}，大哥线={yellow_line:.2f}。"

        if is_gold_cross:
            text += "出现金叉！白线上穿大哥线，多头信号。但别激动，等确认。{self._pick(self.DOUBLE_LINE_PATTERNS)}"
        elif is_dead_cross:
            text += "出现死叉！白线下穿大哥线，空头信号。管住手。{self._pick(self.DOUBLE_LINE_PATTERNS)}"
        elif ratio > 5:
            text += f"白线在黄线上方，偏离{ratio:.1f}%。多头格局，但别追。{self._pick(self.TREND_PATTERNS)}"
        elif ratio > 0:
            text += f"白线在黄线上方，偏离{ratio:.1f}%。还在多头，可以看。{self._pick(self.DOUBLE_LINE_PATTERNS)}"
        elif ratio > -5:
            text += f"白线在黄线下方，偏离{abs(ratio):.1f}%。空头格局，别YY。{self._pick(self.RISK_WARNING_PATTERNS)}"
        else:
            text += f"白线在黄线下方，偏离{abs(ratio):.1f}%。弱势明显，别逆势。{self._pick(self.RISK_WARNING_PATTERNS)}"

        return text

    def explain_needle_20(self, rsl_short: float, rsl_long: float, is_needle: bool) -> str:
        """解读单针下20"""
        text = f"短期RSL={rsl_short:.1f}，长期RSL={rsl_long:.1f}。"

        if is_needle:
            text += f"单针下20信号触发！深V反弹。{self._pick(self.NEEDLE_PATTERNS)}"
        elif rsl_short < 30:
            text += f"短期RSL偏低，但还没到单针下20。等待确认。{self._pick(self.PATIENCE_PATTERNS)}"
        elif rsl_short > 70:
            text += f"短期RSL偏高，没到超跌区域。观望。{self._pick(self.PATIENCE_PATTERNS)}"
        else:
            text += f"不在超跌区域。{self._pick(self.PATIENCE_PATTERNS)}"

        return text

    def explain_brick(self, brick_value: float, brick_trend: str, brick_count: int,
                    trend_up: bool, is_fanbao: bool,
                    macd_hist: float = 0, dif: float = 0) -> str:
        """解读砖型图

        Args:
            brick_value: 砖型图数值 >0为红砖（上涨），<=0为绿砖（下跌/无信号）
            brick_trend: 趋势状态 RED/GREEN/NEUTRAL
            brick_count: 连续砖数
            trend_up: 命值趋势是否上升
            is_fanbao: 是否出现精准反包信号
            macd_hist: MACD柱状图
            dif: DIF值（用于判断多空）
        """
        # 趋势状态解读
        if brick_trend == "RED":
            trend_text = f"红砖连续{brick_count}根"
        elif brick_trend == "GREEN":
            trend_text = f"绿砖连续{brick_count}根"
        else:
            trend_text = "无砖信号"

        text = f"砖型图：{trend_text}。"

        if is_fanbao:
            text += f"出现精准反包信号！{self._pick(self.FANBAO_PATTERNS)}"
            return text

        # 判断多空区间：MACD零轴上方是多头
        is_bullish_macd = dif > 0

        if brick_trend == "RED":
            # 红砖区域 - 有上涨信号
            if brick_count >= 4:
                text += f"第{brick_count}根红砖了！四块红砖数满，至少减半仓。{self._pick(self.BRICK_PATTERNS)}"
            elif is_bullish_macd and macd_hist > 0:
                text += f"红砖 + MACD多头。安心持有的状态。{self._pick(self.BRICK_PATTERNS)}"
            elif is_bullish_macd:
                text += f"红砖 + MACD零轴上方。但红柱在缩小，谨慎。{self._pick(self.BRICK_PATTERNS)}"
            elif trend_up:
                text += f"红砖 + 命值上升。但MACD在零轴下方，别当真。{self._pick(self.BRICK_PATTERNS)}"
            else:
                text += f"红砖{brick_count}根，趋势不明确，MACD空头。观察别重仓。{self._pick(self.PATIENCE_PATTERNS)}"
        elif brick_trend == "GREEN":
            # 绿砖区域
            if brick_count >= 4:
                text += f"四块绿砖数满！{self._pick(self.BRICK_PATTERNS)}"
            else:
                text += f"绿砖{brick_count}根，空头。绝不抄底，先数四块。{self._pick(self.BRICK_PATTERNS)}"
        else:
            text += f"无砖信号。{self._pick(self.PATIENCE_PATTERNS)}"

        return text

    def explain_sell_score(self, score: int, reasons: str = "") -> str:
        """解读防卖飞评分"""
        if score == 5:
            return f"防卖飞评分5分，满分。这种票拿住了，别乱动。{self._pick(self.DISCIPLINE_PATTERNS)} 赚钱的票不要做亏，先出来保住本金这种事儿，不是现在干的。"
        elif score == 4:
            return f"评分{score}分，状态不错。可以持有，但别加仓了。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif score == 3:
            return f"评分{score}分，中庸。可以持有，但盯着点。收盘跌破BBI就要考虑减仓了。{self._maybe(self.EXECUTION_PATTERNS, 0.4)}"
        elif score == 2:
            return f"评分只有{score}分，不太好。要开始关注了。如果连续两天收盘跌破BBI，别犹豫，该走就走。{self._pick(self.DISCIPLINE_PATTERNS)}"
        else:
            return f"评分{score}分，很危险。这种票不能再拿了，别心存侥幸。{self._pick(self.DISCIPLINE_PATTERNS)} 一个字：走。"

    def explain_volume_pattern(self, is_beidou: bool = False, is_suoliang: bool = False,
                              is_jiayin: bool = False, is_fangliang: bool = False,
                              is_yinxian: bool = False, vol_ratio: float = 1.0) -> str:
        """解读量价形态"""
        parts = []

        if is_beidou:
            parts.append(f"出现倍量（量比{vol_ratio:.1f}x），这是异动信号。大哥来了。{self._pick(self.OPPORTUNITY_PATTERNS)}")
        elif is_suoliang:
            parts.append(f"缩量了。低位缩量可能是蓄力，高位缩量可能是衰竭。要看位置。{self._pick(self.PATIENCE_PATTERNS)}")
        else:
            parts.append(f"量能正常。")

        if is_jiayin:
            parts.append("假阴真阳，K线看着是阴线但实际在涨。这种玩意儿主力全吃了，持有。")
        elif is_fangliang and is_yinxian:
            parts.append(f"放量阴线！{self._pick(self.RISK_WARNING_PATTERNS)} 放量的同时在跌，这不是好信号。一个字：走。")
        elif is_yinxian and vol_ratio > 1.3:
            parts.append(f"下跌放量，要小心。{self._pick(self.RISK_WARNING_PATTERNS)}")

        return " ".join(parts) if parts else "量价正常，没啥特别信号。"

    def explain_signal(self, signal_type: str, signal_desc: str = "") -> str:
        """解读交易信号"""
        if signal_type == "B1":
            return f"出现B1买点信号了。{signal_desc}。但B1只是必要条件，不是充分条件。你要结合大盘、板块、图形综合判断。{self._maybe(self.EXECUTION_PATTERNS, 0.3)}"
        elif signal_type == "B2":
            return f"B2确认信号！{signal_desc}。B2比B1确定性更高，但机会也更少。出现了就别犹豫，犹豫就没了。{self._pick(self.OPPORTUNITY_PATTERNS)}"
        elif signal_type == "B3":
            return f"B3中继信号。{signal_desc}。B3确定性最高，但盈亏比最低。小仓位参与，别重仓。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif signal_type == "SB1":
            return f"超级B1！{signal_desc}。这是B1的特殊形态，胜率更高但机会更少。出现了就干，但设好止损。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif signal_type == "S1":
            return f"【重要】S1卖出信号！{signal_desc}。这个信号优先级最高，别犹豫，别YY，别想太多，直接走。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif signal_type == "HOLD":
            return f"持有信号。{signal_desc}。没毛病，继续拿着。但别加仓了。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif signal_type == "WATCH":
            return f"观望信号。{signal_desc}。现在没有明确的买点，继续等。耐心是散户最大的武器。{self._pick(self.PATIENCE_PATTERNS)}"
        elif signal_type == "DIDI":
            return f"滴滴战法触发！14:55跌破昨低，{signal_desc}。这是规则驱动，不是主观判断，按规则来。{self._pick(self.EXECUTION_PATTERNS)}"
        return f"信号: {signal_type}，{signal_desc}"

    def explain_strategy(self, strategy_type: str, confidence: float, description: str) -> str:
        """解读战法信号"""
        conf = f"置信度{confidence*100:.0f}%"

        if strategy_type == "四分之三阴量":
            return f"【卖出】{conf}，{description}。这个形态成功率90%以上，阴量超过阳量75%，主力在出货。卖错也得卖。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif strategy_type == "长安战法":
            return f"【买入】{conf}，{description}。长安战法是Z哥的75%胜率战法，三日确认。但记住，75%不是100%，设好止损。{self._pick(self.DISCIPLINE_PATTERNS)}"
        elif strategy_type == "娜娜图形":
            return f"【买入】{conf}，{description}。娜娜图形胜率很高，连续放量涨后缩量回调+J负值。符合了就干。{self._pick(self.OPPORTUNITY_PATTERNS)}"
        elif strategy_type == "异动+地量地价":
            return f"【买入】{conf}，{description}。异动后缩量回调，这是Z哥选股的核心逻辑。大概率是主力震仓。{self._pick(self.OPPORTUNITY_PATTERNS)}"
        elif strategy_type == "坑里起好货":
            return f"【买入】{conf}，{description}。主力填坑意味着解放所有套牢盘，大概率是先知先觉资金入场。{self._pick(self.CERTAINTY_PATTERNS)}"
        elif strategy_type == "B1":
            return f"【买入】{conf}，{description}。B1买点，J值进入低位。但别急，等确认。{self._maybe(self.PATIENCE_PATTERNS, 0.5)}"
        elif strategy_type == "B2":
            return f"【买入】{conf}，{description}。B2确认，比B1确定性更高。{self._pick(self.OPPORTUNITY_PATTERNS)}"
        elif strategy_type == "单针下20":
            return f"【买入】{conf}，{description}。深V反弹，单针下20是超跌信号。但这种票快进快出，别恋战。{self._pick(self.DISCIPLINE_PATTERNS)}"
        return f"{strategy_type}: {conf}，{description}"

    def explain_stock_score(self, score: float, rating: str, reasons: List[str] = None, warnings: List[str] = None) -> str:
        """综合解读股票评分"""
        reasons = reasons or []
        warnings = warnings or []

        # 评分解读
        if score >= 85:
            text = f"这个票，{score:.0f}分，非常强。{self._pick(self.CERTAINTY_PATTERNS)} 这种票可遇不可求，看到了别犹豫。"
        elif score >= 70:
            text = f"{score:.0f}分，状态不错。可以关注。{self._pick(self.OPPORTUNITY_PATTERNS)}"
        elif score >= 55:
            text = f"{score:.0f}分，中上水平。可以看看，但别重仓。"
        elif score >= 40:
            text = f"{score:.0f}分，一般般。没什么特别的，观望吧。"
        elif score >= 25:
            text = f"分数不高，{score:.0f}分。机会不大，想买的话要非常谨慎。{self._pick(self.RISK_WARNING_PATTERNS)}"
        else:
            text = f"{score:.0f}分，很低。这种票我是不看的，你别浪费时间。{self._pick(self.HUMILITY_PATTERNS)}"

        # 利好
        if reasons:
            text += f"\n利好：{'、'.join(reasons[:3])}。"

        # 风险
        if warnings:
            text += f"\n但有风险：{'、'.join(warnings[:2])}。{self._pick(self.RISK_WARNING_PATTERNS)}"

        return text

    def explain_market(self, direction: str, strength: float, reasons: List[str] = None) -> str:
        """解读大盘状态"""
        reasons = reasons or []

        if direction == "LONG":
            return f"大盘多头格局，市场强度{strength:.0f}分。{reasons[0] if reasons else ''}。可以积极一点，但别乱追。{self._pick(self.TREND_PATTERNS)} 多头市场重个股轻大盘。"
        elif direction == "SHORT":
            return f"大盘空头格局，市场强度{strength:.0f}分。{reasons[0] if reasons else ''}。这种时候要谨慎，能不做就不做。{self._pick(self.TREND_PATTERNS)} 空头市场，保住本金是第一位的。"
        else:
            return f"大盘中性，市场强度{strength:.0f}分。{reasons[0] if reasons else ''}。没方向的时候，观望是最好的选择。{self._pick(self.PATIENCE_PATTERNS)}"

    def daily_workflow_voice(self, market_desc: str, b1_count: int, perfect_count: int) -> str:
        """每日工作流解读（Z哥口吻）"""
        text = "【今日五步走】\n\n"

        text += f"第一步，择时。{market_desc}\n\n"

        if "多头" in market_desc:
            text += "第二步，定策略。多头市场，主攻。找强势股干。\n\n"
        elif "空头" in market_desc:
            text += "第二步，定策略。空头市场，防守。轻仓或空仓。\n\n"
        else:
            text += "第二步，定策略。中性市场，观望为主。\n\n"

        text += "第三步，选股。"
        if b1_count > 0:
            text += f"今天发现{b1_count}只B1买点机会，这是好事。但记住，B1只是候选名单，不是买入清单。要结合大盘和图形再决定。\n\n"
        else:
            text += "今天没有发现明显的B1买点机会。没关系，没机会就不做。宁可错过，不可做错。\n\n"

        if perfect_count > 0:
            text += f"另外，有{perfect_count}只票走出了完美图形。完美图形是可遇不可求的，看到了别犹豫。\n\n"

        text += "第四步，执行。触发条件就干，不犹豫，不YY，不临时改变计划。\n\n"
        text += "第五步，复盘。收盘后记得复盘，记录今天的操作和想法。功夫在盘后，盘中只执行。"

        return text

    def summarize(self, indicator_result: Dict[str, Any], strategy_signals: List[Dict] = None) -> str:
        """综合总结（Z哥风格）"""
        strategy_signals = strategy_signals or []
        lines = []

        lines.append("=" * 50)
        lines.append(f"【{indicator_result.get('ts_code', 'N/A')} 分析总结】")
        lines.append("=" * 50)

        # 开头语
        lines.append(f"\n{self._pick(self.PROBABILITY_PATTERNS)}")

        # KDJ
        if 'j' in indicator_result:
            lines.append(f"\n→ KDJ: K={indicator_result.get('k', 0):.1f} D={indicator_result.get('d', 0):.1f} J={indicator_result['j']:.1f}")
            lines.append(self.explain_kdj(indicator_result.get('k', 0), indicator_result.get('d', 0), indicator_result['j']))

        # MACD
        if 'dif' in indicator_result and indicator_result.get('dif') is not None:
            lines.append(f"\n→ MACD: DIF={indicator_result['dif']:.4f} DEA={indicator_result.get('dea', 0):.4f} 柱={indicator_result.get('macd_hist', 0):.4f}")
            lines.append(self.explain_macd(indicator_result['dif'], indicator_result.get('dea', 0), indicator_result.get('macd_hist', 0)))

        # BBI
        bbi = indicator_result.get('bbi', 0)
        if bbi and bbi > 0:
            price = indicator_result.get('close', indicator_result.get('ma5', bbi))
            lines.append(f"\n→ BBI: {bbi:.2f}")
            lines.append(self.explain_bbi(price, bbi))

        # 均线
        if 'ma5' in indicator_result and indicator_result['ma5'] > 0:
            lines.append(f"\n→ 均线: MA5={indicator_result['ma5']:.2f} MA10={indicator_result.get('ma10', 0):.2f} MA20={indicator_result.get('ma20', 0):.2f}")
            lines.append(self.explain_ma(indicator_result['ma5'], indicator_result.get('ma10', 0), indicator_result.get('ma20', 0), indicator_result.get('ma60', 0), indicator_result.get('close', indicator_result['ma5'])))

        # RSI
        if 'rsi6' in indicator_result and indicator_result['rsi6'] > 0:
            lines.append(f"\n→ RSI: RSI6={indicator_result['rsi6']:.1f} RSI12={indicator_result.get('rsi12', 0):.1f} RSI24={indicator_result.get('rsi24', 0):.1f}")
            lines.append(self.explain_rsi(indicator_result['rsi6'], indicator_result.get('rsi12', 0), indicator_result.get('rsi24', 0)))

        # WR
        if 'wr5' in indicator_result and indicator_result['wr5'] != 0:
            lines.append(f"\n→ WR: WR5={indicator_result['wr5']:.1f} WR10={indicator_result.get('wr10', 0):.1f}")
            lines.append(self.explain_wr(indicator_result['wr5'], indicator_result.get('wr10', 0)))

        # 布林带
        if 'boll_mid' in indicator_result and indicator_result['boll_mid'] > 0:
            lines.append(f"\n→ 布林带: 中={indicator_result['boll_mid']:.2f} 上={indicator_result['boll_upper']:.2f} 下={indicator_result['boll_lower']:.2f} 宽={indicator_result['boll_width']:.1f}%")
            lines.append(self.explain_bollinger(
                indicator_result.get('close', indicator_result['boll_mid']),
                indicator_result['boll_mid'], indicator_result['boll_upper'], indicator_result['boll_lower'],
                indicator_result['boll_width'], indicator_result.get('boll_position', 50)
            ))

        # 双线战法
        if 'zg_white' in indicator_result and indicator_result['zg_white'] > 0:
            lines.append(f"\n→ 双线战法: 白线={indicator_result['zg_white']:.2f} 大哥线={indicator_result.get('dg_yellow', 0):.2f}")
            lines.append(self.explain_double_line(
                indicator_result['zg_white'], indicator_result.get('dg_yellow', 0),
                indicator_result.get('is_gold_cross', False), indicator_result.get('is_dead_cross', False)
            ))

        # 单针下20
        if 'rsl_short' in indicator_result and indicator_result['rsl_short'] > 0:
            lines.append(f"\n→ 单针下20: RSL_S={indicator_result['rsl_short']:.1f} RSL_L={indicator_result.get('rsl_long', 0):.1f}")
            lines.append(self.explain_needle_20(indicator_result['rsl_short'], indicator_result.get('rsl_long', 0), indicator_result.get('is_needle_20', False)))

        # 砖型图
        if 'brick_value' in indicator_result:
            lines.append(f"\n→ 砖型图: 砖值={indicator_result['brick_value']:.2f} 趋势:{indicator_result.get('brick_trend', 'NEUTRAL')} 连续砖数:{indicator_result.get('brick_count', 0)}")
            lines.append(self.explain_brick(
                indicator_result['brick_value'],
                indicator_result.get('brick_trend', 'NEUTRAL'),
                indicator_result.get('brick_count', 0),
                indicator_result.get('brick_trend_up', False),
                indicator_result.get('is_fanbao', False),
                indicator_result.get('macd_hist', 0),
                indicator_result.get('dif', 0)
            ))

        # 防卖飞评分
        if 'sell_score' in indicator_result:
            lines.append(f"\n→ 防卖飞评分: {indicator_result['sell_score']}/5")
            lines.append(self.explain_sell_score(indicator_result['sell_score'], indicator_result.get('sell_reason', '')))

        # 交易信号
        if 'signal' in indicator_result:
            lines.append(f"\n→ 交易信号: {indicator_result['signal']}")
            lines.append(self.explain_signal(indicator_result['signal'], indicator_result.get('signal_desc', '')))

        # 战法信号
        if strategy_signals:
            lines.append(f"\n→ 战法信号 ({len(strategy_signals)}个):")
            for sig in strategy_signals[:3]:
                lines.append(f"  • {self.explain_strategy(sig.get('strategy', ''), sig.get('confidence', 0), sig.get('description', ''))}")

        # 结尾语
        lines.append("\n" + "=" * 50)
        lines.append(f"{self._pick(self.DISCIPLINE_PATTERNS)}")
        lines.append("=" * 50)

        return "\n".join(lines)


# 全局实例
z_voice = ZettarancVoice()


def explain_kdj(k: float, d: float, j: float) -> str:
    return z_voice.explain_kdj(k, d, j)


def explain_macd(dif: float, dea: float, macd_hist: float) -> str:
    return z_voice.explain_macd(dif, dea, macd_hist)


def explain_bbi(price: float, bbi: float) -> str:
    return z_voice.explain_bbi(price, bbi)


def explain_sell_score(score: int, reasons: str = "") -> str:
    return z_voice.explain_sell_score(score, reasons)


def explain_rsi(rsi6: float, rsi12: float, rsi24: float) -> str:
    return z_voice.explain_rsi(rsi6, rsi12, rsi24)


def explain_wr(wr5: float, wr10: float) -> str:
    return z_voice.explain_wr(wr5, wr10)


def explain_bollinger(price: float, boll_mid: float, boll_upper: float,
                     boll_lower: float, boll_width: float, boll_position: float) -> str:
    return z_voice.explain_bollinger(price, boll_mid, boll_upper, boll_lower, boll_width, boll_position)


def explain_double_line(white_line: float, yellow_line: float,
                       is_gold_cross: bool, is_dead_cross: bool) -> str:
    return z_voice.explain_double_line(white_line, yellow_line, is_gold_cross, is_dead_cross)


def explain_needle_20(rsl_short: float, rsl_long: float, is_needle: bool) -> str:
    return z_voice.explain_needle_20(rsl_short, rsl_long, is_needle)


def explain_brick(brick_value: float, brick_trend: str, brick_count: int,
                 trend_up: bool, is_fanbao: bool,
                 macd_hist: float = 0, dif: float = 0) -> str:
    return z_voice.explain_brick(brick_value, brick_trend, brick_count, trend_up, is_fanbao, macd_hist, dif)


def summarize_as_z(result: Dict[str, Any], strategies: List[Dict] = None) -> str:
    return z_voice.summarize(result, strategies)


# 测试
if __name__ == "__main__":
    v = ZettarancVoice()

    print("=" * 60)
    print("Z哥 风格解读 V2.0 测试")
    print("=" * 60)

    # 测试多次随机
    print("\n【KDJ解读测试 - 多次随机】")
    for j in [-20, -10, 50, 88]:
        print(f"\nJ={j}:")
        print(v.explain_kdj(50, 30, j))

    print("\n【综合总结测试】")
    result = {
        'ts_code': '000001.SZ',
        'trade_date': '20260427',
        'k': 51.06,
        'd': 32.37,
        'j': 88.43,
        'dif': -0.0898,
        'dea': -0.0884,
        'macd_hist': -0.0027,
        'bbi': 9.93,
        'close': 11.38,
        'ma5': 10.04,
        'ma10': 9.95,
        'ma20': 10.12,
        'sell_score': 5,
        'signal': 'HOLD',
        'signal_desc': '价格在BBI上方'
    }
    print(v.summarize(result))
