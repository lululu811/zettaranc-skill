import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { runScreen } from '../api/screen';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ApiErrorState from '../components/ui/ApiErrorState';
import { STRATEGIES } from '../lib/constants';
import { formatNumber } from '../lib/formatters';

export default function Screener() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState('B1');
  const [limit, setLimit] = useState(20);
  const [ran, setRan] = useState(false);

  const { data: result, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['screen', selected, limit],
    queryFn: () => runScreen(selected, limit),
    enabled: false,
  });

  const handleRun = async () => {
    setRan(true);
    await refetch();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">选股筛选</h1>
      </div>

      {/* Strategy Selector */}
      <Card>
        <div className="flex flex-wrap gap-2 mb-4">
          {STRATEGIES.map((s) => (
            <button
              key={s.alias}
              onClick={() => setSelected(s.alias)}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${
                selected === s.alias
                  ? 'bg-accent-gold/20 text-accent-gold border border-accent-gold/50'
                  : 'bg-bg-hover text-text-secondary border border-border hover:text-text-primary'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">数量</span>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded border border-border bg-bg-primary px-2 py-1 text-sm text-text-primary"
            >
              {[10, 20, 50, 100].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <Button onClick={handleRun} disabled={isLoading}>
            {isLoading ? '筛选中...' : '开始筛选'}
          </Button>
        </div>
      </Card>

      {/* Results */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      )}

      {ran && isError && !isLoading && (
        <ApiErrorState
          message={(error as Error)?.message || '筛选失败'}
          onRetry={() => refetch()}
        />
      )}

      {/* 初始引导:用户还没跑过筛选时显示 */}
      {!ran && !result && (
        <Card>
          <div className="flex flex-col items-center text-center py-8">
            <div className="text-3xl mb-3 text-accent-gold opacity-60">◎</div>
            <div className="text-sm font-bold text-text-primary mb-1">选择战法开始筛选</div>
            <div className="text-xs text-text-muted max-w-md">在上方选择战法(如 B1 / B2 / 长安战法 等),设定数量后点击"开始筛选",系统会扫描全市场命中该战法的个股。</div>
          </div>
        </Card>
      )}

      {ran && result && !isLoading && (
        <Card title={`筛选结果 — ${result.strategy} (${result.count} 只)`}>
          {result.stocks.length === 0 ? (
            <div className="text-center py-8 text-text-muted">无符合条件的股票</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-2 px-2">代码</th>
                    <th className="text-left py-2 px-2">名称</th>
                    <th className="text-right py-2 px-2">总分</th>
                    <th className="text-right py-2 px-2">B1</th>
                    <th className="text-right py-2 px-2">趋势</th>
                    <th className="text-right py-2 px-2">量价</th>
                    <th className="text-right py-2 px-2">风险</th>
                    <th className="text-left py-2 px-2">评级</th>
                    <th className="text-left py-2 px-2">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stocks.map((s) => (
                    <tr key={s.ts_code} className="border-b border-border/50 hover:bg-bg-hover/50">
                      <td className="py-2 px-2 font-mono text-accent-gold">{s.ts_code}</td>
                      <td className="py-2 px-2 text-text-primary">{s.name}</td>
                      <td className="py-2 px-2 text-right font-mono font-bold">{formatNumber(s.score, 1)}</td>
                      <td className="py-2 px-2 text-right font-mono">{formatNumber(s.b1_score, 1)}</td>
                      <td className="py-2 px-2 text-right font-mono">{formatNumber(s.trend_score, 1)}</td>
                      <td className="py-2 px-2 text-right font-mono">{formatNumber(s.volume_score, 1)}</td>
                      <td className="py-2 px-2 text-right font-mono">{formatNumber(s.risk_score, 1)}</td>
                      <td className="py-2 px-2 text-text-secondary">{s.rating}</td>
                      <td className="py-2 px-2">
                        <button
                          onClick={() => navigate(`/stock/${s.ts_code}`)}
                          className="text-xs text-accent-blue hover:underline"
                        >
                          分析
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
