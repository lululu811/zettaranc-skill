"""
交割单模块
只负责数据准备，不生成点评（点评由 LLM 用 Z哥角色输出）
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from .database import get_connection, save_trade_record, get_trade_record_by_id, get_trade_records
from .indicators import analyze_stock
from .trade_parser import TradeParser, ParseResult
from .zettaranc_voice import TRADE_REVIEW_PROMPT, JARGON_DICT


@dataclass
class ReviewContext:
    """点评上下文 - 准备给 LLM 的数据包"""
    # 基础交易信息
    ts_code: str
    name: str
    trade_date: str
    action: str  # BUY/SELL
    price: float
    quantity: int
    amount: float
    reason: str

    # 计算数据（买点/卖点特有）
    avg_cost: Optional[float] = None  # 对于卖出，计算平均成本
    profit_pct: Optional[float] = None  # 对于卖出，计算盈亏比例
    holding_days: Optional[int] = None  # 持仓天数

    # 指标数据（获取当时的）
    indicators: Optional[Dict] = None  # 当时的技术指标

    # 对应交易
    matched_buy: Optional[Dict] = None  # 对于卖出，找对应的买入
    matched_sell: Optional[Dict] = None  # 对于买入，找对应的卖出

    # 元数据
    is_complete_trade: bool = False  # 是否是完整交易（有买有卖）
    signal_type: Optional[str] = None  # 卤煮/止损/卖飞/建仓
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_llm_prompt(self) -> str:
        """转换为给 LLM 的提示词"""
        parts = [f"【交易记录】"]

        # 基础信息
        action_text = "买入" if self.action == "BUY" else "卖出"
        parts.append(f"股票: {self.name} ({self.ts_code})")
        parts.append(f"日期: {self.trade_date}")
        parts.append(f"操作: {action_text}")
        parts.append(f"价格: {self.price}元")
        parts.append(f"数量: {self.quantity}股")
        parts.append(f"金额: {self.amount}元")
        parts.append(f"原因: {self.reason}")

        # 盈亏（如果是卖出）
        if self.action == "SELL" and self.profit_pct is not None:
            if self.profit_pct >= 0:
                parts.append(f"收益: 盈利{self.profit_pct:.1f}%")
            else:
                parts.append(f"收益: 亏损{abs(self.profit_pct):.1f}%")

        # 持仓天数
        if self.holding_days is not None:
            parts.append(f"持仓天数: {self.holding_days}天")

        # 信号类型
        if self.signal_type:
            parts.append(f"信号类型: {self.signal_type}")

        # 指标数据
        if self.indicators:
            ind = self.indicators
            parts.append("")
            parts.append("【当时技术指标】")
            if 'j' in ind and ind['j']:
                parts.append(f"J值: {ind['j']:.1f}")
            if 'k' in ind and ind['k']:
                parts.append(f"KDJ: K={ind['k']:.1f} D={ind['d']:.1f}")
            if 'bbi' in ind and ind['bbi']:
                parts.append(f"BBI: {ind['bbi']:.2f}")
            if 'signal' in ind:
                parts.append(f"信号: {ind['signal']}")
            if 'sell_score' in ind:
                parts.append(f"防卖飞评分: {ind['sell_score']}/5")

        # 完整交易信息
        if self.is_complete_trade:
            parts.append("")
            parts.append("【这是完整的一笔交易】")
            if self.matched_buy:
                parts.append(f"买入价: {self.matched_buy.get('price')}元")
            if self.matched_sell:
                parts.append(f"卖出价: {self.matched_sell.get('price')}元")

        # 标签
        if self.tags:
            parts.append(f"标签: {', '.join(self.tags)}")

        return "\n".join(parts)

    def get_full_prompt(self) -> str:
        """获取完整的 LLM 提示词（包含角色提示 + 数据）"""
        return f"{TRADE_REVIEW_PROMPT}\n\n---\n\n{self.to_llm_prompt()}\n\n---\n\n请以 Z哥的口吻点评这笔交易。"

    def get_jargon_hint(self) -> str:
        """获取黑话提示"""
        hints = [f"- {k}: {v}" for k, v in JARGON_DICT.items()]
        return "黑话提示：\n" + "\n".join(hints)


class TradeReviewer:
    """交割单 - 数据准备层"""

    def __init__(self):
        self.parser = TradeParser()

    def parse_input(self, text: str) -> Tuple[ParseResult, Optional[Dict]]:
        """
        解析用户输入
        Returns: (解析结果, 状态数据)
        """
        result = self.parser.parse(text)
        return result, result.data

    def prepare_review_context(self, data: Dict, action_type: str = None, extra_info: Dict = None) -> ReviewContext:
        """
        准备点评上下文

        Args:
            data: 解析后的交易数据
            action_type: 交易类型 BUY/SELL
            extra_info: 额外信息（如卤煮/止损/建仓等）
        """
        ctx = ReviewContext(
            ts_code=data.get('ts_code', ''),
            name=data.get('name', data.get('ts_code', '')),
            trade_date=data.get('trade_date', datetime.now().strftime('%Y-%m-%d')),
            action=action_type or data.get('action', 'BUY'),
            price=data.get('price', 0),
            quantity=data.get('quantity', 0),
            amount=data.get('amount', 0),
            reason=data.get('reason', '')
        )

        # 如果有额外信息
        if extra_info:
            if 'signal_type' in extra_info:
                ctx.signal_type = extra_info['signal_type']
            if 'tags' in extra_info:
                ctx.tags = extra_info['tags']

        return ctx

    def enrich_with_indicators(self, ctx: ReviewContext, days: int = 60) -> ReviewContext:
        """补充当时的技术指标数据"""
        try:
            result = analyze_stock(ctx.ts_code, days=days)
            if result:
                ctx.indicators = {
                    'j': getattr(result, 'j', None),
                    'k': getattr(result, 'k', None),
                    'd': getattr(result, 'd', None),
                    'bbi': getattr(result, 'bbi', None),
                    'signal': getattr(result, 'signal', None),
                    'sell_score': getattr(result, 'sell_score', None),
                    'pct_chg': getattr(result, 'pct_chg', None),
                }
        except Exception as e:
            print(f"获取指标失败: {e}")

        return ctx

    def enrich_with_buy_info(self, ctx: ReviewContext) -> ReviewContext:
        """对于卖出，补充买入信息和盈亏计算"""
        trades = get_trade_records(ts_code=ctx.ts_code, limit=100)
        buy_trades = [t for t in trades if t.get('action') == 'BUY']

        if buy_trades:
            # 计算平均成本
            total_amount = sum(t.get('amount', 0) for t in buy_trades)
            total_qty = sum(t.get('quantity', 0) for t in buy_trades)
            ctx.avg_cost = total_amount / total_qty if total_qty > 0 else 0

            # 计算盈亏
            if ctx.price > 0 and ctx.avg_cost > 0:
                ctx.profit_pct = ((ctx.price - ctx.avg_cost) / ctx.avg_cost) * 100

            # 计算持仓天数（第一笔买入到卖出）
            first_buy = buy_trades[-1]
            if first_buy.get('trade_date') and ctx.trade_date:
                try:
                    d1 = datetime.strptime(first_buy['trade_date'], '%Y-%m-%d')
                    d2 = datetime.strptime(ctx.trade_date, '%Y-%m-%d')
                    ctx.holding_days = (d2 - d1).days
                except:
                    pass

            ctx.matched_buy = {
                'price': ctx.avg_cost,
                'date': first_buy.get('trade_date'),
                'quantity': total_qty
            }

        return ctx

    def check_if_complete_trade(self, ctx: ReviewContext) -> ReviewContext:
        """检查是否有对应的买卖交易"""
        trades = get_trade_records(ts_code=ctx.ts_code, limit=100)

        if ctx.action == 'BUY':
            # 查找是否有卖出
            sell_trades = [t for t in trades if t.get('action') == 'SELL']
            if sell_trades:
                ctx.is_complete_trade = True
                ctx.matched_sell = sell_trades[0]
        else:
            # 查找是否有买入
            buy_trades = [t for t in trades if t.get('action') == 'BUY']
            if buy_trades:
                ctx.is_complete_trade = True

        return ctx

    def save_trade(self, ctx: ReviewContext) -> int:
        """保存交易记录"""
        record = {
            'ts_code': ctx.ts_code,
            'trade_date': ctx.trade_date,
            'action': ctx.action,
            'price': ctx.price,
            'quantity': ctx.quantity,
            'amount': ctx.amount,
            'reason': ctx.reason,
            'signal_type': ctx.signal_type or '',
            'tags': ','.join(ctx.tags) if ctx.tags else '',
        }
        return save_trade_record(record)


def create_reviewer() -> TradeReviewer:
    """创建复盘器实例"""
    return TradeReviewer()


# 全局实例
reviewer = TradeReviewer()