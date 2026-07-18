#!/usr/bin/env python3
"""
性能基准脚本：对两个已知热点计时，并支持行为一致性校验。

热点 A：modules/simulator/market_context.py::precompute_market_contexts()
热点 B：modules/datasource.py 中 SQLite/Composite 版 get_kline_dicts() 的批量逐股调用

用法（项目根目录下执行）：
    .venv/bin/python scripts/benchmark_perf.py                          # 计时并打印结果
    .venv/bin/python scripts/benchmark_perf.py --save /tmp/bench_baseline.json  # 保存结果指纹
    .venv/bin/python scripts/benchmark_perf.py --check /tmp/bench_baseline.json # 与基线比对

--check 用于验证「优化不改变函数行为与返回格式」：比对热点 A 的全部输出
（regime/三项得分/notes）与热点 B 每只股票的完整记录哈希，不一致时退出码为 1。

注意：本脚本直接使用真实数据库（DB_PATH 环境变量，默认 data/stock_data.db），
不做测试环境隔离；B3 场景（days + end_date）仅作诊断，不参与指纹比对。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.database import get_connection, get_db_path
from modules.datasource import CompositeDataSource, SqliteDataSource
from modules.simulator.market_context import precompute_market_contexts

N_DATES = 250  # 热点 A：交易日窗口长度
N_STOCKS = 100  # 热点 B：批量查询的股票数
KLINE_DAYS = 250  # 热点 B：单次查询的 K 线天数
REPEAT = 3  # 每个场景重复次数，取均值
B3_END_DATE = "20260710"  # 热点 B 诊断场景的 end_date


def load_trade_dates() -> list[str]:
    """从真实库取最近 N_DATES 个交易日（升序），模拟回测/模拟器窗口。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM daily_kline ORDER BY trade_date DESC LIMIT ?",
            (N_DATES,),
        ).fetchall()
    return sorted(row[0] for row in rows)


