"""组合级回测引擎（v3.7.6，v3.9.0 迁移到 backtest/，v3.10.0 多策略融合）

每日扫描多策略信号、动态选股、维护真实组合账户，从组合资金曲线计算
年化 / Sharpe / MaxDD / Calmar。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from ..core.metrics import TRADING_DAYS_PER_YEAR, compute_drawdown, compute_sharpe, daily_returns
from ..core.market_context import MarketContext, MarketRegime
from ..indicators import DailyData, get_kline_data
from ..loop_engine import LoopConfig, LoopTrade, ShaofuLoopEngine, _calc_stop_loss_price
from ..simulator.market_context import precompute_market_contexts

# 多策略检测函数（延迟导入避免循环依赖）
from ..strategies.base_strategies import detect_b1, detect_b2, detect_sb1
from ..strategies.compound_strategies import detect_changan

logger = logging.getLogger(__name__)


@dataclass
class EntrySignal:
    """单策略入场信号"""

    strategy: str          # "B1", "B2", "长安", "SB1"
    confidence: float      # 置信度 0-1
    reason: str           # 信号原因
    stop_loss_price: float # 建议止损价


# 策略检测函数映射：策略名 -> (detector_func, default_weight)
STRATEGY_DETECTORS: dict[str, tuple] = {
    "B1": (detect_b1, 1.0),
    "B2": (detect_b2, 0.8),
    "SB1": (detect_sb1, 1.2),
    "长安": (detect_changan, 0.9),
}


# 策略名 -> StrategyType 映射（用于 entry_reason）
STRATEGY_NAME_TO_TYPE: dict[str, str] = {
    "B1": "B1",
    "B2": "B2",
    "SB1": "SB1",
    "长安": "长安战法",
}


@dataclass
class MarketAdaptiveConfig:
    """市场环境自适应择时配置（v3.8.0）

    根据上一交易日的市场环境（STRONG/NEUTRAL/WEAK）动态调整仓位参数。
    所有 factor 在 enabled=False 时不生效。
    """

    enabled: bool = False
    weak_no_new_entries: bool = True          # 弱势日是否禁止新开仓
    strong_max_positions_factor: float = 1.0  # 强势日 max_positions 乘数
    neutral_max_positions_factor: float = 1.0 # 震荡日 max_positions 乘数
    weak_max_positions_factor: float = 0.0    # 弱势日 max_positions 乘数（0=空仓）
    strong_position_pct_factor: float = 1.0
    neutral_position_pct_factor: float = 1.0
    weak_position_pct_factor: float = 0.5
    strong_max_entries_factor: float = 1.0
    neutral_max_entries_factor: float = 1.0
    weak_max_entries_factor: float = 0.0


@dataclass
class PortfolioConfig:
    """组合回测配置"""

    initial_capital: float = 1_000_000.0
    max_positions: int = 5           # 最多同时持仓数
    position_pct: float = 0.2        # 单票占组合净值比例
    min_cash_pct: float = 0.05       # 最低现金保留比例
    max_entries_per_day: int = 2     # 每日最多新买入几只
    commission_rate: float = 0.00025 # 佣金
    min_commission: float = 5.0      # 佣金最低 5 元
    stamp_duty_rate: float = 0.0005  # 印花税（卖出）
    min_signal_days: int = 30        # 最少需要多少根 K 线才检查信号
    adaptive: MarketAdaptiveConfig = field(default_factory=MarketAdaptiveConfig)
    # v3.10.0 多策略融合配置
    enabled_strategies: list[str] = field(default_factory=lambda: ["B1"])
    strategy_weights: dict[str, float] = field(default_factory=lambda: {
        "B1": 1.0, "B2": 0.8, "SB1": 1.2, "长安": 0.9
    })
    min_composite_score: float = 0.3


@dataclass
class Position:
    """组合中的一笔持仓"""

    ts_code: str
    shares: int                      # 持股数（A股100整数倍）
    entry_price: float
    entry_date: str
    cost_basis: float                # 含手续费的总成本
    trade: LoopTrade                 # 当前持仓交易对象


@dataclass
class PortfolioBacktestResult:
    """组合回测结果"""

    dates: list[str] = field(default_factory=list)
    net_values: list[float] = field(default_factory=list)
    cash_history: list[float] = field(default_factory=list)
    trades: list[LoopTrade] = field(default_factory=list)
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    calmar: float = 0.0


class PortfolioBacktestEngine:
    """组合级回测引擎

    每日流程：
    1. 处理持仓离场（调用 ShaofuLoopEngine.process_day）
    2. 扫描 universe 中未持仓股票的 B1 信号
    3. 按资金和仓位规则买入
    4. 记录当日组合净值
    """

    def __init__(
        self,
        portfolio_config: PortfolioConfig | None = None,
        loop_config: LoopConfig | None = None,
    ):
        self.portfolio_config = portfolio_config or PortfolioConfig()
        self.loop_config = loop_config or LoopConfig()
        self.loop_engine = ShaofuLoopEngine(self.loop_config)

    def load_data(
        self,
        ts_codes: list[str],
        days: int,
    ) -> tuple[dict[str, list[DailyData]], list[str]]:
        """加载 K 线并返回 {ts_code: klines} 与升序交易日列表

        数据只加载一次，可重复传给 run_with_data 跑不同日期窗口。
        """
        klines_map = self._load_klines(ts_codes, days)
        all_dates = self._build_date_index(klines_map)
        return klines_map, all_dates

    def run_with_data(
        self,
        klines_map: dict[str, list[DailyData]],
        all_dates: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> PortfolioBacktestResult:
        """在已加载数据上运行组合回测，可限定日期窗口

        Args:
            klines_map: 候选股票 K 线字典
            all_dates: 升序交易日列表（通常来自 load_data）
            start_date: 窗口起始日（含），None 表示从头开始
            end_date: 窗口结束日（含），None 表示到最后

        Returns:
            PortfolioBacktestResult
        """
        if not klines_map or not all_dates:
            return PortfolioBacktestResult()

        # 日期窗口切片（保留 K 线数据用于指标热身）
        window_dates = all_dates
        if start_date is not None or end_date is not None:
            window_dates = [
                d
                for d in all_dates
                if (start_date is None or d >= start_date)
                and (end_date is None or d <= end_date)
            ]
        if not window_dates:
            return PortfolioBacktestResult()

        logger.info(
            "组合回测窗口: dates=%d, start=%s, end=%s",
            len(window_dates),
            window_dates[0],
            window_dates[-1],
        )

        # 为每只股票建立 date -> index 映射
        date_index_map: dict[str, dict[str, int]] = {}
        for code, klines in klines_map.items():
            date_index_map[code] = {k.trade_date: i for i, k in enumerate(klines)}

        # 初始化账户
        config = self.portfolio_config
        cash = config.initial_capital
        positions: dict[str, Position] = {}
        completed_trades: list[LoopTrade] = []

        dates: list[str] = []
        net_values: list[float] = []
        cash_history: list[float] = []

        # 预计算市场环境（用上一交易日context做择时开关，避免偷看当天）
        market_contexts: dict[str, MarketContext] = {}
        if config.adaptive.enabled:
            try:
                market_contexts = precompute_market_contexts(window_dates)
            except Exception as e:  # noqa: BLE001
                logger.warning("市场环境预计算失败，回退到默认震荡: %s", e)

        for idx, date in enumerate(window_dates):
            # 取上一交易日的市场环境；首日无数据则默认 NEUTRAL
            prev_date = window_dates[idx - 1] if idx > 0 else None
            prev_context = None
            if prev_date is not None:
                prev_context = market_contexts.get(prev_date)
            if prev_context is None:
                prev_context = MarketContext(
                    date=date,
                    regime=MarketRegime.NEUTRAL,
                    index_trend=50.0,
                    breadth=0.0,
                    moneyflow_score=50.0,
                )

            # Step 1: 处理持仓离场
            cash = self._process_exits(
                date=date,
                klines_map=klines_map,
                date_index_map=date_index_map,
                positions=positions,
                cash=cash,
                completed_trades=completed_trades,
            )

            # Step 2 & 3: 扫描 B1 并买入
            cash = self._scan_and_buy(
                date=date,
                klines_map=klines_map,
                date_index_map=date_index_map,
                positions=positions,
                cash=cash,
                net_value=self._calc_net_value(cash, positions, klines_map, date_index_map, date),
                prev_context=prev_context,
            )

            # Step 4: 记录净值
            net_value = self._calc_net_value(cash, positions, klines_map, date_index_map, date)
            dates.append(date)
            net_values.append(net_value)
            cash_history.append(cash)

        return self._build_result(
            dates=dates,
            net_values=net_values,
            cash_history=cash_history,
            completed_trades=completed_trades,
        )

    def run(
        self,
        ts_codes: list[str],
        days: int = 250,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> PortfolioBacktestResult:
        """运行组合级回测

        Args:
            ts_codes: 候选股票池（universe）
            days: 回测天数
            start_date: 窗口起始日（含）
            end_date: 窗口结束日（含）

        Returns:
            PortfolioBacktestResult
        """
        logger.info(
            "组合回测启动: universe=%d, days=%d, max_positions=%d",
            len(ts_codes),
            days,
            self.portfolio_config.max_positions,
        )

        klines_map, all_dates = self.load_data(ts_codes, days)
        return self.run_with_data(klines_map, all_dates, start_date, end_date)

    def _load_klines(
        self,
        ts_codes: list[str],
        days: int,
    ) -> dict[str, list[DailyData]]:
        """加载所有候选股票的 K 线数据"""
        klines_map: dict[str, list[DailyData]] = {}
        for code in ts_codes:
            try:
                klines = get_kline_data(code, days)
                if klines and len(klines) >= 30:
                    klines_map[code] = klines
            except Exception as e:  # noqa: BLE001
                logger.warning("加载 %s K线失败: %s", code, e)
        return klines_map

    def _build_date_index(self, klines_map: dict[str, list[DailyData]]) -> list[str]:
        """取所有 K 线交易日的并集并排序"""
        dates: set[str] = set()
        for klines in klines_map.values():
            for k in klines:
                dates.add(k.trade_date)
        return sorted(dates)

    def _calc_net_value(
        self,
        cash: float,
        positions: dict[str, Position],
        klines_map: dict[str, list[DailyData]],
        date_index_map: dict[str, dict[str, int]],
        date: str,
    ) -> float:
        """计算当日组合净值 = 现金 + 持仓市值"""
        market_value = 0.0
        for code, pos in positions.items():
            idx = date_index_map.get(code, {}).get(date)
            if idx is not None:
                market_value += pos.shares * klines_map[code][idx].close
            else:
                # 停牌：用最近已知收盘价（ entry_price 近似）
                market_value += pos.shares * pos.entry_price
        return cash + market_value

    def _process_exits(
        self,
        date: str,
        klines_map: dict[str, list[DailyData]],
        date_index_map: dict[str, dict[str, int]],
        positions: dict[str, Position],
        cash: float,
        completed_trades: list[LoopTrade],
    ) -> float:
        """处理持仓离场，返回更新后的现金"""
        for code in list(positions.keys()):
            idx = date_index_map.get(code, {}).get(date)
            min_days = self.portfolio_config.min_signal_days
            if idx is None or idx < min_days:
                continue

            pos = positions[code]
            updated_trade, completed = self.loop_engine.process_day(
                ts_code=code,
                klines=klines_map[code],
                day_idx=idx,
                current_trade=pos.trade,
            )

            if completed is not None:
                # 平仓：按收盘价卖出
                exit_price = completed.exit_price
                sell_amount = pos.shares * exit_price
                commission = max(self.portfolio_config.min_commission, sell_amount * self.portfolio_config.commission_rate)
                stamp_duty = sell_amount * self.portfolio_config.stamp_duty_rate
                cash += sell_amount - commission - stamp_duty
                completed_trades.append(completed)
                del positions[code]
            else:
                # 更新持仓交易对象（止损位等可能变化）
                pos.trade = updated_trade  # type: ignore[assignment]

        return cash

    def _check_multi_entry(
        self,
        klines: list[DailyData],
        idx: int,
        enabled_strategies: list[str],
    ) -> list[EntrySignal]:
        """检测多策略入场信号

        Args:
            klines: 完整 K 线序列
            idx: 当日索引
            enabled_strategies: 启用的策略名列表

        Returns:
            触发的 EntrySignal 列表（可能为空）
        """
        signals: list[EntrySignal] = []
        for strategy_name in enabled_strategies:
            detector = STRATEGY_DETECTORS.get(strategy_name)
            if detector is None:
                continue
            detect_fn, _default_weight = detector
            try:
                sig = detect_fn(klines, idx)
            except Exception:  # noqa: BLE001
                continue
            if sig is None:
                continue
            # 只保留 BUY 类信号
            if sig.action != "BUY":
                continue
            # 计算止损价（v3.10.1：支持 ATR 动态止损）
            stop_price = _calc_stop_loss_price(
                klines, idx,
                self.loop_config.stop_loss_method,
                self.loop_config.stop_loss_pct,
                atr_multiplier=self.loop_config.atr_stop_multiplier,
                atr_window=self.loop_config.atr_stop_window,
            )
            signals.append(EntrySignal(
                strategy=strategy_name,
                confidence=float(sig.confidence or 0.5),
                reason=str(sig.reason or sig.description or strategy_name),
                stop_loss_price=stop_price,
            ))
        return signals

    @staticmethod
    def _score_candidate(
        signals: list[EntrySignal],
        weights: dict[str, float],
    ) -> float:
        """计算候选股票的综合评分

        评分 = sum(confidence * strategy_weight) + 共振奖励
        共振奖励：多策略同时触发时额外加分（每多一个策略 +0.1）

        Args:
            signals: 该股票触发的信号列表
            weights: 策略权重字典

        Returns:
            综合评分（>= 0）
        """
        if not signals:
            return 0.0
        base_score = 0.0
        for sig in signals:
            w = weights.get(sig.strategy, 1.0)
            base_score += sig.confidence * w
        # 共振奖励：多策略同时触发
        if len(signals) > 1:
            base_score += 0.1 * (len(signals) - 1)
        return base_score

    def _scan_and_buy(
        self,
        date: str,
        klines_map: dict[str, list[DailyData]],
        date_index_map: dict[str, dict[str, int]],
        positions: dict[str, Position],
        cash: float,
        net_value: float,
        prev_context: MarketContext | None = None,
    ) -> float:
        """扫描多策略信号并买入，返回更新后的现金

        支持多策略并行检测，按综合评分（置信度 × 策略权重 + 共振奖励）排序。
        prev_context 为上一交易日市场环境，用于自适应仓位控制。
        """
        config = self.portfolio_config
        eff_max_positions, eff_position_pct, eff_max_entries, allow_new = self._resolve_adaptive(
            config, prev_context
        )

        if not allow_new:
            return cash

        available_slots = eff_max_positions - len(positions)
        if available_slots <= 0:
            return cash

        enabled = config.enabled_strategies
        weights = config.strategy_weights
        min_score = config.min_composite_score

        # 收集候选：(code, EntrySignal 列表, 综合评分)
        candidates: list[tuple[str, list[EntrySignal], float]] = []
        for code, klines in klines_map.items():
            if code in positions:
                continue
            idx = date_index_map.get(code, {}).get(date)
            min_days = self.portfolio_config.min_signal_days
            if idx is None or idx < min_days:
                continue

            # 多策略检测
            signals = self._check_multi_entry(klines, idx, enabled)
            if not signals:
                continue

            composite_score = self._score_candidate(signals, weights)
            if composite_score < min_score:
                continue

            candidates.append((code, signals, composite_score))

        if not candidates:
            return cash

        # 按综合评分降序排序
        candidates.sort(key=lambda x: x[2], reverse=True)

        max_new = min(eff_max_entries, available_slots)
        for code, signals, score in candidates[:max_new]:
            idx = date_index_map[code][date]
            price = klines_map[code][idx].close

            # 目标仓位金额
            target_amount = net_value * eff_position_pct
            # 可用现金（扣除保留现金）
            max_cash_use = cash - net_value * config.min_cash_pct
            if max_cash_use <= 0:
                break

            amount = min(target_amount, max_cash_use)
            if amount < price * 100:
                continue

            # A股100股整数倍
            shares = int(amount / price / 100) * 100
            if shares < 100:
                continue

            buy_amount = shares * price
            commission = max(config.min_commission, buy_amount * config.commission_rate)
            total_cost = buy_amount + commission
            if total_cost > cash:
                continue

            # 选取置信度最高的信号作为入场原因
            best_signal = max(signals, key=lambda s: s.confidence)
            strategy_label = STRATEGY_NAME_TO_TYPE.get(best_signal.strategy, best_signal.strategy)
            entry_reason = f"{strategy_label}: {best_signal.reason}"

            # 创建 LoopTrade 持仓对象
            stop_loss = best_signal.stop_loss_price
            trade = LoopTrade(
                ts_code=code,
                entry_date=date,
                entry_price=price,
                entry_reason=entry_reason,
                stop_loss_price=stop_loss,
                position_pct=self.loop_config.position_pct,
            )

            positions[code] = Position(
                ts_code=code,
                shares=shares,
                entry_price=price,
                entry_date=date,
                cost_basis=total_cost,
                trade=trade,
            )
            cash -= total_cost

        return cash

    def _resolve_adaptive(
        self,
        config: PortfolioConfig,
        prev_context: MarketContext | None,
    ) -> tuple[int, float, int, bool]:
        """根据市场环境解析当日有效仓位参数

        Returns:
            (max_positions, position_pct, max_entries_per_day, allow_new)
        """
        ac = config.adaptive
        if not ac.enabled or prev_context is None:
            return config.max_positions, config.position_pct, config.max_entries_per_day, True

        if prev_context.regime == MarketRegime.STRONG:
            mp = int(round(config.max_positions * ac.strong_max_positions_factor))
            pp = config.position_pct * ac.strong_position_pct_factor
            me = int(round(config.max_entries_per_day * ac.strong_max_entries_factor))
        elif prev_context.regime == MarketRegime.WEAK:
            mp = int(round(config.max_positions * ac.weak_max_positions_factor))
            pp = config.position_pct * ac.weak_position_pct_factor
            me = int(round(config.max_entries_per_day * ac.weak_max_entries_factor))
            if ac.weak_no_new_entries:
                return mp, pp, 0, False
        else:  # NEUTRAL
            mp = int(round(config.max_positions * ac.neutral_max_positions_factor))
            pp = config.position_pct * ac.neutral_position_pct_factor
            me = int(round(config.max_entries_per_day * ac.neutral_max_entries_factor))

        return max(mp, 0), pp, max(me, 0), True

    def _recent_return(self, klines: list[DailyData], idx: int, lookback: int = 60) -> float:
        """计算近 lookback 日涨幅，用于买入排序"""
        start = max(0, idx - lookback + 1)
        if start >= idx:
            return 0.0
        first_close = klines[start].close
        last_close = klines[idx].close
        if first_close <= 0:
            return 0.0
        return (last_close - first_close) / first_close

    def _build_result(
        self,
        dates: list[str],
        net_values: list[float],
        cash_history: list[float],
        completed_trades: list[LoopTrade],
        days: int | None = None,  # 兼容旧调用，实际使用 len(net_values)
    ) -> PortfolioBacktestResult:
        """从回测记录构建 PortfolioBacktestResult"""
        result = PortfolioBacktestResult(
            dates=dates,
            net_values=net_values,
            cash_history=cash_history,
            trades=completed_trades,
        )

        if not net_values or len(net_values) < 2:
            return result

        # 交易统计
        result.total_trades = len(completed_trades)
        wins = [t for t in completed_trades if t.pnl_pct > 0]
        result.win_count = len(wins)
        result.loss_count = result.total_trades - result.win_count
        result.win_rate = result.win_count / result.total_trades if result.total_trades > 0 else 0.0

        # 收益：按实际净值序列长度年化，避免日期窗口被截断后失真
        actual_trading_days = len(net_values)
        initial = net_values[0]
        final = net_values[-1]
        result.total_return = final / initial - 1.0
        result.annualized_return = (1.0 + result.total_return) ** (TRADING_DAYS_PER_YEAR / actual_trading_days) - 1.0

        # 最大回撤
        max_dd, _ = compute_drawdown(net_values)
        result.max_drawdown = max_dd

        # Sharpe（基于日收益率，年化 252）
        daily_rets = daily_returns(net_values)
        result.sharpe_ratio = compute_sharpe(daily_rets)

        # Calmar
        result.calmar = (
            result.annualized_return / result.max_drawdown if result.max_drawdown > 0.001 else 0.0
        )

        return result
