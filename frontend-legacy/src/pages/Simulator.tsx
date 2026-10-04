import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { runSimulation } from '../api/simulator';
import type { SimulationRequest, SimulationResponse } from '../api/types';
import Card from '../components/ui/Card';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import SimulatorEquityCurveChart from '../components/charts/SimulatorEquityCurveChart';
import { formatNumber, formatPct } from '../lib/formatters';

const DAY_OPTIONS = [120, 250, 365, 500, 730];

function parseTsCodes(input: string): string[] {
  if (!input.trim()) return [];
  return input
    .split(/[,，\s]+/)
    .map((c) => c.trim())
    .filter(Boolean)
    .map((c) => {
      if (/^\d{6}$/.test(c)) {
        return c.startsWith('6') ? `${c}.SH` : `${c}.SZ`;
      }
      return c.toUpperCase();
    });
}

export default function Simulator() {
  const [tsCodesInput, setTsCodesInput] = useState('');
  const [days, setDays] = useState(250);
  const [capital, setCapital] = useState(1_000_000);
  const [strategyMode, setStrategyMode] = useState<'simple' | 'resonance'>('simple');
  const [atrSizing, setAtrSizing] = useState(false);
  const [result, setResult] = useState<SimulationResponse | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const params: SimulationRequest = {
        ts_codes: parseTsCodes(tsCodesInput),
        days,
        capital,
        max_positions: 5,
        risk_per_trade: 0.02,
        min_score: 60,
        min_signals: 2,
        atr_sizing: atrSizing,
        max_position_pct: 0.15,
        benchmark: '000300.SH',
        cost_model: 'realistic',
        slippage: 'dynamic',
        no_st: false,
        strategy_mode: strategyMode,
        strategy_lookback: 5,
        min_resonance_score: 50,
        walk_forward: false,
        wf_train_days: 120,
        wf_test_days: 60,
        wf_objective: 'calmar',
      };
      return runSimulation(params);
    },
    onSuccess: (data) => setResult(data),
  });

  const handleRun = () => {
    mutation.mutate();
  };

  const metrics = result?.metrics;
  const summary = result?.summary as Record<string, number> | undefined;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">端到端模拟</h1>

      {/* Config */}
      <Card title="模拟配置">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <label className="block text-xs text-text-muted mb-1">股票代码（逗号/空格分隔，留空=全市场）</label>
            <input
              type="text"
              value={tsCodesInput}
              onChange={(e) => setTsCodesInput(e.target.value)}
              placeholder="如 000001.SZ, 600487.SH"
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold"
            />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">回测天数</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-full rounded border border-border bg-bg-primary px-2 py-1.5 text-sm text-text-primary"
            >
              {DAY_OPTIONS.map((n) => (
                <option key={n} value={n}>{n} 天</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">初始资金</label>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              min={10000}
              step={100000}
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent-gold"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-muted">策略模式</span>
            <div className="flex rounded border border-border overflow-hidden">
              <button
                type="button"
                onClick={() => setStrategyMode('simple')}
                className={`px-3 py-1.5 text-xs ${strategyMode === 'simple'
                  ? 'bg-accent-gold/20 text-accent-gold'
                  : 'bg-bg-primary text-text-secondary hover:text-text-primary'
                  }`}
              >
                简单
              </button>
              <button
                type="button"
                onClick={() => setStrategyMode('resonance')}
                className={`px-3 py-1.5 text-xs ${strategyMode === 'resonance'
                  ? 'bg-accent-gold/20 text-accent-gold'
                  : 'bg-bg-primary text-text-secondary hover:text-text-primary'
                  }`}
              >
                战法共振
              </button>
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={atrSizing}
              onChange={(e) => setAtrSizing(e.target.checked)}
              className="h-4 w-4 accent-accent-gold"
            />
            <span className="text-xs text-text-secondary">ATR 动态仓位</span>
          </label>

          <div className="flex-1" />

          <button
            onClick={handleRun}
            disabled={mutation.isPending}
            className="rounded-lg border border-accent-gold/40 bg-gradient-to-b from-accent-gold/30 to-accent-gold/15 px-5 py-2 text-sm font-bold tracking-wider text-accent-gold shadow-[0_0_20px_-8px_rgba(245,158,11,0.5)] transition-all hover:from-accent-gold/40 hover:to-accent-gold/25 hover:shadow-[0_0_24px_-6px_rgba(245,158,11,0.7)] disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {mutation.isPending ? '模拟中...' : '▶ 开始模拟'}
          </button>
        </div>
      </Card>

      {/* Loading */}
      {mutation.isPending && (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      )}

      {/* Results */}
      {result && !mutation.isPending && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-3 gap-3 md:grid-cols-6">
            {[
              {
                label: '年化收益',
                value: formatPct(((metrics?.annualized_return ?? 0) as number) * 100),
                color: (metrics?.annualized_return ?? 0) >= 0 ? '#ef4444' : '#22c55e',
              },
              {
                label: '夏普比率',
                value: formatNumber(metrics?.sharpe_ratio ?? 0),
                color: '#3b82f6',
              },
              {
                label: 'Calmar',
                value: formatNumber(metrics?.calmar_ratio ?? 0),
                color: '#a855f7',
              },
              {
                label: '最大回撤',
                value: formatPct(-Math.abs((metrics?.max_drawdown ?? 0) as number) * 100),
                color: '#ef4444',
              },
              {
                label: '胜率',
                value: formatPct(((metrics?.win_rate ?? 0) as number) * 100),
                color: '#f59e0b',
              },
              {
                label: '总交易数',
                value: String(summary?.total_trades ?? 0),
                color: '#06b6d4',
              },
            ].map((item) => (
              <Card key={item.label}>
                <div className="text-center">
                  <div className="text-xs text-text-muted">{item.label}</div>
                  <div
                    className="text-lg font-bold mt-1"
                    style={{ color: item.color }}
                  >
                    {item.value}
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {/* Equity Curve */}
          <Card title="资金曲线 / 回撤">
            <SimulatorEquityCurveChart
              equityCurve={result.equity_curve}
              benchmarkCurve={result.benchmark_curve}
              height={360}
            />
          </Card>

          {/* Trade Table */}
          <Card title={`交易明细 (${result.trades.length} 笔)`}>
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-bg-card">
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-1.5 px-2">日期</th>
                    <th className="text-left py-1.5 px-2">代码</th>
                    <th className="text-left py-1.5 px-2">操作</th>
                    <th className="text-right py-1.5 px-2">价格</th>
                    <th className="text-right py-1.5 px-2">股数</th>
                    <th className="text-right py-1.5 px-2">盈亏</th>
                    <th className="text-right py-1.5 px-2">手续费</th>
                    <th className="text-left py-1.5 px-2">原因</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-b border-border/50">
                      <td className="py-1.5 px-2 text-text-secondary">{t.date}</td>
                      <td className="py-1.5 px-2 text-text-secondary">{t.ts_code}</td>
                      <td
                        className={`py-1.5 px-2 font-bold ${t.action === 'BUY'
                          ? 'text-up'
                          : t.action === 'SELL' || t.action === 'PARTIAL_SELL'
                            ? 'text-down'
                            : 'text-text-secondary'
                          }`}
                      >
                        {t.action}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">{formatNumber(t.price, 3)}</td>
                      <td className="py-1.5 px-2 text-right font-mono">{t.shares}</td>
                      <td
                        className={`py-1.5 px-2 text-right font-mono font-bold ${(t.pnl ?? 0) >= 0 ? 'text-up' : 'text-down'}`}
                      >
                        {t.pnl != null ? formatPct(t.pnl_pct ?? 0) : '--'}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">{formatNumber(t.fee)}</td>
                      <td className="py-1.5 px-2 text-text-muted">{t.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