def load_sample_codes() -> list[str]:
    """从真实库取前 N_STOCKS 只股票代码（按代码排序，保证可复现）。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ts_code FROM stock_basic ORDER BY ts_code LIMIT ?",
            (N_STOCKS,),
        ).fetchall()
    return [row[0] for row in rows]


def serialize_contexts(result: dict) -> dict:
    """把 precompute 结果序列化为可比对的基础类型结构。"""
    return {
        date: [ctx.regime.value, ctx.index_trend, ctx.breadth, ctx.moneyflow_score, list(ctx.notes)]
        for date, ctx in sorted(result.items())
    }


def hash_kline_records(records: list[dict]) -> str:
    """对单只股票返回的完整 K 线记录列表计算 sha256 指纹。"""
    h = hashlib.sha256()
    h.update(json.dumps(records, sort_keys=True, default=str).encode())
    return h.hexdigest()


def bench_scenario_a(dates: list[str]) -> tuple[float, dict]:
    """热点 A：precompute_market_contexts 全窗口计时，返回 (均值毫秒, 序列化结果)。"""
    ds = CompositeDataSource("sqlite")
    # 暖身一次，消除冷页缓存影响
    result = precompute_market_contexts(dates, datasource=ds)
    samples = []
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        result = precompute_market_contexts(dates, datasource=ds)
        samples.append(time.perf_counter() - t0)
    return sum(samples) / REPEAT * 1000, serialize_contexts(result)


def bench_scenario_b(codes: list[str], end_date: str | None = None) -> tuple[float, dict[str, list]]:
    """热点 B：批量逐股调用 get_kline_dicts，返回 (单次均值毫秒, 每股指纹)。

    同时覆盖 SqliteDataSource 与 CompositeDataSource("sqlite")（生产默认路径）。
    end_date 非空时走「days + end_date」诊断路径（B3，不参与指纹比对）。
    """
    sources = {
        "sqlite": SqliteDataSource(),
        "composite": CompositeDataSource("sqlite"),
    }
    # 暖身
    for code in codes:
        for ds in sources.values():
            ds.get_kline_dicts(code, days=KLINE_DAYS, end_date=end_date)

    total_ms = 0.0
    fingerprints: dict[str, list] = {}
    for name, ds in sources.items():
        samples = []
        records_by_code: dict[str, list[dict]] = {}
        for _ in range(REPEAT):
            t0 = time.perf_counter()
            for code in codes:
                records_by_code[code] = ds.get_kline_dicts(code, days=KLINE_DAYS, end_date=end_date)
            samples.append(time.perf_counter() - t0)
        per_call_ms = sum(samples) / REPEAT / len(codes) * 1000
        fingerprints[name] = [
            [code, len(records_by_code[code]), hash_kline_records(records_by_code[code])] for code in codes
        ]
        total_ms += per_call_ms
        print(f"    - {name:10s}: {per_call_ms:.3f} ms/次（{len(codes)} 股 x {REPEAT} 轮取均值）")
    return total_ms / len(sources), fingerprints


def bench_scenario_b_batch(codes: list[str]) -> tuple[float, dict[str, list]]:
    """热点 B 对照：get_kline_dicts_batch 共享连接批量查询，返回 (每股均摊毫秒, 每股指纹)。"""
    ds = CompositeDataSource("sqlite")
    # 暖身
    ds.get_kline_dicts_batch(codes, days=KLINE_DAYS)
    samples = []
    records_map: dict[str, list[dict]] = {}
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        records_map = ds.get_kline_dicts_batch(codes, days=KLINE_DAYS)
        samples.append(time.perf_counter() - t0)
    per_stock_ms = sum(samples) / REPEAT / len(codes) * 1000
    fingerprints = [[code, len(records_map[code]), hash_kline_records(records_map[code])] for code in codes]
    return per_stock_ms, fingerprints


def main() -> int:
    parser = argparse.ArgumentParser(description="两个性能热点的基准计时（真实数据库）")
    parser.add_argument("--save", metavar="FILE", help="保存本次结果指纹到 JSON 文件")
    parser.add_argument("--check", metavar="FILE", help="与指定基线 JSON 比对行为一致性")
    args = parser.parse_args()

    print("=" * 72)
    print("性能基准：precompute_market_contexts + SQLite 版 get_kline_dicts")
    print("=" * 72)
    print(f"数据库: {get_db_path()}")
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily_kline").fetchone()
    print(f"daily_kline: {row[0]} 行, {row[1]} ~ {row[2]}")

    dates = load_trade_dates()
    codes = load_sample_codes()
    print(f"热点 A 窗口: {dates[0]} ~ {dates[-1]} 共 {len(dates)} 天; 热点 B 样本: {len(codes)} 股")
    print()

    # ---- 热点 A ----
    print(f"[A] precompute_market_contexts(dates x {len(dates)})")
    a_ms, a_serialized = bench_scenario_a(dates)
    print(f"  平均耗时: {a_ms:.1f} ms（暖身 1 次后 {REPEAT} 轮均值）")
    print()

    # ---- 热点 B：days-only（主场景） ----
    print(f"[B] get_kline_dicts 批量查询（{len(codes)} 股, days={KLINE_DAYS}）")
    b_ms, b_fingerprints = bench_scenario_b(codes)
    print(f"  两个数据源平均: {b_ms:.3f} ms/次")
    print()

    # ---- 热点 B 对照：共享连接批量查询 ----
    print(f"[B-批量] get_kline_dicts_batch 共享连接批量查询（{len(codes)} 股, days={KLINE_DAYS}）")
    b_batch_ms, b_batch_fingerprints = bench_scenario_b_batch(codes)
    batch_same = b_batch_fingerprints == b_fingerprints["composite"]
    print(f"  单连接批量: {b_batch_ms:.3f} ms/股（总 {b_batch_ms * len(codes):.1f} ms）")
    print(f"  相对逐股循环加速比: {b_ms / b_batch_ms:.2f}x; 与逐股返回记录完全一致: {batch_same}")
    print()

    # ---- 热点 B3：days + end_date（诊断，不参与指纹比对） ----
    print(f"[B3-诊断] get_kline_dicts(days={KLINE_DAYS}, end_date={B3_END_DATE})")
    b3_ms, b3_fingerprints = bench_scenario_b(codes, end_date=B3_END_DATE)
    b3_rows = sum(item[1] for item in b3_fingerprints["composite"]) / len(codes)
    print(f"  平均: {b3_ms:.3f} ms/次, composite 平均每股返回 {b3_rows:.0f} 行（days={KLINE_DAYS}）")
    print()

    summary = {"A_ms": a_ms, "B_ms": b_ms, "B_batch_ms": b_batch_ms, "B3_ms": b3_ms}

    if args.save:
        payload = {"summary": summary, "scenario_a": a_serialized, "scenario_b": b_fingerprints}
        Path(args.save).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        print(f"结果指纹已保存: {args.save}")

    if args.check:
        baseline = json.loads(Path(args.check).read_text())
        base_summary = baseline["summary"]
        print(f"{'场景':<10}{'基线':>12}{'本次':>12}{'加速比':>10}")
        for key, label in (("A_ms", "A"), ("B_ms", "B"), ("B_batch_ms", "B-批量"), ("B3_ms", "B3-诊断")):
            if key not in base_summary:
                continue
            base, cur = base_summary[key], summary[key]
            print(f"{label:<10}{base:>10.1f}ms{cur:>10.1f}ms{base / cur:>9.2f}x")

        mismatches = []
        if baseline["scenario_a"] != a_serialized:
            for date, entry in baseline["scenario_a"].items():
                if a_serialized.get(date) != entry:
                    mismatches.append(f"  A/{date}: 基线 {entry} != 本次 {a_serialized.get(date)}")
        for name in baseline["scenario_b"]:
            base_map = {item[0]: item for item in baseline["scenario_b"][name]}
            cur_map = {item[0]: item for item in b_fingerprints[name]}
            for code, base_item in base_map.items():
                if cur_map.get(code) != base_item:
                    mismatches.append(f"  B/{name}/{code}: 行数或记录哈希不一致")
        if mismatches:
            print(f"\n行为一致性校验失败，共 {len(mismatches)} 处差异（前 10 处）:")
            print("\n".join(mismatches[:10]))
            return 1
        print("行为一致性校验通过：热点 A 全部输出与热点 B 全部记录与基线完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
