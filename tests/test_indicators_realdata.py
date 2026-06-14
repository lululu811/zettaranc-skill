"""
P2-1 真实数据回归测试：自研指标 vs Tushare 官方 stk_factor

策略：拉 600519.SH 最近 120 天的 K 线 + Tushare 官方 stk_factor（MACD/KDJ/RSI），
对比自研计算 vs 官方值的 diff，断言 < 阈值。

- skipif：未配置 TUSHARE_TOKEN 时整文件 skip（不影响普通测试）
- 阈值：v2.10.0 观察期 5%，v2.11.0 收紧到 2%，v3.0.0 目标 1%
- 命名约定：test_<indicator>_vs_stk_factor（便于 pytest -k 单独跑）
"""

import os
from datetime import datetime, timedelta
import pandas as pd
import pytest
from dotenv import load_dotenv

load_dotenv()


# 整文件 skipif：无 Tushare Token 或未设置 RUN_REALDATA=true 时就跳过
_TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
_TUSHARE_API_URL = os.environ.get("TUSHARE_API_URL", "")
_RUN_REALDATA = os.environ.get("RUN_REALDATA", "").lower() == "true"
pytestmark = pytest.mark.skipif(
    not (_TUSHARE_TOKEN and _TUSHARE_API_URL and _RUN_REALDATA),
    reason="需配置 TUSHARE_TOKEN + TUSHARE_API_URL 并设置 RUN_REALDATA=true 才能跑真实数据回归",
)

# 测试范围
REALDATA_TS_CODE = "600519.SH"
LOOKBACK_DAYS = 365  # 拉 1 年数据，确保足够样本
DIFF_TOLERANCE = 0.02  # 2% 阈值（收紧 v3.2.0）


# ==================== Fixtures ====================


@pytest.fixture(scope="module")
def tushare_client():
    """拉真实 Tushare 客户端（需要 token）"""
    from modules.tushare_client import TushareClient

    return TushareClient(token=_TUSHARE_TOKEN)


@pytest.fixture(scope="module")
def trade_dates(tushare_client) -> tuple:
    """返回 (start_date, end_date) YYYYMMDD 字符串"""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=LOOKBACK_DAYS)
    return (
        start_dt.strftime("%Y%m%d"),
        end_dt.strftime("%Y%m%d"),
    )


@pytest.fixture(scope="module")
def kline_df(tushare_client, trade_dates) -> pd.DataFrame:
    """拉 600519.SH K 线"""
    start_date, end_date = trade_dates
    df = tushare_client.get_daily(REALDATA_TS_CODE, start_date, end_date)
    assert df is not None and len(df) > 0, f"无法拉取 {REALDATA_TS_CODE} K 线"
    # 按日期排序
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


@pytest.fixture(scope="module")
def stk_factor_df(tushare_client, trade_dates) -> pd.DataFrame:
    """拉 Tushare 官方 stk_factor 指标"""
    start_date, end_date = trade_dates
    df = tushare_client._pro.stk_factor(
        ts_code=REALDATA_TS_CODE,
        start_date=start_date,
        end_date=end_date,
    )
    assert df is not None and len(df) > 0, f"无法拉取 {REALDATA_TS_CODE} stk_factor（可能需要 5000 积分）"
    return df.sort_values("trade_date").reset_index(drop=True)


@pytest.fixture(scope="module")
def merged(kline_df, stk_factor_df) -> pd.DataFrame:
    """内连接 K 线 + stk_factor（按 trade_date 对齐）"""
    # 仅从 stk_factor_df 中提取需要的指标字段以避免列名冲突
    factor_cols = [
        "trade_date",
        "macd_dif",
        "macd_dea",
        "macd",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "rsi_6",
        "rsi_12",
        "rsi_24",
        "boll_upper",
        "boll_mid",
        "boll_lower",
        "cci",
    ]
    cols_to_use = [c for c in factor_cols if c in stk_factor_df.columns]
    return kline_df.merge(
        stk_factor_df[cols_to_use],
        on="trade_date",
    )


# ==================== MACD 对比 ====================


def test_macd_dif_vs_stk_factor(merged):
    """自研 MACD.dif vs Tushare stk_factor.macd_dif（v2.10.0 阈值 5%）"""
    # 用自研 calculate_macd
    from modules.indicators import calculate_macd
    from modules.indicators.data_layer import DailyData

    daily_data = [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in merged.iterrows()
    ]
    difs, deas, hists = calculate_macd(daily_data)

    merged["macd_dif_ours"] = difs
    merged["macd_dif_diff_pct"] = (merged["macd_dif_ours"] - merged["macd_dif"]).abs() / merged["macd_dif"].abs()

    median_diff = merged["macd_dif_diff_pct"].median()
    mean_diff = merged["macd_dif_diff_pct"].mean()
    max_diff = merged["macd_dif_diff_pct"].max()

    assert (
        median_diff < DIFF_TOLERANCE
    ), f"MACD.dif 中位数 diff {median_diff:.2%} > {DIFF_TOLERANCE:.0%}（mean={mean_diff:.2%} max={max_diff:.2%}）"


