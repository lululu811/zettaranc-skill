#!/usr/bin/env python3
"""
[薄壳] 批量计算自选股清单的指标缓存（已有 K 线，只算指标）
v2.10.0 重构：业务逻辑迁至 modules.data_sync.DataSyncer.sync_all_indicators
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.data_sync import DataSyncer
from modules.tushare_client import TushareClient  # noqa: F401  触发 env / token 校验
from scripts._common import load_watchlist


def main():
    p = argparse.ArgumentParser(description="批量计算自选股的指标缓存（薄壳）")
    args = p.parse_args()

    ts_codes = load_watchlist()
    if not ts_codes:
        print("自选股清单为空")
        return

    syncer = DataSyncer()
    results = syncer.sync_all_indicators(ts_codes=ts_codes)
    synced = sum(1 for v in results.values() if v > 0)
    print(f"sync_all_indicators 完成: 总 {len(ts_codes)} 只, 成功 {synced} 只")


if __name__ == "__main__":
    main()
