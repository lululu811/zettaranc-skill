#!/usr/bin/env python3
"""
自我改进系统 - 数据同步模块

同步跟踪股票的K线、指标、信号数据
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any
import pandas as pd

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.database import get_connection
from modules.improvement_logger import ImprovementLogger
from modules.tushare_client import TushareClient
from modules.indicators.data_layer import analyze_stock


class TrackingSyncer:
    """跟踪数据同步器"""

    def __init__(self):
        """初始化同步器"""
        self.client = TushareClient()
        self.logger = ImprovementLogger()

    def sync_daily(self, ts_code: str, days: int = 365) -> dict[str, Any]:
        """
        同步单只股票的每日数据

        Args:
            ts_code: 股票代码
            days: 同步天数

        Returns:
            同步结果
        """
        try:
            # 检查是否在跟踪池中
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id FROM tracking_pool_self
                    WHERE ts_code = ? AND status = 'active'
                """,
                    (ts_code,),
                )

                if not cursor.fetchone():
                    return {"success": False, "message": f"{ts_code} 不在跟踪池中"}

            # 从 daily_kline 表中读取K线数据
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT trade_date, open, high, low, close, vol, pct_chg, amount
                    FROM daily_kline
                    WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ?
                    ORDER BY trade_date
                """,
                    (ts_code, start_date, end_date),
                )

                kline_records = cursor.fetchall()

                if not kline_records:
                    return {"success": False, "message": f"无法获取 {ts_code} 的K线数据"}

                # 转换为 DataFrame 格式
                import pandas as pd

                kline_data = pd.DataFrame(
                    kline_records, columns=["trade_date", "open", "high", "low", "close", "vol", "pct_chg", "amount"]
                )

            # 计算指标
            indicator_result = analyze_stock(ts_code, days=days)

            if indicator_result is None:
                return {"success": False, "message": f"无法计算 {ts_code} 的指标"}

            # 保存到跟踪记录表
            saved_count = 0
            with get_connection() as conn:
                cursor = conn.cursor()

                # 转换为列表，便于获取前一日数据
                kline_records = kline_data.to_dict("records")

                for i, row in enumerate(kline_records):
                    trade_date = row["trade_date"]

                    # 获取该日期的指标数据
                    indicator_data = self._get_indicators_for_date(ts_code, trade_date)

                    # 检测信号
                    kline_dict = {
                        "ts_code": ts_code,
                        "trade_date": trade_date,
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "pct_chg": row.get("pct_chg"),
                        "vol": row.get("vol"),
                    }

                    # 获取前一日 K 线数据
                    prev_kline_dict = None
                    if i > 0:
                        prev_row = kline_records[i - 1]
                        prev_kline_dict = {
                            "open": prev_row.get("open"),
                            "high": prev_row.get("high"),
                            "low": prev_row.get("low"),
                            "close": prev_row.get("close"),
                            "pct_chg": prev_row.get("pct_chg"),
                            "vol": prev_row.get("vol"),
                        }

                    signal_info = self._detect_signal(indicator_data, kline_dict, prev_kline_dict)

                    # 检测形态
                    pattern_info = self._detect_patterns(indicator_data)

                    # 检测主力阶段
                    stage_info = self._detect_stage(indicator_data)

                    # 插入或更新记录
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO tracking_records_self (
                            ts_code, trade_date, open, high, low, close, vol, pct_chg, amount,
                            j_value, k_value, d_value, bbi, macd_dif, macd_dea, macd_hist,
                            rsi_6, wr_6, boll_upper, boll_mid, boll_lower, vol_ratio,
                            is_brick_red, is_brick_green, brick_count, is_n_structure, is_double_gun,
                            signal_type, signal_score, signal_reason, stage, stage_confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            ts_code,
                            trade_date,
                            row.get("open"),
                            row.get("high"),
                            row.get("low"),
                            row.get("close"),
                            row.get("vol"),
                            row.get("pct_chg"),
                            row.get("amount"),
                            indicator_data.get("j_value"),
                            indicator_data.get("k_value"),
                            indicator_data.get("d_value"),
                            indicator_data.get("bbi"),
                            indicator_data.get("macd_dif"),
                            indicator_data.get("macd_dea"),
                            indicator_data.get("macd_hist"),
                            indicator_data.get("rsi_6"),
                            indicator_data.get("wr_6"),
                            indicator_data.get("boll_upper"),
                            indicator_data.get("boll_mid"),
                            indicator_data.get("boll_lower"),
                            indicator_data.get("vol_ratio"),
                            pattern_info.get("is_brick_red", 0),
                            pattern_info.get("is_brick_green", 0),
                            pattern_info.get("brick_count", 0),
                            pattern_info.get("is_n_structure", 0),
                            pattern_info.get("is_double_gun", 0),
                            signal_info.get("signal_type"),
                            signal_info.get("signal_score"),
                            signal_info.get("signal_reason"),
                            stage_info.get("stage"),
                            stage_info.get("stage_confidence"),
                        ),
                    )
                    saved_count += 1

                conn.commit()

            return {"success": True, "message": f"已同步 {ts_code} 的 {saved_count} 条记录", "saved_count": saved_count}

        except Exception as e:
            return {"success": False, "message": f"同步失败: {str(e)}"}

    def sync_all_active(self, days: int = 365) -> dict[str, Any]:
        """
        同步所有活跃跟踪股票

        Args:
            days: 同步天数

        Returns:
            同步结果
        """
        try:
            # 获取所有活跃股票
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ts_code FROM tracking_pool_self
                    WHERE status = 'active'
                """)
                active_stocks = [row["ts_code"] for row in cursor.fetchall()]

            if not active_stocks:
                return {"success": True, "message": "跟踪池为空，无需同步", "results": {}}

            results = {}
            success_count = 0
            fail_count = 0

            for ts_code in active_stocks:
                result = self.sync_daily(ts_code, days=days)
                results[ts_code] = result

                if result["success"]:
                    success_count += 1
                else:
                    fail_count += 1

            return {
                "success": True,
                "message": f"同步完成：成功 {success_count} 只，失败 {fail_count} 只",
                "results": results,
                "success_count": success_count,
                "fail_count": fail_count,
            }

        except Exception as e:
            return {"success": False, "message": f"批量同步失败: {str(e)}"}

    def _get_indicators_for_date(self, ts_code: str, trade_date: str) -> dict[str, Any]:
        """
        获取指定日期的指标数据（从 indicator_cache 表中读取）

        Args:
            ts_code: 股票代码
            trade_date: 交易日期

        Returns:
            指标数据字典
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT j, k, d, bbi, dif, dea, macd_hist, rsi6, wr5,
                           boll_upper, boll_mid, boll_lower, vol_ratio
                    FROM indicator_cache
                    WHERE ts_code = ? AND trade_date = ?
                """,
                    (ts_code, trade_date),
                )

                row = cursor.fetchone()
                if row:
                    return {
                        "j_value": row[0],
                        "k_value": row[1],
                        "d_value": row[2],
                        "bbi": row[3],
                        "macd_dif": row[4],
                        "macd_dea": row[5],
                        "macd_hist": row[6],
                        "rsi_6": row[7],
                        "wr_6": row[8],
                        "boll_upper": row[9],
                        "boll_mid": row[10],
                        "boll_lower": row[11],
                        "vol_ratio": row[12],
                    }
                else:
                    return {}
        except Exception as e:
            print(f"获取指标数据失败: {e}")
            return {}

    def _detect_signal(
        self, indicator_data: dict[str, Any], kline_data: dict[str, Any] = None, prev_kline_data: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        检测交易信号（根据 Z 哥的策略）

        Args:
            indicator_data: 指标数据
            kline_data: K线数据（可选，用于计算换手率等）
            prev_kline_data: 前一日K线数据（可选，用于 B3 和长安战法）

        Returns:
            信号信息
        """
        try:
            signal_type = "NONE"
            signal_score = 0
            signal_reason = ""

            j_value = indicator_data.get("j_value")
            bbi = indicator_data.get("bbi")
            macd_dif = indicator_data.get("macd_dif")
            macd_dea = indicator_data.get("macd_dea")
            k_value = indicator_data.get("k_value")
            d_value = indicator_data.get("d_value")
            vol_ratio = indicator_data.get("vol_ratio")

            # 获取 K 线数据
            close = kline_data.get("close") if kline_data else None
            open_price = kline_data.get("open") if kline_data else None
            high = kline_data.get("high") if kline_data else None
            low = kline_data.get("low") if kline_data else None
            pct_chg = kline_data.get("pct_chg") if kline_data else None
            vol = kline_data.get("vol") if kline_data else None

            # 获取前一日 K 线数据
            prev_close = prev_kline_data.get("close") if prev_kline_data else None
            prev_vol = prev_kline_data.get("vol") if prev_kline_data else None
            prev_pct_chg = prev_kline_data.get("pct_chg") if prev_kline_data else None

            # ========== B1 买入信号 ==========
            # 条件：J值 ≤ -10，涨幅在 -2% ~ 1.8%，振幅 < 7%
            if j_value is not None and j_value <= -10:
                # 检查涨幅条件
                pct_ok = True
                if pct_chg is not None:
                    pct_ok = -2 <= pct_chg <= 1.8

                # 检查振幅条件
                amplitude_ok = True
                if high is not None and low is not None and close is not None and close > 0:
                    amplitude = (high - low) / close * 100
                    amplitude_ok = amplitude < 7

                if pct_ok and amplitude_ok:
                    signal_type = "B1"
                    signal_score = 80
                    signal_reason = f"B1买点：J值={j_value:.1f}<=-10"
                    if pct_chg is not None:
                        signal_reason += f"，涨幅={pct_chg:.1f}%"

            # ========== B2 确认信号 ==========
            # 条件：B1后3日内，涨幅≥4%，KDJ钩值<55，放量
            elif j_value is not None and 0 < j_value < 55:
                # 检查是否在 BBI 之上
                if close is not None and bbi is not None and close > bbi:
                    # 检查量比（放量）
                    vol_ok = vol_ratio is not None and vol_ratio > 1.2

                    # 检查涨幅
                    pct_ok = pct_chg is not None and pct_chg >= 4

                    if vol_ok and pct_ok:
                        signal_type = "B2"
                        signal_score = 70
                        signal_reason = f"B2确认：J值={j_value:.1f}，涨幅={pct_chg:.1f}%，量比={vol_ratio:.1f}"

            # ========== B3 加速确认信号 ==========
            # 条件：B2后出现十字星/小阴线，平开一致
            elif j_value is not None and 0 < j_value < 55:
                if prev_pct_chg is not None and prev_pct_chg >= 4:  # 前一日是 B2
                    # 检查是否是十字星或小阴线
                    if pct_chg is not None and -2 <= pct_chg <= 2:
                        # 检查是否平开
                        if open_price is not None and prev_close is not None:
                            open_pct = abs(open_price - prev_close) / prev_close * 100
                            if open_pct < 1:  # 平开（开盘价与前收盘价相差<1%）
                                signal_type = "B3"
                                signal_score = 75
                                signal_reason = f"B3加速确认：J值={j_value:.1f}，涨幅={pct_chg:.1f}%，平开一致"

            # ========== 长安战法信号 ==========
            # 条件：第一天B1(J<-13)，第二天放量长阳，第三天分歧转一致缩半量
            elif j_value is not None and j_value > 0 and j_value < 55:
                if prev_kline_data is not None:
                    # 检查前前一日是否是 B1
                    # 这里简化处理，实际需要检查前前一日的 J 值
                    # 暂时跳过这个检查

                    # 检查前一日是否是放量长阳
                    if prev_pct_chg is not None and prev_pct_chg >= 4:
                        # 检查今日是否是分歧转一致缩半量
                        if pct_chg is not None and -2 <= pct_chg <= 2:
                            # 检查是否缩量
                            if vol is not None and prev_vol is not None:
                                if vol < prev_vol * 0.6:  # 缩半量
                                    signal_type = "CHANGAN"
                                    signal_score = 85
                                    signal_reason = f"长安战法：前日涨幅={prev_pct_chg:.1f}%，今日涨幅={pct_chg:.1f}%，缩量={vol / prev_vol * 100:.0f}%"

            # ========== MACD 金叉信号 ==========
            elif macd_dif is not None and macd_dea is not None:
                if macd_dif > macd_dea and macd_dif > 0:
                    signal_type = "WATCH"
                    signal_score = 60
                    signal_reason = "MACD金叉观察"

            # ========== 量比战法 ==========
            elif vol_ratio is not None and vol_ratio > 20:
                if pct_chg is not None and pct_chg > 0:
                    signal_type = "BUY"
                    signal_score = 75
                    signal_reason = f"量比攻击日：量比={vol_ratio:.1f}，涨幅={pct_chg:.1f}%"

            # 记录信号检测日志
            if signal_type != "NONE":
                self.logger.log_signal_detection(
                    ts_code=kline_data.get("ts_code", "") if kline_data else "",
                    trade_date=kline_data.get("trade_date", "") if kline_data else "",
                    signal_type=signal_type,
                    signal_score=signal_score,
                    signal_reason=signal_reason,
                    indicator_data=indicator_data,
                )

            return {"signal_type": signal_type, "signal_score": signal_score, "signal_reason": signal_reason}
        except Exception as e:
            print(f"检测信号失败: {e}")
            return {"signal_type": "NONE", "signal_score": 0, "signal_reason": ""}

    def _detect_patterns(self, indicator_data: dict[str, Any]) -> dict[str, Any]:
        """
        检测形态

        Args:
            indicator_data: 指标数据

        Returns:
            形态信息
        """
        try:
            # 这里简化处理，实际实现需要调用砖形图、N型结构等检测函数
            return {"is_brick_red": 0, "is_brick_green": 0, "brick_count": 0, "is_n_structure": 0, "is_double_gun": 0}
        except Exception:
            return {"is_brick_red": 0, "is_brick_green": 0, "brick_count": 0, "is_n_structure": 0, "is_double_gun": 0}

    def _detect_stage(self, indicator_data: dict[str, Any]) -> dict[str, Any]:
        """
        检测主力阶段

        Args:
            indicator_data: 指标数据

        Returns:
            阶段信息
        """
        try:
            # 这里简化处理，实际实现需要调用麒麟会等检测函数
            return {"stage": None, "stage_confidence": None}
        except Exception:
            return {"stage": None, "stage_confidence": None}


def main():
    """测试函数"""
    syncer = TrackingSyncer()

    # 测试同步单只股票
    print("\n=== 测试同步单只股票 ===")
    result = syncer.sync_daily("600519.SH", days=30)
    print(f"结果：{result}")

    # 测试同步所有活跃股票
    print("\n=== 测试同步所有活跃股票 ===")
    result = syncer.sync_all_active(days=30)
    print(f"结果：{result}")


if __name__ == "__main__":
    main()