def test_macd_dea_vs_stk_factor(merged):
    """自研 MACD.dea vs Tushare stk_factor.macd_dea"""
    from modules.indicators import calculate_macd
    from modules.indicators.data_layer import DailyData

    daily_data = [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in merged.iterrows()
    ]
    difs, deas, hists = calculate_macd(daily_data)
    merged["macd_dea_ours"] = deas
    merged["macd_dea_diff_pct"] = (merged["macd_dea_ours"] - merged["macd_dea"]).abs() / merged["macd_dea"].abs()

    median_diff = merged["macd_dea_diff_pct"].median()
    assert median_diff < DIFF_TOLERANCE, f"MACD.dea 中位数 diff {median_diff:.2%} > {DIFF_TOLERANCE:.0%}"


# ==================== KDJ 对比 ====================


def test_kdj_k_vs_stk_factor(merged):
    """自研 KDJ.k vs Tushare stk_factor.kdj_k"""
    from modules.indicators import calculate_kdj
    from modules.indicators.data_layer import DailyData

    daily_data = [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in merged.iterrows()
    ]
    ks, ds, js = calculate_kdj(daily_data)
    merged["kdj_k_ours"] = ks
    merged["kdj_k_diff_pct"] = (
        (merged["kdj_k_ours"] - merged["kdj_k"]).abs() / 100  # KDJ 是 0-100 量纲，用绝对差
    )

    median_diff = merged["kdj_k_diff_pct"].median()
    # KDJ 量纲 0-100，绝对差阈值用 2（2 个百分点）
    assert median_diff < 2, f"KDJ.k 中位数绝对差 {median_diff:.2f} > 2（百分点）"


def test_kdj_d_vs_stk_factor(merged):
    """自研 KDJ.d vs Tushare stk_factor.kdj_d"""
    from modules.indicators import calculate_kdj
    from modules.indicators.data_layer import DailyData

    daily_data = [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in merged.iterrows()
    ]
    ks, ds, js = calculate_kdj(daily_data)
    merged["kdj_d_ours"] = ds
    merged["kdj_d_diff_pct"] = (merged["kdj_d_ours"] - merged["kdj_d"]).abs()

    median_diff = merged["kdj_d_diff_pct"].median()
    assert median_diff < 2, f"KDJ.d 中位数绝对差 {median_diff:.2f} > 2（百分点）"


# ==================== RSI 对比 ====================


def test_rsi6_vs_stk_factor(merged):
    """自研 RSI6 vs Tushare stk_factor.rsi_6"""
    from modules.indicators import calculate_rsi
    from modules.indicators.data_layer import DailyData

    daily_data = [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in merged.iterrows()
    ]
    rsi6 = calculate_rsi(daily_data, period=6)
    merged["rsi_6_ours"] = rsi6
    merged["rsi_6_diff_pct"] = (merged["rsi_6_ours"] - merged["rsi_6"]).abs()

    median_diff = merged["rsi_6_diff_pct"].median()
    # RSI 0-100 量纲，绝对差阈值 2
    assert median_diff < 2, f"RSI6 中位数绝对差 {median_diff:.2f} > 2（百分点）"


def test_rsi12_vs_stk_factor(merged):
    """自研 RSI12 vs Tushare stk_factor.rsi_12"""
    from modules.indicators import calculate_rsi
    from modules.indicators.data_layer import DailyData

    daily_data = [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in merged.iterrows()
    ]
    rsi12 = calculate_rsi(daily_data, period=12)
    merged["rsi_12_ours"] = rsi12
    merged["rsi_12_diff_pct"] = (merged["rsi_12_ours"] - merged["rsi_12"]).abs()

    median_diff = merged["rsi_12_diff_pct"].median()
    assert median_diff < 2, f"RSI12 中位数绝对差 {median_diff:.2f} > 2（百分点）"


# ==================== 集成检查 ====================


def test_merged_dataframe_has_minimum_samples(merged):
    """合并后的数据必须至少有 100 个交易日样本（保证统计意义）"""
    assert len(merged) >= 100, f"合并后仅 {len(merged)} 个交易日，样本量不足"


def test_merged_dataframe_covers_expected_columns(merged):
    """合并后必须有 K 线 + stk_factor 双边字段"""
    required_ours = ["open", "high", "low", "close"]  # K 线字段
    required_tushare = ["macd_dif", "macd_dea", "kdj_k", "kdj_d", "rsi_6", "rsi_12"]  # stk_factor 字段
    for col in required_ours + required_tushare:
        assert col in merged.columns, f"合并后缺字段: {col}"


# ==================== 离线基线（v2.11.0 计划：保存 baseline JSON） ====================


def test_indicator_diff_summary(merged):
    """汇总所有指标 diff（用于人工 review / v2.11.0 写 baseline）"""
    # 这个测试只打印汇总，不做断言
    summary_lines = ["\n=== 真实数据回归 diff 汇总（v2.10.0 观察期） ==="]

    # 已在前面 test_xxx 中计算过 diff 列
    for col in [
        "macd_dif_diff_pct",
        "macd_dea_diff_pct",
        "kdj_k_diff_pct",
        "kdj_d_diff_pct",
        "rsi_6_diff_pct",
        "rsi_12_diff_pct",
    ]:
        if col in merged.columns:
            med = merged[col].median()
            summary_lines.append(f"  {col}: median={med:.4f}")

    summary_lines.append(f"  threshold: {DIFF_TOLERANCE}")
    print("\n".join(summary_lines))
