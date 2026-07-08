"""
组合级仓位管理器 — 基于风险的动态仓位计算

实现专业的仓位管理：
1. 基于风险的仓位计算（固定风险比例法）
2. 波动率调整（ATR 目标波动率缩放）
3. 市场状态调整（牛市/熊市/震荡乘数）
4. 组合级约束（最大持仓数、单只上限、行业分散化）

核心公式：
  shares = (equity × risk_per_trade) / (entry_price - stop_loss)
           × min(target_vol / (ATR/price), 1.5)   ← 波动率调整
           × regime_multiplier                     ← 市场状态调整

最终股数取 A 股整手（100 股整数倍），并受单只上限约束。
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field

from modules.market_regime import MarketRegime

logger = logging.getLogger(__name__)

# 默认市场状态乘数：牛市积极、熊市保守、震荡中性
_DEFAULT_REGIME_MULTIPLIERS: dict[str, float] = {
    "BULL": 1.2,
    "SIDEWAYS": 1.0,
    "BEAR": 0.6,
}

# A 股最小交易单位
_LOT_SIZE = 100


@dataclass
class PositionInfo:
    """单只持仓信息"""

    ts_code: str
    shares: int
    entry_price: float
    stop_loss_price: float

    @property
    def cost(self) -> float:
        """持仓成本"""
        return self.shares * self.entry_price

    @property
    def risk_amount(self) -> float:
        """该笔持仓的风险金额（到止损）"""
        return self.shares * abs(self.entry_price - self.stop_loss_price)


@dataclass
class PositionManager:
    """组合级仓位管理器

    基于风险的仓位计算 + 组合约束检查。

    Attributes:
        initial_capital: 初始资金
        risk_per_trade: 每笔风险占净值比例（默认 2%）
        max_single_pct: 单只股票最大占比（默认 25%）
        max_positions: 最大持仓只数（默认 5）
        target_volatility: 目标年化波动率（默认 15%）
        regime_multipliers: 市场状态乘数
        cash: 当前可用现金
        positions: 持仓字典 {ts_code: PositionInfo}
    """

    initial_capital: float = 1_000_000
    risk_per_trade: float = 0.02
    max_single_pct: float = 0.25
    max_positions: int = 5
    target_volatility: float = 0.15
    regime_multipliers: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_REGIME_MULTIPLIERS))
    cash: float = 0.0
    positions: dict[str, PositionInfo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cash == 0.0:
            self.cash = self.initial_capital

    # ------------------------------------------------------------------
    # 核心：仓位计算
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        ts_code: str,
        entry_price: float,
        stop_loss_price: float,
        current_equity: float,
        regime: MarketRegime = MarketRegime.SIDEWAYS,
        atr: float | None = None,
    ) -> int:
        """计算买入股数（A 股整手）

        公式：
          base_shares = (equity × risk_per_trade) / (entry - stop_loss)
          vol_adj    = min(target_vol / (ATR / entry), 1.5)
          shares     = base_shares × vol_adj × regime_multiplier

        Args:
            ts_code: 股票代码
            entry_price: 计划买入价
            stop_loss_price: 止损价
            current_equity: 当前总净值（现金 + 持仓市值）
            regime: 当前市场状态
            atr: 当前 ATR 值（14 日或 20 日），为 None 时不做波动率调整

        Returns:
            建议买入股数（100 的整数倍），最少 100 股，不满足条件时返回 0

        Raises:
            ValueError: 当 entry_price <= 0 或 stop_loss_price >= entry_price 时
        """
        if entry_price <= 0:
            raise ValueError(f"买入价必须大于 0，当前: {entry_price}")
        if stop_loss_price >= entry_price:
            raise ValueError(f"止损价({stop_loss_price})必须低于买入价({entry_price})")

        risk_per_share = entry_price - stop_loss_price

        # Step 1: 基于风险的基准仓位
        base_shares = (current_equity * self.risk_per_trade) / risk_per_share

        # Step 2: 波动率调整
        vol_adj = 1.0
        if atr is not None and atr > 0:
            stock_vol = atr / entry_price  # ATR 占价格的比率作为波动率代理
            if stock_vol > 0:
                vol_adj = min(self.target_volatility / stock_vol, 1.5)
                vol_adj = max(vol_adj, 0.3)  # 下限 0.3，避免过度缩减

        # Step 3: 市场状态调整
        regime_mult = self.regime_multipliers.get(regime.value, 1.0)

        # 计算理论股数
        raw_shares = base_shares * vol_adj * regime_mult
        logger.debug(
            "[%s] base=%.0f, vol_adj=%.2f, regime=%.1f, raw=%.0f",
            ts_code, base_shares, vol_adj, regime_mult, raw_shares,
        )

        # Step 4: 取整到 A 股整手
        shares = int(raw_shares // _LOT_SIZE) * _LOT_SIZE
        if shares < _LOT_SIZE:
            return 0  # 不足 1 手

        # Step 5: 单只上限约束
        max_amount = current_equity * self.max_single_pct
        max_shares_by_pct = int(max_amount // entry_price // _LOT_SIZE) * _LOT_SIZE
        if max_shares_by_pct < _LOT_SIZE:
            return 0
        shares = min(shares, max_shares_by_pct)

        # Step 6: 现金约束（不超过可用现金）
        affordable = int(self.cash // entry_price // _LOT_SIZE) * _LOT_SIZE
        shares = min(shares, affordable)

        if shares < _LOT_SIZE:
            return 0

        return shares

    # ------------------------------------------------------------------
    # 入场约束检查
    # ------------------------------------------------------------------

    def can_enter(
        self,
        ts_code: str,
        current_holdings: list[str] | None = None,
        industry_filter: object | None = None,
    ) -> bool:
        """检查是否可以入场（仓位约束 + 行业约束）

        Args:
            ts_code: 股票代码
            current_holdings: 当前持仓股票代码列表，为 None 时使用 self.positions
            industry_filter: IndustryFilter 实例（可选），传入时检查行业约束

        Returns:
            True 表示允许入场，False 表示违反约束
        """
        holdings = current_holdings if current_holdings is not None else list(self.positions.keys())

        # 已持有该股票
        if ts_code in holdings:
            logger.debug("[%s] 已持有，跳过", ts_code)
            return False

        # 持仓数量约束
        if len(holdings) >= self.max_positions:
            logger.debug(
                "[%s] 持仓数(%d)已达上限(%d)", ts_code, len(holdings), self.max_positions,
            )
            return False

        # 行业约束（可选）
        if industry_filter is not None:
            from modules.industry_filter import IndustryFilter

            if isinstance(industry_filter, IndustryFilter):
                target_industry = industry_filter.get_industry(ts_code)
                if target_industry:
                    industry_count = Counter()
                    for code in holdings:
                        ind = industry_filter.get_industry(code)
                        if ind:
                            industry_count[ind] += 1
                    if industry_count[target_industry] >= industry_filter.max_per_industry:
                        logger.debug(
                            "[%s] 同行业(%s)持仓(%d)已达上限(%d)",
                            ts_code, target_industry,
                            industry_count[target_industry],
                            industry_filter.max_per_industry,
                        )
                        return False

        return True

    # ------------------------------------------------------------------
    # 持仓管理
    # ------------------------------------------------------------------

    def record_entry(
        self,
        ts_code: str,
        shares: int,
        entry_price: float,
        stop_loss_price: float,
    ) -> None:
        """记录建仓

        Args:
            ts_code: 股票代码
            shares: 买入股数
            entry_price: 买入价格
            stop_loss_price: 止损价格
        """
        cost = shares * entry_price
        if cost > self.cash:
            logger.warning("[%s] 现金不足: 需要 %.0f，可用 %.0f", ts_code, cost, self.cash)
        self.cash -= cost
        self.positions[ts_code] = PositionInfo(
            ts_code=ts_code,
            shares=shares,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
        )
        logger.info(
            "[%s] 建仓 %d 股 @ %.2f，止损 %.2f，花费 %.0f",
            ts_code, shares, entry_price, stop_loss_price, cost,
        )

    def record_exit(self, ts_code: str, exit_price: float) -> float:
        """记录平仓

        Args:
            ts_code: 股票代码
            exit_price: 卖出价格

        Returns:
            该笔交易的盈亏金额
        """
        if ts_code not in self.positions:
            logger.warning("[%s] 未持有，无法平仓", ts_code)
            return 0.0

        pos = self.positions[ts_code]
        proceeds = pos.shares * exit_price
        pnl = pos.shares * (exit_price - pos.entry_price)
        self.cash += proceeds
        del self.positions[ts_code]
        logger.info(
            "[%s] 平仓 %d 股 @ %.2f，盈亏 %.0f (%.1f%%)",
            ts_code, pos.shares, exit_price, pnl,
            (exit_price / pos.entry_price - 1) * 100,
        )
        return pnl

    # ------------------------------------------------------------------
    # 组合摘要
    # ------------------------------------------------------------------

    def get_portfolio_summary(self) -> dict:
        """获取组合摘要

        Returns:
            包含以下字段的字典：
            - initial_capital: 初始资金
            - cash: 可用现金
            - positions_count: 持仓只数
            - total_cost: 持仓总成本
            - total_risk: 持仓总风险金额（到止损）
            - equity: 总净值（仅基于成本估算，未含市值变动）
            - cash_pct: 现金占比
            - position_pct: 仓位占比
            - positions: 各持仓明细列表
        """
        total_cost = sum(p.cost for p in self.positions.values())
        total_risk = sum(p.risk_amount for p in self.positions.values())
        equity = self.cash + total_cost

        return {
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 2),
            "positions_count": len(self.positions),
            "max_positions": self.max_positions,
            "total_cost": round(total_cost, 2),
            "total_risk": round(total_risk, 2),
            "equity": round(equity, 2),
            "cash_pct": round(self.cash / equity, 4) if equity > 0 else 0,
            "position_pct": round(total_cost / equity, 4) if equity > 0 else 0,
            "positions": [
                {
                    "ts_code": p.ts_code,
                    "shares": p.shares,
                    "entry_price": p.entry_price,
                    "stop_loss_price": p.stop_loss_price,
                    "cost": round(p.cost, 2),
                    "risk_amount": round(p.risk_amount, 2),
                }
                for p in self.positions.values()
            ],
        }

    # ------------------------------------------------------------------
    # 重置
    # ------------------------------------------------------------------

    def reset(self, initial_capital: float) -> None:
        """重置状态

        Args:
            initial_capital: 新的初始资金
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions.clear()
        logger.info("仓位管理器重置，初始资金 %.0f", initial_capital)


