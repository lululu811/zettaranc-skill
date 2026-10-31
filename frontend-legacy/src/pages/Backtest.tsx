import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { runShaofu } from '../api/backtest';
import type { BacktestResult } from '../api/types';
import Card from '../components/ui/Card';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import EquityCurveChart from '../components/charts/EquityCurveChart';
import { formatNumber, formatPct } from '../lib/formatters';

export default function Backtest() {
  const [tsCode, setTsCode] = useState('');
  const [days, setDays] = useState(250);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const mutation = useMutation({
    mutationFn: () => runShaofu({ ts_code: tsCode, days }),
    onSuccess: (data) => setResult(data),
  });

  const handleRun = () => {
    if (!tsCode.trim()) return;
    let code = tsCode.trim().toUpperCase();
    if (/^\d{6}$/.test(code)) {
      code = code.startsWith('6') ? `${code}.SH` : `${code}.SZ`;
    }
    setTsCode(code);
    mutation.mutate();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">策略回测</h1>

      {/* Config */}
      <Card title="回测配置">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="block text-xs text-text-muted mb-1">股票代码</label>
            <input
              type="text"
              value={tsCode}
              onChange={(e) => setTsCode(e.target.value)}
              placeholder="如 600487.SH"
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold"
            />
          </div>
          <div className="w-32">
            <label className="block text-xs text-text-muted mb-1">回测天数</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-full rounded border border-border bg-bg-primary px-2 py-1.5 text-sm text-text-primary"
            >
              {[120, 250, 365, 500, 730].map((n) => (
                <option key={n} value={n}>{n} 天</option>
              ))}
            </select>
          </div>
          <div className="flex items-end gap-3">
            <button
              onClick={handleRun}
              disabled={mutation.isPending || !tsCode.trim()}
              className="rounded-lg border border-accent-gold/40 bg-gradient-to-b from-accent-gold/30 to-accent-gold/15 px-5 py-2 text-sm font-bold tracking-wider text-accent-gold shadow-[0_0_20px_-8px_rgba(245,158,11,0.5)] transition-all hover:from-accent-gold/40 hover:to-accent-gold/25 hover:shadow-[0_0_24px_-6px_rgba(245,158,11,0.7)] disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              {mutation.isPending ? '回测中...' : '▶ 开始回测'}
            </button>
          </div>
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
          <div className="grid grid-cols-6 gap-3">
            {[
              { label: '总收益', value: formatPct(result.summary.total_return), color: result.summary.total_return >= 0 ? '#ef4444' : '#22c55e' },
              { label: '胜率', value: `${(result.summary.win_rate * 100).toFixed(1)}%`, color: '#f59e0b' },
              { label: '盈亏比', value: formatNumber(result.summary.profit_factor), color: '#3b82f6' },
              { label: '最大回撤', value: formatPct(-Math.abs(result.summary.max_drawdown)), color: '#ef4444' },
              { label: '夏普比率', value: formatNumber(result.summary.sharpe_ratio), color: '#a855f7' },
              { label: '交易次数', value: String(result.summary.total_trades), color: '#06b6d4' },
            ].map((item) => (
              <Card key={item.label}>
                <div className="text-center">
                  <div className="text-xs text-text-muted">{item.label}</div>
                  <div className="text-lg font-bold mt-1" style={{ color: item.color }}>{item.value}</div>
                </div>
              </Card>
            ))}
          </div>

          {/* Equity Curve */}
          <Card title="资金曲线">
            <EquityCurveChart equityCurve={result.equity_curve} height={300} />
          </Card>

          {/* Trade Table */}
          <Card title={`交易明细 (${result.trades.length} 笔)`}>
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-bg-card">
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-1.5 px-2">买入日期</th>
                    <th className="text-right py-1.5 px-2">买入价</th>
                    <th className="text-left py-1.5 px-2">卖出日期</th>
                    <th className="text-right py-1.5 px-2">卖出价</th>
                    <th className="text-right py-1.5 px-2">盈亏</th>
                    <th className="text-right py-1.5 px-2">持仓天数</th>
                    <th className="text-left py-1.5 px-2">退出原因</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-b border-border/50">
                      <td className="py-1.5 px-2 text-text-secondary">{t.entry_date}</td>
                      <td className="py-1.5 px-2 text-right font-mono">{formatNumber(t.entry_price)}</td>
                      <td className="py-1.5 px-2 text-text-secondary">{t.exit_date || '--'}</td>
                      <td className="py-1.5 px-2 text-right font-mono">{t.exit_price ? formatNumber(t.exit_price) : '--'}</td>
                      <td className={`py-1.5 px-2 text-right font-mono font-bold ${t.pnl_pct >= 0 ? 'text-up' : 'text-down'}`}>
                        {formatPct(t.pnl_pct)}
                      </td>
                      <td className="py-1.5 px-2 text-right">{t.holding_days}</td>
                      <td className="py-1.5 px-2 text-text-muted">{t.exit_reason}</td>
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
