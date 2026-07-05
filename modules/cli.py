#!/usr/bin/env python3
"""Z哥量化工具 CLI（v2.10.0 统一入口）

用法：
    python -m modules.cli analyze 600487.SH
    python -m modules.cli screen --strategy B1
    python -m modules.cli score 600487.SH
    python -m modules.cli workflow
    python -m modules.cli watchlist add 600487.SH --tags 通信设备
    python -m modules.cli diagnose 600487.SH
    python -m modules.cli sync init
    python -m modules.cli sync sync 600487.SH
    python -m modules.cli sync status
    python -m modules.cli sync stk-factor 600487.SH

设计：所有命令通过 `zt` entry point（已在 pyproject.toml 注册）暴露。
本文件取代 v2.9.0 散落在 5 个模块的独立 main()（screener / data_sync /
portfolio_diagnosis / watchlist / indicators.data_layer）。
"""

from __future__ import annotations

import argparse
import json
import sys
import os
from pathlib import Path

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）


def _json_output(data):
    """Print data as JSON and exit."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


# CLI 中文别名 → screener 英文 criteria 的统一映射
STRATEGY_ALIAS = {
    "B1": "b1",
    "B2": "b2_breakout",
    "B3": "b3_consensus",
    "完美图形": "perfect",
    "超级B1": "super_b1",
    "长安战法": "changan",
    "建仓波": "build_wave",
    "吸筹": "xishou",
    "安全": "safe",
    "超跌": "oversold",
    "突破": "breakout",
    "牵牛": "bull_rope",
    "牛绳": "bull_rope",
    "沙漏": "sandglass_perfect",
    "沙漏评分": "sandglass_perfect",
    "量比战法": "volume_ratio_super",
}

STRATEGY_CHOICES = list(STRATEGY_ALIAS.keys())


def _analyze_core(ts_code: str, days: int = 120) -> dict:
    """
    核心分析逻辑，返回所有分析结果的字典。
    cmd_analyze 和 cmd_score 共用此函数，避免重复计算。
    """
    from modules.indicators import analyze_stock
    from modules.indicators.data_layer import get_kline_data, DailyData
    from modules.strategies import detect_all_strategies
    from modules.portfolio_diagnosis import diagnose_stock
    from modules.screener import analyze_stock as screener_analyze

    # 1. 指标分析
    result = analyze_stock(ts_code, days=days)

    # 2. 主力阶段
    wave_data = None
    kirin_data = None
    try:
        from modules.indicators import detect_three_waves, detect_kirin_stage

        klines = get_kline_data(ts_code, days=days)
        if klines:
            daily_klines = []
            for i, k in enumerate(klines):
                prev_close = klines[i - 1].close if i > 0 else k.close
                daily_klines.append(
                    DailyData(
                        ts_code=k.ts_code,
                        trade_date=k.trade_date,
                        open=k.open,
                        high=k.high,
                        low=k.low,
                        close=k.close,
                        vol=k.vol,
                        amount=k.amount,
                        pct_chg=k.pct_chg,
                        prev_close=prev_close,
                    )
                )
            wave_data = detect_three_waves(daily_klines)
            kirin_data = detect_kirin_stage(daily_klines)
    except Exception:
        pass

    # 3. 策略信号
    signals = detect_all_strategies(ts_code, days=days)

    # 4. 诊断
    diagnosis = diagnose_stock(ts_code, days=days)

    # 5. screener 评分（复用已有数据，不再重复拉取）
    score = screener_analyze(ts_code)

    return {
        "ts_code": ts_code,
        "days": days,
        "result": result,
        "wave_data": wave_data,
        "kirin_data": kirin_data,
        "signals": signals,
        "diagnosis": diagnosis,
        "score": score,
    }


def cmd_analyze(args):
    """分析单只股票（指标 + 主力 + 战法 + 诊断 + 评分）"""
    core = _analyze_core(args.ts_code, args.days)

    ts_code = core["ts_code"]
    result = core["result"]
    wave_data = core["wave_data"]
    kirin_data = core["kirin_data"]
    signals = core["signals"]
    diagnosis = core["diagnosis"]
    score = core["score"]

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "ts_code": ts_code,
            "name": getattr(diagnosis, "name", ts_code),
            "price": getattr(diagnosis, "price", 0),
            "indicators": {
                "kdj": {"k": result.k, "d": result.d, "j": result.j},
                "macd": {
                    "dif": result.dif,
                    "dea": result.dea,
                    "hist": result.macd_hist,
                    "veto": getattr(diagnosis, "macd_veto", False),
                },
                "bbi": result.bbi,
                "white_line": getattr(diagnosis, "white_line", 0),
                "yellow_line": getattr(diagnosis, "yellow_line", 0),
                "rsi": {"rsi6": result.rsi6, "rsi12": result.rsi12, "rsi24": result.rsi24},
            },
            "waves": {
                "type": wave_data["wave"] if wave_data else "未知",
                "confidence": wave_data["confidence"] if wave_data else 0,
            },
            "kirin": {
                "phase": kirin_data["stage"] if kirin_data else "未知",
                "confidence": kirin_data["confidence"] if kirin_data else 0,
            },
            "strategies": [
                {
                    "strategy": s.strategy.value,
                    "date": s.trade_date,
                    "confidence": s.confidence,
                    "action": s.action,
                    "description": s.description,
                }
                for s in signals[:10]
            ],
            "diagnosis": {
                "price_position": getattr(diagnosis, "price_position", ""),
                "trend_status": getattr(diagnosis, "trend_status", ""),
                "sell_score": getattr(diagnosis, "sell_score", 0),
                "sell_score_desc": getattr(diagnosis, "sell_score_desc", ""),
                "kirin_phase": getattr(diagnosis, "kirin_phase", ""),
                "bull_rope": getattr(diagnosis, "bull_rope_status", ""),
                "sandglass_score": getattr(diagnosis, "sandglass_score", 0),
                "is_centipede": getattr(diagnosis, "is_centipede", False),
                "risk_level": getattr(diagnosis, "risk_level", ""),
                "recommendation": getattr(diagnosis, "recommendation", ""),
            },
            "score": {
                "total": score.score,
                "b1_score": score.b1_score,
                "trend_score": score.trend_score,
                "volume_score": score.volume_score,
                "risk_score": score.risk_score,
                "rating": score.rating,
                "reasons": score.reasons,
                "warnings": score.warnings,
            },
        }
        _json_output(json_result)
        return

    # ── 人类可读输出（保持原样） ──
    print(f"\n{'=' * 60}")
    print(f"股票分析: {ts_code}")
    print(f"{'=' * 60}")

    print("\n【技术指标】")
    print(f"  日期: {result.trade_date}")
    print(f"  KDJ:  K={result.k:.2f}  D={result.d:.2f}  J={result.j:.2f}")
    print(f"  MACD: DIF={result.dif:.4f}  DEA={result.dea:.4f}  柱={result.macd_hist:.4f}")
    print(f"  BBI:  {result.bbi:.2f}")
    print(f"  均线: MA5={result.ma5:.2f}  MA10={result.ma10:.2f}  MA20={result.ma20:.2f}")
    print(f"  RSI:  {result.rsi6:.2f}/{result.rsi12:.2f}/{result.rsi24:.2f}")
    print(f"  砖型图: {result.brick_trend}({result.brick_count}块)  值={result.brick_value:.2f}")

    print("\n【主力阶段】")
    if wave_data:
        print(f"  三波理论: {wave_data['wave']} (conf={wave_data['confidence']}) → {wave_data['b1_suggestion']}")
        if wave_data["stats"]:
            s = wave_data["stats"]
            print(f"    低点→当前: {s['low_price']:.1f}→{s['high_price']:.1f} 涨幅{s['gain_pct']:.1f}%")
            print(f"    涨停{s['limit_up_count']}次 阳线占比{s['red_ratio'] * 100:.0f}% 日均{s['avg_daily_gain']:.2f}%")
    if kirin_data:
        print(f"  麒麟会: {kirin_data['stage']} (conf={kirin_data['confidence']}) → {kirin_data['operation']}")
        if kirin_data["sub_type"] != "未知":
            print(f"    子类型: {kirin_data['sub_type']}")
        if kirin_data.get("scores"):
            sc = kirin_data["scores"]
            print(f"    评分: 吸{sc['xishou']} 拉{sc['lasheng']} 派{sc['paifa']} 落{sc['luoluo']}")
    if not wave_data and not kirin_data:
        print("  无 K 线数据，跳过主力阶段分析")

    print("\n【战法信号】")
    if not signals:
        print("  无信号")
    else:
        critical = [s for s in signals if s.priority.value == 3]
        opportunity = [s for s in signals if s.priority.value == 2]
        observe = [s for s in signals if s.priority.value == 1]

        if critical:
            print(f"  🔴 紧急 ({len(critical)}个):")
            for s in critical[:3]:
                print(f"     {s.trade_date} {s.strategy.value}: {s.description}")
        if opportunity:
            print(f"  🟢 机会 ({len(opportunity)}个):")
            for s in opportunity[:3]:
                print(f"     {s.trade_date} {s.strategy.value}: {s.description}")
        if observe:
            print(f"  ⚪ 观察 ({len(observe)}个):")
            for s in observe[:3]:
                print(f"     {s.trade_date} {s.strategy.value}: {s.description}")

    print("\n【综合评分】")
    print(f"  总分: {score.score:.1f}  {score.rating}")
    print(
        f"  B1评分: {score.b1_score:.1f}  趋势: {score.trend_score:.1f}  量价: {score.volume_score:.1f}  风险: {score.risk_score:.1f}"
    )
    if score.reasons:
        print(f"  理由: {', '.join(score.reasons[:5])}")
    if score.warnings:
        print(f"  警告: {', '.join(score.warnings[:3])}")

    print("\n【持仓诊断】")
    from modules.portfolio_diagnosis import format_report

    print(format_report(diagnosis))


def cmd_screen(args):
    """筛选股票（调 screener.screen_stocks）"""
    from modules.screener import screen_stocks

    criteria = STRATEGY_ALIAS.get(args.strategy, args.strategy)

    results = screen_stocks(
        criteria=criteria,
        max_stocks=args.limit if args.limit > 0 else 0,
        use_parallel=not args.no_parallel,
    )

    # 输出前 limit 只（limit=0 时输出全部 500 上限内的命中）
    output_limit = args.limit if args.limit > 0 else len(results)

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "criteria": criteria,
            "count": len(results[:output_limit]),
            "stocks": [
                {
                    "ts_code": r.ts_code,
                    "name": r.name,
                    "score": r.score,
                    "rating": r.rating,
                    "reasons": getattr(r, "reasons", []) or [],
                    "warnings": getattr(r, "warnings", []) or [],
                }
                for r in results[:output_limit]
            ],
        }
        _json_output(json_result)
        return

    # ── 人类可读输出（保持原样） ──
    print(f"\n{'=' * 60}")
    print(f"股票筛选 (criteria={criteria}, 上限={args.limit or '全市场'})")
    print(f"{'=' * 60}")
    print(f"\n扫描完成，命中: {len(results)} 只\n")

    for r in results[:output_limit]:
        print(f"  {r.ts_code:<12} {r.name:<8} score={r.score:.1f}  {r.rating}")
        reasons = getattr(r, "reasons", []) or []
        warnings = getattr(r, "warnings", []) or []
        if reasons:
            print(f"    reasons: {','.join(reasons[:3])}")
        if warnings:
            print(f"    warnings: {','.join(warnings[:3])}")


def cmd_score(args):
    """单只股票综合评分（复用 _analyze_core，不重复计算）"""
    from modules.screener import format_stock_score

    if not args.ts_code:
        print("请指定股票代码: zt score <ts_code>")
        sys.exit(1)

    core = _analyze_core(args.ts_code, days=60)
    score = core["score"]

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "ts_code": score.ts_code,
            "name": score.name,
            "score": score.score,
            "b1_score": score.b1_score,
            "trend_score": score.trend_score,
            "volume_score": score.volume_score,
            "risk_score": score.risk_score,
            "rating": score.rating,
            "reasons": score.reasons,
            "warnings": score.warnings,
        }
        _json_output(json_result)
        return

    # ── 人类可读输出 ──
    print(format_stock_score(score))


def cmd_workflow(args):
    """每日五步工作流（来自 screener.py workflow action）"""
    from modules.screener import daily_workflow

    daily_workflow()


def cmd_watchlist(args):
    """自选股管理"""
    from modules.watchlist import (
        add_watch,
        remove_watch,
        list_watch,
        scan_watchlist,
        generate_daily_report,
    )

    action = args.action

    if action == "add":
        tags = args.tags if hasattr(args, "tags") and args.tags else ""
        add_watch(args.ts_code, tags=tags)
        print(f"已添加: {args.ts_code}")

    elif action == "remove":
        remove_watch(args.ts_code)
        print(f"已移除: {args.ts_code}")

    elif action == "list":
        stocks = list_watch()
        print(f"\n自选股列表 ({len(stocks)}只):")
        for s in stocks:
            tags = s.get("tags", "") or "无"
            added = s.get("added_date", s.get("updated_at", "未知"))
            print(f"  {s['ts_code']}  标签:{tags}  添加:{added}")

    elif action == "scan":
        result = scan_watchlist()
        alerts = result.get("alerts", [])
        summary = result.get("summary", {})

        # ── JSON 输出 ──
        if hasattr(args, "json") and args.json:
            # 按 ts_code 聚合 alerts
            stock_map = {}
            for a in alerts:
                if a.ts_code not in stock_map:
                    stock_map[a.ts_code] = {"ts_code": a.ts_code, "name": a.name, "signals": [], "alerts": []}
                stock_map[a.ts_code]["alerts"].append(
                    {
                        "alert_type": a.alert_type,
                        "level": a.level,
                        "message": a.message,
                    }
                )
            json_result = {
                "count": len(stock_map),
                "stocks": list(stock_map.values()),
            }
            _json_output(json_result)
            return

        # ── 人类可读输出（保持原样） ──
        print(f"\n扫描自选股 ({summary.get('total', 0)}只):")
        print(
            f"  B1={summary.get('b1_count', 0)}  B2={summary.get('b2_count', 0)}  "
            f"逃顶={summary.get('exit_count', 0)}  破位={summary.get('break_count', 0)}  "
            f"异动={summary.get('abnormal_count', 0)}"
        )
        for a in alerts[:20]:
            print(f"  [{a.level}] {a.ts_code} {a.name}  {a.alert_type}: {a.message}")

    elif action == "report":
        print(generate_daily_report())


def cmd_diagnose(args):
    """持仓诊断"""
    from modules.portfolio_diagnosis import diagnose_stock, format_report

    ts_code = args.ts_code
    diagnosis = diagnose_stock(ts_code, days=args.days)

    # ── JSON 输出 ──
    if args.json:
        from dataclasses import asdict

        _json_output(asdict(diagnosis))
        return

    # ── 人类可读输出（保持原样） ──
    print(format_report(diagnosis))


def cmd_sync(args):
    """数据同步（init / sync / status / stk-factor）"""
    import logging
    from datetime import datetime, timedelta
    from modules.data_sync import DataSyncer
    from modules.database import init_database
    from modules.datasource import get_datasource

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    action = args.sync_action

    if action == "init":
        init_database()
        print("数据库初始化完成")

    elif action == "sync":
        syncer = DataSyncer(datasource=get_datasource("tushare"))
        if args.ts_code:
            # 同步单只股票
            syncer.sync_daily_kline(args.ts_code)
            if not args.skip_indicators:
                print(f"正在同步指标缓存: {args.ts_code} ...")
                syncer.sync_indicator_cache(args.ts_code, days=args.days)
        else:
            # 批量同步所有股票
            syncer.sync_stock_basic()
            syncer.sync_all_daily_kline(days=args.days)
            if args.indicators and not args.skip_indicators:
                print("正在批量同步指标缓存...")
                syncer.sync_all_indicators()
        print("同步完成")
        print(syncer.get_sync_status())

    elif action == "stk-factor":
        syncer = DataSyncer(datasource=get_datasource("tushare"))
        if args.ts_code:
            print(f"正在同步 Tushare 官方指标: {args.ts_code} ...")
            start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            count = syncer.sync_stk_factor(args.ts_code, start_date=start_date, end_date=end_date)
            print(f"同步完成，{count} 条")
        else:
            print("正在批量同步 Tushare 官方指标...")
            results = syncer.sync_all_stk_factor(days=args.days)
            success = sum(1 for v in results.values() if v > 0)
            print(f"批量同步完成，成功 {success}/{len(results)}")

    elif action == "status":
        syncer = DataSyncer(datasource=get_datasource("tushare"))
        status = syncer.get_sync_status()
        print("=" * 50)
        print(f"  数据库: {status.get('db_path', 'N/A')}")
        print(f"  股票: {status.get('stock_count', 0)}")
        print(f"  K线: {status.get('kline_count', 0)}")
        print("=" * 50)
        if status.get("sync_status"):
            print("同步状态:")
            for s in status["sync_status"]:
                print(f"  {s['data_type']}: {s.get('last_date', 'N/A')} ({s.get('status', 'N/A')})")


def cmd_self_optimize(args) -> int:
    """self-optimize 子命令."""
    from modules.self_optimizer import SelfOptimizer

    opt = SelfOptimizer(
        target=args.target,
        rounds=args.rounds,
        mode="dry_run",
    )
    if args.action == "run":
        result = opt.run()
        print(f"✓ Phase 3 done. {result['rounds']} rounds.")
        print(f"  keep={result['keep']} revert={result['revert']} break={result['break']}")
        print(f"  results.tsv: {result['results_tsv']}")
        print(f"  drafts: {result['drafts_dir']}")
        print("⚠️  请人工 review optimization_drafts/ 后决定合入")
        return 0
    if args.action == "status":
        print(f"target={opt.target} rounds={opt.rounds} mode={opt.mode}")
        return 0
    if args.action == "reset":
        state = Path("logs/self_optimizer_state.json")
        if state.exists():
            state.unlink()
            print("✓ state.json 已删除")
        return 0
    print(f"Unknown action: {args.action}")
    return 1


def add_self_optimize_parser(subparsers) -> None:
    """注册 self-optimize 子命令."""
    p = subparsers.add_parser("self-optimize", help="darwin self-optimizer")
    p.add_argument("action", choices=["run", "status", "reset"])
    p.add_argument("--target", choices=["trading", "skill"], default="trading")
    p.add_argument("--rounds", type=int, default=3)
    p.set_defaults(func=cmd_self_optimize)


def cmd_track(args):
    """跟踪池管理（add / remove / list / info / status / stats）"""
    from modules.tracking_manager import TrackingManager
    import json

    manager = TrackingManager()

    action = args.track_action

    if action == "add":
        if not args.ts_code:
            print("错误：添加股票需要指定股票代码")
            return
        success = manager.add_stock(
            ts_code=args.ts_code, name=args.name, reason=args.reason, strategy_tags=args.strategy, notes=args.notes
        )
        if args.json:
            print(json.dumps({"success": success}, ensure_ascii=False))

    elif action == "remove":
        if not args.ts_code:
            print("错误：移除股票需要指定股票代码")
            return
        success = manager.remove_stock(ts_code=args.ts_code, reason=args.reason)
        if args.json:
            print(json.dumps({"success": success}, ensure_ascii=False))

    elif action == "list":
        stocks = manager.list_stocks(status=args.status, strategy_tag=args.strategy[0] if args.strategy else None)
        if args.json:
            print(json.dumps(stocks, ensure_ascii=False, indent=2))
        else:
            if not stocks:
                print("跟踪池为空")
                return
            print(f"\n跟踪池（状态：{args.status}）")
            print("-" * 80)
            print(f"{'代码':<12} {'名称':<10} {'添加日期':<12} {'策略标签':<15} {'原因'}")
            print("-" * 80)
            for stock in stocks:
                print(
                    f"{stock['ts_code']:<12} {stock.get('name', '') or '':<10} {stock['add_date']:<12} {stock.get('strategy_tags', '') or '':<15} {stock.get('track_reason', '') or ''}"
                )
            print("-" * 80)
            print(f"共 {len(stocks)} 只股票")

    elif action == "info":
        if not args.ts_code:
            print("错误：查看股票信息需要指定股票代码")
            return
        stock = manager.get_stock_info(args.ts_code)
        if args.json:
            print(json.dumps(stock, ensure_ascii=False, indent=2) if stock else "{}")
        else:
            if not stock:
                print(f"股票 {args.ts_code} 不在跟踪池中")
                return
            print(f"\n股票信息：{stock['ts_code']}")
            print("-" * 40)
            print(f"名称：{stock.get('name', '') or ''}")
            print(f"状态：{stock['status']}")
            print(f"添加日期：{stock['add_date']}")
            print(f"移除日期：{stock.get('remove_date', '') or '未移除'}")
            print(f"策略标签：{stock.get('strategy_tags', '') or ''}")
            print(f"跟踪原因：{stock.get('track_reason', '') or ''}")
            print(f"备注：{stock.get('notes', '') or ''}")

    elif action == "status":
        if not args.ts_code:
            print("错误：更新状态需要指定股票代码")
            return
        success = manager.update_stock_status(ts_code=args.ts_code, status=args.status, notes=args.notes)
        if args.json:
            print(json.dumps({"success": success}, ensure_ascii=False))

    elif action == "stats":
        stats = manager.get_tracking_stats()
        distribution = manager.get_strategy_distribution()
        if args.json:
            print(json.dumps({"stats": stats, "distribution": distribution}, ensure_ascii=False, indent=2))
        else:
            print("\n跟踪池统计")
            print("-" * 40)
            print(f"总数量：{stats.get('total', 0)}")
            print(f"活跃：{stats.get('active', 0)}")
            print(f"暂停：{stats.get('paused', 0)}")
            print(f"已移除：{stats.get('removed', 0)}")
            print(f"今日新增：{stats.get('today_added', 0)}")
            if distribution:
                print("\n策略分布：")
                for strategy, count in sorted(distribution.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {strategy}: {count}只")


def build_parser():
    """构建并返回 zt CLI 的 ArgumentParser（支持独立导入测试）"""
    parser = argparse.ArgumentParser(
        prog="zt",
        description="Z哥量化工具 CLI（v2.10.0 统一入口）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  zt analyze 600487.SH
  zt analyze 600487.SH --json
  zt screen --strategy B1 --limit 20
  zt score 600487.SH
  zt diagnose 600487.SH
  zt watchlist add 600487.SH --tags 通信设备,5G
  zt watchlist scan
  zt backtest shaofu 600487.SH --days 250
  zt backtest multi 600487.SH --strategy b1,b2
  zt backtest portfolio 600487.SH,601318.SH
  zt trade add "4月25号买了100股茅台1800块"
  zt trade list
  zt trade review
  zt daily
  zt sync init
  zt sync sync 600487.SH
  zt simulate 600487.SH --days 250 --cost-model advanced --slippage dynamic
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令", required=True)

    # ── analyze ──
    p_analyze = subparsers.add_parser("analyze", help="分析单只股票（指标 + 主力阶段 + 战法信号 + 诊断）")
    p_analyze.add_argument("ts_code", help="股票代码，如 600487.SH")
    p_analyze.add_argument("--days", type=int, default=120, help="分析天数")
    p_analyze.add_argument("--json", action="store_true", help="JSON输出")

    # ── screen ──
    p_screen = subparsers.add_parser("screen", help="批量选股（11 种策略）")
    p_screen.add_argument("--strategy", choices=STRATEGY_CHOICES, default="B1", help="筛选策略（11 种别名）")
    p_screen.add_argument("--limit", type=int, default=20, help="输出数量（0=全市场 500 上限）")
    p_screen.add_argument("--no-parallel", action="store_true", help="禁用多进程并行")
    p_screen.add_argument("--json", action="store_true", help="JSON输出")

    # ── score（来自 screener.py score）──
    p_score = subparsers.add_parser("score", help="单只股票综合评分")
    p_score.add_argument("ts_code", nargs="?", help="股票代码，如 600487.SH")
    p_score.add_argument("--json", action="store_true", help="JSON输出")

    # ── workflow（来自 screener.py workflow）──
    subparsers.add_parser("workflow", help="每日五步工作流")

    # ── diagnose ──
    p_diag = subparsers.add_parser("diagnose", help="持仓诊断")
    p_diag.add_argument("ts_code", help="股票代码")
    p_diag.add_argument("--days", type=int, default=120, help="分析天数")
    p_diag.add_argument("--json", action="store_true", help="JSON输出")

    # ── watchlist（add/remove/list/scan/report）──
    p_wl = subparsers.add_parser("watchlist", help="自选股管理")
    p_wl.add_argument("action", choices=["add", "remove", "list", "scan", "report"], help="操作")
    p_wl.add_argument("ts_code", nargs="?", help="股票代码（add/remove 必填）")
    p_wl.add_argument("--tags", help="标签，逗号分隔")
    p_wl.add_argument("--json", action="store_true", help="JSON输出（仅 scan 操作）")

    # ── sync（init/sync/status/stk-factor）──
    p_sync = subparsers.add_parser("sync", help="数据同步（init/sync/status/stk-factor）")
    p_sync_sub = p_sync.add_subparsers(dest="sync_action", required=True)

    p_sync_sub.add_parser("init", help="初始化数据库")
    p_sync_run = p_sync_sub.add_parser("sync", help="同步日线 K 线（+ 可选指标缓存）")
    p_sync_run.add_argument("ts_code", nargs="?", help="股票代码（不传 = 全市场批量）")
    p_sync_run.add_argument("--days", type=int, default=730, help="同步天数")
    p_sync_run.add_argument("--indicators", action="store_true", help="批量同步完成后计算并缓存技术指标")
    p_sync_run.add_argument(
        "--skip-indicators", action="store_true", help="跳过指标缓存（单只默认同步，批量需 --indicators）"
    )
    p_sync_sub.add_parser("status", help="查看同步状态")
    p_sync_factor = p_sync_sub.add_parser("stk-factor", help="同步 Tushare 官方指标（diff 验证用）")
    p_sync_factor.add_argument("ts_code", nargs="?", help="股票代码（不传 = 全市场）")
    p_sync_factor.add_argument("--days", type=int, default=365, help="同步天数")

    # ── track（自我改进系统 - 跟踪池管理）──
    p_track = subparsers.add_parser("track", help="自我改进系统 - 跟踪池管理")
    p_track.add_argument("track_action", choices=["add", "remove", "list", "info", "status", "stats"], help="操作")
    p_track.add_argument("ts_code", nargs="?", help="股票代码")
    p_track.add_argument("--reason", help="跟踪/移除原因")
    p_track.add_argument("--strategy", nargs="+", help="策略标签（可多个）")
    p_track.add_argument("--name", help="股票名称")
    p_track.add_argument("--notes", help="备注")
    p_track.add_argument("--status", choices=["active", "paused", "removed"], default="active", help="状态筛选")
    p_track.add_argument("--json", action="store_true", help="JSON输出")
    # ── self-optimize (darwin self-optimizer) ──
    add_self_optimize_parser(subparsers)

    # ── backtest（shaofu / multi / portfolio）──
    # dest 字段名必须与 cli_commands.cmd_backtest 里 getattr(args, "backtest_sub", ...) 一致
    p_bt = subparsers.add_parser("backtest", help="策略回测")
    p_bt_sub = p_bt.add_subparsers(dest="backtest_sub", required=True)

    p_bt_shaofu = p_bt_sub.add_parser("shaofu", help="少妇战法六步回测")
    p_bt_shaofu.add_argument("ts_code", help="股票代码")
    p_bt_shaofu.add_argument("--days", type=int, default=250, help="回测天数")
    p_bt_shaofu.add_argument("--json", action="store_true", help="JSON输出")

    p_bt_multi = p_bt_sub.add_parser("multi", help="多策略融合回测")
    p_bt_multi.add_argument("ts_code", help="股票代码")
    p_bt_multi.add_argument("--strategy", default="b1,b2", help="策略列表，逗号分隔")
    p_bt_multi.add_argument("--days", type=int, default=120, help="回测天数")
    p_bt_multi.add_argument("--json", action="store_true", help="JSON输出")

    p_bt_portfolio = p_bt_sub.add_parser("portfolio", help="多股票组合回测")
    # 字段名 codes 与 cli_commands.cmd_backtest 中 getattr(args, "codes", ...) 对齐
    p_bt_portfolio.add_argument("codes", help="股票代码，逗号分隔")
    p_bt_portfolio.add_argument("--days", type=int, default=120, help="回测天数")
    p_bt_portfolio.add_argument("--mode", choices=["shaofu", "multi"], default="shaofu", help="回测模式")
    p_bt_portfolio.add_argument("--json", action="store_true", help="JSON输出")

    # ── trade（add / list / review / stats）──
    # 改为 subparser 模式：dest="trade_sub" 与 cli_commands.cmd_trade 里 getattr(args, "trade_sub", ...) 对齐
    p_trade = subparsers.add_parser("trade", help="交易记录管理")
    p_trade_sub = p_trade.add_subparsers(dest="trade_sub", required=True)

    p_trade_add = p_trade_sub.add_parser("add", help="添加交易记录")
    # 字段名 text 与 cli_commands.cmd_trade 中 getattr(args, "text", ...) 对齐
    p_trade_add.add_argument("text", help="交易描述（口语化）")
    p_trade_add.add_argument("--json", action="store_true", help="JSON输出")

    p_trade_list = p_trade_sub.add_parser("list", help="列出最近交易记录")
    p_trade_list.add_argument("--limit", type=int, default=20, help="列出条数")
    p_trade_list.add_argument("--json", action="store_true", help="JSON输出")

    p_trade_review = p_trade_sub.add_parser("review", help="构建复盘上下文（给 LLM）")
    p_trade_review.add_argument("--json", action="store_true", help="JSON输出")

    p_trade_stats = p_trade_sub.add_parser("stats", help="交易统计摘要")
    p_trade_stats.add_argument("--json", action="store_true", help="JSON输出")

    # ── daily ──
    p_daily = subparsers.add_parser("daily", help="每日五步工作流")
    p_daily.add_argument("--json", action="store_true", help="JSON输出")

    # ── monitor ──
    p_monitor = subparsers.add_parser("monitor", help="自选股主动预警与扫描推送")
    p_monitor.add_argument("--days", type=int, default=30, help="同步 K 线回溯天数")
    p_monitor.add_argument("--no-push", action="store_true", help="关闭推送通知")
    p_monitor.add_argument("--json", action="store_true", help="JSON输出")

    # ── simulate（少女/少妇模拟器 v0.2）──
    p_sim = subparsers.add_parser("simulate", help="端到端交易模拟回测（择时+选股+仓位+卖出）")
    p_sim.add_argument("codes", nargs="?", help="股票代码，逗号分隔；省略则使用前 500 只")
    p_sim.add_argument("--days", type=int, default=250, help="回测天数")
    p_sim.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    p_sim.add_argument("--max-positions", type=int, default=5, help="最大同时持仓")
    p_sim.add_argument("--risk", type=float, default=0.02, help="单笔风险占净值比例")
    p_sim.add_argument("--score", type=float, default=70.0, help="入选信号最低综合评分")
    p_sim.add_argument("--signals", type=int, default=2, help="最小共振标签数")
    p_sim.add_argument("--benchmark", type=str, default="000300.SH", help="基准指数代码")
    p_sim.add_argument(
        "--cost-model",
        choices=["simple", "advanced"],
        default="simple",
        help="成本模型：simple=仅佣金，advanced=含印花税/过户费",
    )
    p_sim.add_argument("--slippage", choices=["fixed", "dynamic"], default="fixed", help="滑点模型")
    p_sim.add_argument("--atr-sizing", action="store_true", help="启用 ATR 波动率仓位调整")
    p_sim.add_argument("--max-position-pct", type=float, default=0.20, help="单票最大仓位占比")
    p_sim.add_argument("--no-st", action="store_true", help="不允许交易 ST/*ST 股票")
    p_sim.add_argument("--t1-lock", dest="t1_lock", action="store_true", default=True, help="启用 T+1 卖出锁定（默认）")
    p_sim.add_argument("--no-t1-lock", dest="t1_lock", action="store_false", default=True, help="禁用 T+1 卖出锁定")
    # v0.3 新增：战法共振模式参数
    p_sim.add_argument("--strategy-mode", choices=["simple", "resonance"], default="simple", help="选股模式")
    p_sim.add_argument("--strategy-lookback", type=int, default=5, help="战法信号回看交易日数")
    p_sim.add_argument("--min-resonance-score", type=float, default=0.35, help="共振模式最低入选分")
    p_sim.add_argument("--json", action="store_true", help="JSON输出")

    return parser


def main():
    """zt CLI 主入口"""
    parser = build_parser()
    args = parser.parse_args()

    # 调度表
    from modules.cli_commands import cmd_backtest, cmd_trade, cmd_daily, cmd_monitor, cmd_simulate

    handlers = {
        "analyze": cmd_analyze,
        "screen": cmd_screen,
        "score": cmd_score,
        "workflow": cmd_workflow,
        "diagnose": cmd_diagnose,
        "watchlist": cmd_watchlist,
        "sync": cmd_sync,
        "backtest": cmd_backtest,
        "trade": cmd_trade,
        "daily": cmd_daily,
        "track": cmd_track,
        "self-optimize": cmd_self_optimize,
        "monitor": cmd_monitor,
        "simulate": cmd_simulate,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    # 取消代理，避免 Tushare 连接问题（仅脚本直调时，不影响库导入）
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""
    main()