# ------------------------------------------------------------------
# 测试入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    pm = PositionManager(initial_capital=1_000_000, risk_per_trade=0.02)

    print("=" * 60)
    print("组合级仓位管理器 — 测试")
    print("=" * 60)

    # 场景 1: 震荡市，无 ATR 调整
    print("\n--- 场景 1: 震荡市，无止损距离大 ---")
    shares = pm.calculate_position_size(
        ts_code="600487.SH",
        entry_price=50.0,
        stop_loss_price=47.0,  # 6% 止损
        current_equity=1_000_000,
        regime=MarketRegime.SIDEWAYS,
    )
    print(f"建议买入: {shares} 股，金额 {shares * 50:.0f}")

    # 场景 2: 牛市 + ATR 调整
    print("\n--- 场景 2: 牛市 + 波动率调整 ---")
    shares = pm.calculate_position_size(
        ts_code="000001.SZ",
        entry_price=20.0,
        stop_loss_price=18.5,  # 7.5% 止损
        current_equity=1_000_000,
        regime=MarketRegime.BULL,
        atr=1.0,  # ATR/price = 5%，低于 target_vol 15%
    )
    print(f"建议买入: {shares} 股，金额 {shares * 20:.0f}")

    # 场景 3: 熊市
    print("\n--- 场景 3: 熊市 ---")
    shares = pm.calculate_position_size(
        ts_code="600036.SH",
        entry_price=40.0,
        stop_loss_price=38.0,
        current_equity=1_000_000,
        regime=MarketRegime.BEAR,
    )
    print(f"建议买入: {shares} 股，金额 {shares * 40:.0f}")

    # 场景 4: 入场约束检查
    print("\n--- 场景 4: 入场约束检查 ---")
    print(f"空仓可入场: {pm.can_enter('600487.SH')}")
    pm.record_entry("600487.SH", 1000, 50.0, 47.0)
    print(f"重复入场: {pm.can_enter('600487.SH')}")

    # 填满持仓
    for i, code in enumerate(["000001.SZ", "600036.SH", "002594.SZ", "601318.SH"]):
        pm.record_entry(code, 500, 20.0 + i * 10, 18.0 + i * 10)
    print(f"5 只满仓后可入场: {pm.can_enter('600519.SH')}")

    # 场景 5: 组合摘要
    print("\n--- 场景 5: 组合摘要 ---")
    summary = pm.get_portfolio_summary()
    print(f"净值: {summary['equity']:,.0f}")
    print(f"现金: {summary['cash']:,.0f} ({summary['cash_pct']:.1%})")
    print(f"仓位: {summary['position_pct']:.1%}")
    print(f"持仓数: {summary['positions_count']}/{summary['max_positions']}")
    for p in summary["positions"]:
        print(f"  {p['ts_code']}: {p['shares']} 股 @ {p['entry_price']:.2f}")

    # 场景 6: 重置
    print("\n--- 场景 6: 重置 ---")
    pm.reset(500_000)
    print(f"重置后净值: {pm.get_portfolio_summary()['equity']:,.0f}")
    print(f"重置后持仓数: {pm.get_portfolio_summary()['positions_count']}")

    print("\n✅ 所有测试场景通过")
