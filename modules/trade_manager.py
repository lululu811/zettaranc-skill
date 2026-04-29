"""
交易记录管理模块
封装 trade_records 表的 CRUD 操作
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from .database import (
    save_trade_record,
    get_trade_records,
    get_trade_record_by_id,
    update_trade_record,
    delete_trade_record,
    get_trade_summary
)
from .indicators import analyze_stock
from .strategies import detect_all_strategies


class TradeManager:
    """交易记录管理器"""

    def __init__(self):
        pass

    def add_trade(self, trade_data: Dict[str, Any]) -> int:
        """
        添加交易记录

        Args:
            trade_data: 交易数据字典

        Returns:
            记录ID
        """
        return save_trade_record(trade_data)

    def get_recent_trades(self, limit: int = 10, action: str = None) -> List[Dict]:
        """获取最近的交易记录"""
        return get_trade_records(action=action, limit=limit)

    def get_trades_by_stock(self, ts_code: str, limit: int = 50) -> List[Dict]:
        """获取指定股票的交易记录"""
        return get_trade_records(ts_code=ts_code, limit=limit)

    def get_trades_by_period(self, start_date: str, end_date: str = None, ts_code: str = None) -> List[Dict]:
        """获取指定时间段的交易记录"""
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        return get_trade_records(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )

    def get_trade_history(self, ts_code: str, days: int = 30) -> List[Dict]:
        """获取股票的历史交易记录（最近N天）"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        return get_trade_records(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date
        )

    def update_trade_info(self, trade_id: int, **kwargs) -> bool:
        """更新交易记录"""
        return update_trade_record(trade_id, kwargs)

    def delete_trade(self, trade_id: int) -> bool:
        """删除交易记录"""
        return delete_trade_record(trade_id)

    def link_strategy(self, trade_id: int, signal_type: str, reason: str = "") -> bool:
        """关联战法到交易记录"""
        return update_trade_record(trade_id, {
            "signal_type": signal_type,
            "reason": reason
        })

    def add_review(self, trade_id: int, zg_review: str) -> bool:
        """添加Z哥点评"""
        return update_trade_record(trade_id, {"zg_review": zg_review})

    def get_summary(self, ts_code: str = None, start_date: str = None, end_date: str = None) -> Dict:
        """获取交易汇总"""
        return get_trade_summary(ts_code=ts_code, start_date=start_date, end_date=end_date)

    def get_stock_holding(self, ts_code: str) -> Dict:
        """
        计算股票持仓情况
        根据买卖记录计算当前持仓数量和平均成本
        """
        trades = self.get_trades_by_stock(ts_code, limit=1000)

        total_buy_qty = 0
        total_buy_amount = 0
        total_sell_qty = 0
        total_sell_amount = 0

        for trade in trades:
            if trade['action'] == 'BUY':
                total_buy_qty += trade['quantity']
                total_buy_amount += trade['amount']
            elif trade['action'] == 'SELL':
                total_sell_qty += trade['quantity']
                total_sell_amount += trade['amount']

        current_qty = total_buy_qty - total_sell_qty
        avg_cost = total_buy_amount / total_buy_qty if total_buy_qty > 0 else 0

        return {
            "ts_code": ts_code,
            "total_buy": total_buy_qty,
            "total_sell": total_sell_qty,
            "current_qty": current_qty,
            "avg_cost": round(avg_cost, 2),
            "total_cost": total_buy_amount,
            "total_profit": total_sell_amount - (current_qty * avg_cost) if current_qty > 0 else total_sell_amount
        }

    def check_trade_conditions(self, trade_id: int) -> Dict[str, Any]:
        """
        检查交易当时的指标条件

        Returns:
            当时的K线数据、指标数据、是否匹配战法
        """
        trade = get_trade_record_by_id(trade_id)
        if not trade:
            return {}

        ts_code = trade['ts_code']
        trade_date = trade['trade_date']

        # 获取交易当天的指标数据
        indicators = get_indicator_data(ts_code, trade_date)
        stock_info = get_stock_info(ts_code)

        # 尝试匹配战法
        strategy_result = match_strategy(indicators) if indicators else None

        return {
            "trade": trade,
            "stock_info": stock_info,
            "indicators": indicators,
            "matched_strategy": strategy_result
        }

    def list_all_trades(self, page: int = 1, page_size: int = 20) -> Dict:
        """
        分页列出所有交易记录

        Returns:
            包含 records 和 total 的字典
        """
        offset = (page - 1) * page_size
        records = get_trade_records(limit=page_size)

        # 这里简化处理，实际应该用 SQL 的 COUNT
        all_records = get_trade_records(limit=1000)
        total = len(all_records)

        return {
            "records": records[offset:offset+page_size],
            "total": total,
            "page": page,
            "page_size": page_size
        }

    def export_to_dict(self, ts_code: str = None, start_date: str = None, end_date: str = None) -> List[Dict]:
        """导出交易记录为列表"""
        return get_trade_records(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )

    def calculate_pnl(self, ts_code: str = None) -> Dict:
        """
        计算盈亏情况

        Returns:
            包含买入总额、卖出总额、当前持仓、市值（如果有实时价格）等
        """
        trades = get_trade_records(ts_code=ts_code, limit=10000)

        buy_total = 0  # 买入总额
        sell_total = 0  # 卖出总额
        buy_qty = 0    # 买入股数
        sell_qty = 0   # 卖出股数

        for trade in trades:
            if trade['action'] == 'BUY':
                buy_total += trade['amount']
                buy_qty += trade['quantity']
            elif trade['action'] == 'SELL':
                sell_total += trade['amount']
                sell_qty += trade['quantity']

        current_qty = buy_qty - sell_qty

        return {
            "buy_total": round(buy_total, 2),
            "sell_total": round(sell_total, 2),
            "net_invested": round(buy_total - sell_total, 2),
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "current_qty": current_qty,
            "realized_pnl": round(sell_total - (sell_qty * (buy_total / buy_qty if buy_qty > 0 else 0)), 2)
        }


# 全局实例
trade_manager = TradeManager()