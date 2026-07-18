#!/usr/bin/env python3
"""
少妇战法六步闭环引擎

状态机驱动的交易循环，严格遵循 Z 哥 SOP 六步流程：
  1. 择时 → 2. 选股 → 3. 等B1 → 4. 设止损 → 5. 卤煮止盈 → 6. 白线两日破位离场

核心趋势线：
  - 白线（Z哥白线）= EMA(EMA(C,10),10) — 短期趋势支撑，"牵牛绳"
  - 黄线（大哥线）= (MA14+MA28+MA57+MA114)/4 — 中期趋势
  - 白线在黄线上 = 主力牵牛，任何下跌都是洗盘
  - 白线死叉黄线 = 无条件清仓

用法：
    from modules.loop_engine import ShaofuLoopEngine, LoopConfig
    engine = ShaofuLoopEngine(LoopConfig(j_threshold=12))
    trades = engine.run_stock(klines)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .indicators import (
    DailyData,
    TradeSignal,
    calculate_bbi,
    calculate_kdj,
    calculate_zg_white,
    calculate_dg_yellow,
    detect_b1_today,
    detect_double_line_cross,
    detect_trade_signal,
)
from .constants import BACKTEST_DEFAULT_TRAILING_STOP_PCT


# ============================================================
# 状态定义
# ============================================================


class LoopState(Enum):
    """六步闭环状态"""

    TIMING = "择时"  # Step 1: 看大环境
    SELECTING = "选股"  # Step 2: 筛选标的
    WAITING_B1 = "等B1"  # Step 3: 等待 B1 信号
    HOLDING = "持仓"  # Step 4-5: 止损/止盈管理
    EXITED = "离场"  # Step 6: 平仓完成


# ============================================================
# 数据结构
# ============================================================


@dataclass
class LoopConfig:
    """策略参数配置"""

    j_threshold: float = 12  # B1 J 值阈值（SOP: J<=12，最好负值）
    stop_loss_pct: float = -0.03  # 止损比例（现已实际生效，原硬编码 0.97 = -3%）
    stop_loss_method: str = "entry_low"  # "entry_low" | "n_structure_low" | "j_negative_low" | "atr_based"
    # v3.10.1 新增：ATR 动态止损
    atr_stop_window: int = 14  # ATR 计算窗口
    atr_stop_multiplier: float = 2.0  # ATR 乘数（止损距离 = ATR × 倍数）
    # v3.10.1 新增：移动止损（trailing stop）
    trailing_stop_enabled: bool = False  # 是否启用移动止损
    trailing_stop_pct: float = BACKTEST_DEFAULT_TRAILING_STOP_PCT  # 移动止损比例（高点回落超过此比例则止损）
    bbi_break_days: int = 2  # BBI 连续跌破天数触发离场
    bbi_break_threshold: float = 0.01  # 收盘价低于 BBI 超过此比例才算"跌破"（1%）
    min_holding_days: int = 3  # 最少持仓天数（避免入场后次日就被震出）
    lu_half: bool = True  # 卤煮减半（站上BBI+连续两根阳线→减半）
    position_pct: float = 0.3  # 单笔仓位比例
    vol_shrink_threshold: float = 0.8  # 缩量判定阈值（当日量 / 前日量 < 此值视为缩量）

    @classmethod
    def from_registry(cls, strategy_name: str = "shaofu_v1") -> LoopConfig | None:
        """
        从 param_registry 读取 LoopConfig（可选扩展点）。

        注意：本方法需要循环依赖避免，所以延迟 import：
        - modules.verify.registry_writer.load_config_from_registry
        - 若 modules.verify 不可用（如 zettaranc_skill 未安装 verify 子包），
          返回 None
        """
        try:
            from modules.verify.registry_writer import load_config_from_registry

            return load_config_from_registry(strategy_name)
        except ImportError:
            return None


@dataclass
class LoopTrade:
    """一笔完整的少妇战法交易记录

    记录从入场到出价的完整交易生命周期，包含：
    - 入场信息：日期、价格、原因（B1 信号详情）
    - 出场信息：日期、价格、原因（卤煮止盈/白线跌破/止损/白线死叉黄线）
    - 过程指标：盈亏比、持仓天数、最大浮盈/浮亏
    - 仓位管理：卤煮减仓记录、实际仓位比例
    - 市场环境：入场时的市场状态（BULL/BEAR/SIDEWAYS）
    """

    ts_code: str
    entry_date: str
    entry_price: float
    entry_reason: str  # B1 信号详情
    stop_loss_price: float  # Step 4: 收盘价止损位
    # v3.10.1：移动止损追踪入场后最高点（用于动态抬高止损价）
    highest_after_entry: float = 0.0
    exit_date: str = ""
    exit_price: float = 0
    exit_reason: str = ""  # "卤煮止盈" | "白线跌破" | "止损" | "白线死叉黄线"
    pnl_pct: float = 0
    holding_days: int = 0
    max_favorable: float = 0  # 最大浮盈%
    max_adverse: float = 0  # 最大浮亏%
    partial_exits: list[dict[str, Any]] = field(default_factory=list)  # 卤煮减仓记录
    position_pct: float = 0.0  # 该笔交易的实际仓位比例（占总资金）
    market_regime: str = ""  # 入场时的市场状态（BULL/BEAR/SIDEWAYS）
    strategy_source: str = ""  # v3.10.0：触发该交易的策略名（B1/B2/SB1/长安 等）


# ============================================================
# 辅助函数
# ============================================================


def detect_bbi_break_streak(
    closes: list[float], bbi_values: list[float], days: int = 2, threshold: float = 0.0
) -> bool:
    """
    检测收盘价是否连续 N 天跌破 BBI

    Args:
        closes: 收盘价序列
        bbi_values: BBI 值序列（与 closes 等长）
        days: 连续跌破天数要求
        threshold: 跌破阈值比例（0.01 = 收盘价低于 BBI 1% 才算跌破）

    Returns:
        是否连续 N 天跌破
    """
    if len(closes) < days or len(bbi_values) < days:
        return False

    for i in range(1, days + 1):
        if closes[-i] >= bbi_values[-i] * (1 - threshold):
            return False

    return True


def _calc_stop_loss_price(
    klines: list[DailyData],
    day_idx: int,
    method: str = "entry_low",
    stop_loss_pct: float = -0.07,
    atr_multiplier: float = 2.0,
    atr_window: int = 14,
) -> float:
    """
    根据不同方法计算止损价

    四种方法（SOP 第 4 步）：
    - entry_low: 入场 K 线最低价 + 止损比例缓冲
    - n_structure_low: N 型结构前低（入场前最近一个回调低点）
    - j_negative_low: J 值转负那天 K 线的最低价
    - atr_based: v3.10.1 ATR 动态止损 = 入场价 - ATR × 倍数
      （高波动自动放宽，低波动自动收紧）

    Args:
        klines: K 线数据
        day_idx: 入场日索引
        method: 止损方法（"entry_low"/"n_structure_low"/"j_negative_low"/"atr_based"）
        stop_loss_pct: 止损比例（负值，如 -0.07 表示 -7%），仅 entry_low 模式使用
        atr_multiplier: ATR 倍数（止损距离 = ATR × 倍数），仅 atr_based 模式使用
        atr_window: ATR 计算窗口，仅 atr_based 模式使用

    Returns:
        止损价
    """
    entry_kline = klines[day_idx]

    if method == "entry_low":
        # 入场日最低价 × (1 + 止损比例)
        # stop_loss_pct=-0.07 表示入场低下方 7% 为止损位
        return entry_kline.low * (1 + stop_loss_pct)

    if method == "n_structure_low":
        # 回溯找入场前最近的回调低点（N 型结构的前低）
        lookback = min(day_idx, 30)
        window = klines[day_idx - lookback : day_idx]
        if not window:
            return entry_kline.low
        return min(k.low for k in window)

    if method == "j_negative_low":
        # 找入场前 J 值首次转负的那根 K 线
        for i in range(day_idx - 1, max(day_idx - 30, -1), -1):
            sub_klines = klines[: i + 1]
            if len(sub_klines) < 9:
                continue
            _, _, j = calculate_kdj(sub_klines)
            if j <= 0:
                return klines[i].low
        # 未找到则退化为 entry_low
        return entry_kline.low

    if method == "atr_based":
        # v3.10.1：ATR 动态止损
        # 止损价 = 入场参考价 - ATR × 倍数
        # 入场参考价用 entry_kline.close，更贴近实际成交
        from .core.atr import calculate_atr

        # 用入场前 window+1 根 K 线计算 ATR（不偷看入场日之后数据）
        atr_window_klines = klines[max(0, day_idx - atr_window - 1) : day_idx + 1]
        atr_value = calculate_atr(atr_window_klines, window=min(atr_window, len(atr_window_klines) - 1))
        if atr_value <= 0:
            # 数据不足 fallback 到 entry_low
            return entry_kline.low * (1 + stop_loss_pct)
        entry_ref = entry_kline.close or entry_kline.open
        return entry_ref - atr_value * atr_multiplier

    # 默认
    return entry_kline.low


def calc_trailing_stop_price(
    highest_after_entry: float,
    trailing_stop_pct: float,
) -> float:
    """
    计算移动止损价（v3.10.1）

    移动止损：当股价上涨时，止损价同步上移（保护浮盈）；
    当股价下跌时，止损价固定不变（不下移）。

    Args:
        highest_after_entry: 入场后最高价
        trailing_stop_pct: 移动止损比例（负值，如 -0.05 表示从高点回落 5%）

    Returns:
        移动止损价
    """
    if highest_after_entry <= 0:
        return 0.0
    return highest_after_entry * (1 + trailing_stop_pct)


# ============================================================
# 核心引擎
# ============================================================


class ShaofuLoopEngine:
    """
    少妇战法六步闭环引擎

    状态机驱动，逐日处理 K 线数据，自动完成：
    - B1 入场检测（含 J 值阈值、N 型上移、缩量回调、MACD 否决）
    - 收盘价止损
    - 卤煮减半止盈
    - 白线两日破位离场
    - 白线死叉黄线紧急离场

    设计原则：
    - Python 层只做数据判断，不生成话术
    - 使用收盘价，不看盘中价（SOP 明确要求）
    - 支持回测场景（顺序遍历历史数据）
    """

    def __init__(self, config: LoopConfig | None = None):
        """
        初始化引擎

        Args:
            config: 策略参数配置，None 则使用默认值
        """
        self.config = config or LoopConfig()

    # ----------------------------------------------------------
    # 公开检查方法（供外部测试和调用）
    # ----------------------------------------------------------

    def check_entry(self, klines: list[DailyData]) -> dict[str, Any] | None:
        """
        Step 3: 检查 B1 入场条件（公开接口）

        综合判断：
        1. KDJ J 值 <= 阈值（默认 12，最好负值）
        2. N 型上移结构：近期有 higher lows
        3. 缩量回调：当日成交量低于前日
        4. MACD 未一票否决

        Args:
            klines: 完整 K 线数据（按日期升序）

        Returns:
            信号字典或 None
        """
        if len(klines) < 30:
            return None

        # --- B1 检测 ---
        b1 = detect_b1_today(klines)
        if not b1.get("is_b1"):
            return None

        j_val = b1.get("b1_j_value", 50)

        # J 值阈值过滤（可配置，默认 SOP 标准 12）
        if j_val > self.config.j_threshold:
            return None

        # --- 牛绳检查：白线在黄线上才入场 ---
        white = calculate_zg_white(klines)
        yellow = calculate_dg_yellow(klines)
        if white < yellow:
            return None

        # --- 缩量回调 ---
        today = klines[-1]
        yesterday = klines[-2]
        vol_shrink = today.vol < yesterday.vol * self.config.vol_shrink_threshold

        # --- N 型上移结构 ---
        n_structure_ok = self._check_n_structure(klines, len(klines) - 1)

        # 综合判定：B1 通过 + 牛绳牵牛 + 缩量 + N型结构 OK
        if b1["is_b1"] and vol_shrink and n_structure_ok:
            reason_parts = [
                f"J={j_val:.1f}",
                f"振幅={b1.get('b1_amplitude', 0):.1f}%",
                f"评分={b1.get('b1_score', 0)}",
            ]
            if n_structure_ok:
                reason_parts.append("N型上移")
            if vol_shrink:
                reason_parts.append("缩量回调")

            return {
                "is_b1": True,
                "j_value": j_val,
                "entry_price": today.close,
                "signal": True,
                "reason": "B1: " + ", ".join(reason_parts),
            }

        return None

    def check_stop_loss(self, current: DailyData, entry_low: float) -> bool:
        """
        Step 4: 检查收盘价止损（公开接口）

        SOP: "看收盘价，不看盘中"
        触发条件：当日收盘价 < 止损位

        Args:
            current: 当日 K 线数据
            entry_low: 止损价位

        Returns:
            是否触发止损
        """
        return current.close < entry_low

    def check_lu_zhu(self, recent_klines: list[DailyData], white_line: float) -> bool:
        """
        Step 5: 检查卤煮止盈条件（公开接口）

        SOP: 站上白线 + 连续两根中/大阳线 → 减半
        阳线定义：close > open
        额外条件：成交量不能明显萎缩

        Args:
            recent_klines: 最近的 K 线列表（至少 2 根）
            white_line: 当前白线值

        Returns:
            是否触发卤煮止盈
        """
        if len(recent_klines) < 2:
            return False

        today = recent_klines[-1]
        yesterday = recent_klines[-2]

        # 条件 1: 当日站上白线
        if today.close <= white_line:
            return False

        # 条件 2: 连续两根阳线（close >= open，含十字星）
        two_consecutive_yang = today.close >= today.open and yesterday.close >= yesterday.open
        if not two_consecutive_yang:
            return False

        # 条件 3: 量能不萎缩（当日量不低于前日的 80%）
        if yesterday.vol > 0 and today.vol < yesterday.vol * 0.8:
            return False

        return True

    def check_white_line_exit(self, closes: list[float], white_values: list[float]) -> bool:
        """
        Step 6: 检查白线两日破位（公开接口）

        SOP: 收盘价连续两天跌破白线 → 清仓
        白线 = EMA(EMA(C,10),10)，是 Z 哥的"牵牛绳"

        Args:
            closes: 最近 N 天的收盘价列表
            white_values: 最近 N 天的白线值列表

        Returns:
            是否触发白线两日破位离场
        """
        return detect_bbi_break_streak(
            closes, white_values, self.config.bbi_break_days, self.config.bbi_break_threshold
        )

    # ----------------------------------------------------------
    # 内部检查方法（供 run_stock 循环使用）
    # ----------------------------------------------------------

    def _check_entry_internal(self, klines: list[DailyData], day_idx: int) -> dict[str, Any] | None:
        """
        内部入口检查（供 run_stock 逐日调用）

        Args:
            klines: K 线数据
            day_idx: 当前日索引

        Returns:
            信号字典（含 reason 字段）或 None
        """
        sub = klines[: day_idx + 1]
        return self.check_entry(sub)

    def _check_stop_loss_internal(
        self,
        klines: list[DailyData],
        day_idx: int,
        trade: LoopTrade,
    ) -> bool:
        """
        内部止损检查（v3.10.1 支持 trailing stop）

        Args:
            klines: K 线数据
            day_idx: 当前日索引
            trade: 当前交易

        Returns:
            是否触发止损（原始止损价 或 移动止损 任一触发）
        """
        current = klines[day_idx]
        # 原始止损检查
        if self.check_stop_loss(current, trade.stop_loss_price):
            return True
        # v3.10.1：移动止损检查（仅在启用时）
        if self.config.trailing_stop_enabled and trade.highest_after_entry > 0:
            trailing_price = calc_trailing_stop_price(trade.highest_after_entry, self.config.trailing_stop_pct)
            if trailing_price > 0 and current.close < trailing_price:
                return True
        return False

    def _check_lu_zhu_internal(self, klines: list[DailyData], day_idx: int) -> bool:
        """
        内部卤煮检查

        Args:
            klines: K 线数据
            day_idx: 当前日索引

        Returns:
            是否触发卤煮止盈
        """
        if day_idx < 2:
            return False

        sub = klines[: day_idx + 1]
        if len(sub) < 24:
            return False

        white = calculate_zg_white(sub)
        return self.check_lu_zhu(sub[-3:], white)

    def _check_white_line_exit_internal(self, klines: list[DailyData], day_idx: int) -> bool:
        """
        内部白线破位检查

        Args:
            klines: K 线数据
            day_idx: 当前日索引

        Returns:
            是否触发白线两日破位离场
        """
        days_needed = self.config.bbi_break_days
        if day_idx < days_needed:
            return False

        # 逐天计算白线并检查
        closes = []
        white_values = []
        for i in range(day_idx - days_needed + 1, day_idx + 1):
            sub = klines[: i + 1]
            if len(sub) < 10:
                return False
            closes.append(sub[-1].close)
            white_values.append(calculate_zg_white(sub))

        return self.check_white_line_exit(closes, white_values)

    def _check_dead_cross_exit(self, klines: list[DailyData], day_idx: int) -> bool:
        """
        检查白线死叉黄线（紧急离场）

        SOP: 白线死叉黄线 = 无条件清仓
        "白线在黄线上 = 主力牵着牛绳（洗盘），白线在黄线下 = 牛绳断了（反弹）"

        Args:
            klines: K 线数据
            day_idx: 当前日索引

        Returns:
            是否触发白线死叉黄线离场
        """
        sub = klines[: day_idx + 1]
        if len(sub) < 20:
            return False

        is_gold, is_dead = detect_double_line_cross(sub)
        return is_dead

    def _check_n_structure(self, klines: list[DailyData], day_idx: int) -> bool:
        """
        检查 N 型上移结构

        在近 20 天内寻找两个低点，后一个低点高于前一个（higher lows）。
        这是 B1 信号的辅助确认条件。

        Args:
            klines: K 线数据
            day_idx: 当前日索引

        Returns:
            是否形成 N 型上移
        """
        lookback = min(day_idx, 20)
        if lookback < 10:
            return True  # 数据不足时放行

        window = klines[day_idx - lookback : day_idx + 1]
        if len(window) < 10:
            return True

        # 将窗口分为前后两半，比较各自的最低价
        mid = len(window) // 2
        first_half = window[:mid]
        second_half = window[mid:]

        if not first_half or not second_half:
            return True

        first_low = min(k.low for k in first_half)
        second_low = min(k.low for k in second_half)

        # 后半段低点 >= 前半段低点（允许 2% 容差）
        return second_low >= first_low * 0.98

    # ----------------------------------------------------------
    # 离场检查（共享逻辑，消除 run_stock / process_day 重复）
    # ----------------------------------------------------------

    def _close_trade(self, trade: LoopTrade, date: str, price: float, reason: str, pnl_pct: float) -> LoopTrade:
        """平仓并返回已完成的交易"""
        trade.exit_date = date
        trade.exit_price = price
        trade.exit_reason = reason
        trade.pnl_pct = pnl_pct
        return trade

    def _apply_exit_checks(
        self, klines: list[DailyData], day_idx: int, trade: LoopTrade
    ) -> tuple[LoopTrade | None, LoopTrade | None]:
        """六层离场检查，返回 (更新后的持仓, 已完成的交易)

        被 run_stock 和 process_day 共享调用。
        """
        current_price = klines[day_idx].close
        pnl_pct = (current_price - trade.entry_price) / trade.entry_price * 100
        trade.max_favorable = max(trade.max_favorable, pnl_pct)
        trade.max_adverse = min(trade.max_adverse, pnl_pct)
        # v3.10.1：追踪入场后最高价（驱动移动止损上移）
        current_high = klines[day_idx].high
        trade.highest_after_entry = max(trade.highest_after_entry, current_high)
        trade.holding_days += 1

        # 白线死叉黄线（无条件清仓）
        if self._check_dead_cross_exit(klines, day_idx):
            return None, self._close_trade(trade, klines[day_idx].trade_date, current_price, "白线死叉黄线", pnl_pct)

        # 最少持仓天数保护（止损在保护期后才生效，避免入场次日被震出）
        if trade.holding_days < self.config.min_holding_days:
            return trade, None

        # Step 4: 收盘价止损
        if self._check_stop_loss_internal(klines, day_idx, trade):
            return None, self._close_trade(trade, klines[day_idx].trade_date, current_price, "止损", pnl_pct)

        # Step 6: 白线两日破位
        if self._check_white_line_exit_internal(klines, day_idx):
            return None, self._close_trade(trade, klines[day_idx].trade_date, current_price, "白线跌破", pnl_pct)

        # Step 5: 卤煮止盈
        if self._check_lu_zhu_internal(klines, day_idx):
            if self.config.lu_half:
                trade.partial_exits.append(
                    {
                        "date": klines[day_idx].trade_date,
                        "price": current_price,
                        "pnl_pct": pnl_pct,
                        "type": "卤煮减半",
                    }
                )
                trade.entry_reason += " [已卤煮减半]"
                return trade, None
            else:
                return None, self._close_trade(trade, klines[day_idx].trade_date, current_price, "卤煮止盈", pnl_pct)

        return trade, None

    # ----------------------------------------------------------
    # 主循环
    # ----------------------------------------------------------

    def run_stock(self, klines: list[DailyData], ts_code: str = "") -> list[LoopTrade]:
        """对一只股票运行完整的六步闭环

        从第 30 根 K 线开始，自动完成入场→持仓→离场的循环。
        """
        if not klines or len(klines) < 30:
            return []

        if not ts_code:
            ts_code = klines[0].ts_code if klines else ""

        completed_trades: list[LoopTrade] = []
        current_trade: LoopTrade | None = None

        for day_idx in range(30, len(klines)):
            if current_trade is None:
                signal = self._check_entry_internal(klines, day_idx)
                if signal is not None:
                    entry_price = klines[day_idx].close
                    stop_loss = _calc_stop_loss_price(
                        klines, day_idx, self.config.stop_loss_method, self.config.stop_loss_pct
                    )
                    current_trade = LoopTrade(
                        ts_code=ts_code,
                        entry_date=klines[day_idx].trade_date,
                        entry_price=entry_price,
                        entry_reason=signal.get("reason", "B1信号"),
                        stop_loss_price=stop_loss,
                        position_pct=self.config.position_pct,
                    )
            else:
                current_trade, completed = self._apply_exit_checks(klines, day_idx, current_trade)
                if completed:
                    completed_trades.append(completed)
                    current_trade = None
                    continue

        # 数据末尾：强制平仓
        if current_trade is not None and klines:
            last = klines[-1]
            pnl_pct = (last.close - current_trade.entry_price) / current_trade.entry_price * 100
            completed_trades.append(self._close_trade(current_trade, last.trade_date, last.close, "数据末尾", pnl_pct))

        return completed_trades

    def process_day(
        self,
        ts_code: str,
        klines: list[DailyData],
        day_idx: int,
        current_trade: LoopTrade | None = None,
    ) -> tuple[LoopTrade | None, LoopTrade | None]:
        """处理单日数据（供外部精细控制调用）

        Returns:
            (updated_trade, completed_trade)
        """
        if day_idx < 30 or day_idx >= len(klines):
            return current_trade, None

        if current_trade is None:
            signal = self._check_entry_internal(klines, day_idx)
            if signal is not None:
                entry_price = klines[day_idx].close
                stop_loss = _calc_stop_loss_price(klines, day_idx, self.config.stop_loss_method)
                new_trade = LoopTrade(
                    ts_code=ts_code,
                    entry_date=klines[day_idx].trade_date,
                    entry_price=entry_price,
                    entry_reason=signal.get("reason", "B1信号"),
                    stop_loss_price=stop_loss,
                    position_pct=self.config.position_pct,
                )
                return new_trade, None
            return None, None

        return self._apply_exit_checks(klines, day_idx, current_trade)


# ============================================================
# CLI 入口
# ============================================================

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="少妇战法六步闭环引擎")
    parser.add_argument("ts_code", help="股票代码，如 600487.SH")
    parser.add_argument("--days", type=int, default=240, help="回测天数（默认 240）")
    parser.add_argument(
        "--j-threshold",
        type=float,
        default=12,
        help="B1 J 值阈值（默认 12）",
    )
    parser.add_argument(
        "--stop-loss-method",
        choices=["entry_low", "n_structure_low", "j_negative_low"],
        default="entry_low",
        help="止损方法",
    )
    parser.add_argument(
        "--bbi-days",
        type=int,
        default=2,
        help="BBI 连续跌破天数（默认 2）",
    )

    args = parser.parse_args()

    # 获取 K 线数据
    try:
        from modules.indicators import get_kline_data

        raw_klines = get_kline_data(args.ts_code, args.days)
    except ImportError:
        print("无法导入 get_kline_data，请确保 modules.indicators 可用", file=sys.stderr)
        sys.exit(1)

    if not raw_klines:
        print(f"未获取到 {args.ts_code} 的 K 线数据", file=sys.stderr)
        sys.exit(1)

    # 转换为 DailyData
    klines: list[DailyData] = []
    for k in raw_klines:
        klines.append(
            DailyData(
                ts_code=args.ts_code,
                trade_date=k.get("trade_date", ""),
                open=float(k.get("open", 0)),
                high=float(k.get("high", 0)),
                low=float(k.get("low", 0)),
                close=float(k.get("close", 0)),
                vol=float(k.get("vol", 0)),
                amount=float(k.get("amount", 0)),
                pct_chg=float(k.get("pct_chg", 0)),
            )
        )

    # 构建配置并运行
    config = LoopConfig(
        j_threshold=args.j_threshold,
        stop_loss_method=args.stop_loss_method,
        bbi_break_days=args.bbi_days,
    )
    engine = ShaofuLoopEngine(config)
    trades = engine.run_stock(klines, args.ts_code)

    # 输出结果
    print(f"{'=' * 60}")
    print(f"少妇战法闭环回测: {args.ts_code}")
    print(f"{'=' * 60}")
    print(f"K 线天数:   {len(klines)}")
    print(f"交易次数:   {len(trades)}")

    if trades:
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        losses = sum(1 for t in trades if t.pnl_pct < 0)
        win_rate = wins / len(trades) * 100 if trades else 0
        avg_pnl = sum(t.pnl_pct for t in trades) / len(trades)
        avg_days = sum(t.holding_days for t in trades) / len(trades)

        print(f"盈利次数:   {wins}")
        print(f"亏损次数:   {losses}")
        print(f"胜率:       {win_rate:.1f}%")
        print(f"平均收益:   {avg_pnl:+.2f}%")
        print(f"平均持仓:   {avg_days:.1f} 天")
        print(f"{'=' * 60}")

        print("\n交易明细:")
        for i, t in enumerate(trades, 1):
            status = "+" if t.pnl_pct > 0 else "-" if t.pnl_pct < 0 else "="
            partial = " [减半]" if t.partial_exits else ""
            print(
                f"  {i}. {t.entry_date} → {t.exit_date}  "
                f"{t.pnl_pct:+.2f}%{partial}  "
                f"({t.exit_reason})  "
                f"持仓{t.holding_days}天  "
                f"最大浮盈{t.max_favorable:+.1f}%  "
                f"最大浮亏{t.max_adverse:+.1f}%"
            )
    else:
        print("未产生交易信号")

    print()
