import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { fetchStrategies, runScreen } from '../api/screen';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ApiErrorState from '../components/ui/ApiErrorState';
import { STRATEGIES } from '../lib/constants';
import { formatNumber } from '../lib/formatters';
import { useAppStore } from '../stores/appStore';

export default function Screener() {
  const navigate = useNavigate();
  const setScreenResults = useAppStore((s) => s.setScreenResults);
  // 上次筛选快照：刷新/返回后用它还原条件与结果，不再空白
  const snapshot = useAppStore((s) => s.screenSnapshot);
  const setScreenSnapshot = useAppStore((s) => s.setScreenSnapshot);
  const clearScreenSnapshot = useAppStore((s) => s.clearScreenSnapshot);

  // 初始值直接取自快照，回到本页时条件与原结果一起恢复
  const [selected, setSelected] = useState(snapshot?.strategy ?? 'B1');
  const [limit, setLimit] = useState(snapshot?.limit ?? 100); // 扫描数量（0=全市场）
  const [top, setTop] = useState(snapshot?.top ?? 0); // 返回条数（0=全部命中）
  const [ran, setRan] = useState(!!snapshot);
  // 参数覆盖按「策略别名」分组存储，默认值由后端下发，避免 effect 内 setState
  const [overrides, setOverrides] = useState<Record<string, Record<string, number>>>(
    snapshot?.overrides ?? {},
  );

  // 策略参数定义（含默认值/取值范围）来自后端 param_registry，避免前端重复维护
  const { data: strategies } = useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    staleTime: 30 * 60 * 1000,
  });

  const currentParams = useMemo(
    () => strategies?.find((s) => s.alias === selected)?.params ?? [],
    [strategies, selected],
  );

  // 当前策略生效的参数 = 默认值 + 用户覆盖
  const paramValues = useMemo(
    () => ({
      ...Object.fromEntries(currentParams.map((p) => [p.name, Number(p.default)])),
      ...(overrides[selected] ?? {}),
    }),
    [currentParams, overrides, selected],
  );

  const setParam = (name: string, value: number) =>
    setOverrides((prev) => ({ ...prev, [selected]: { ...(prev[selected] ?? {}), [name]: value } }));

  const resetParams = () => setOverrides((prev) => ({ ...prev, [selected]: {} }));

  // 条件指纹：只用「用户可见条件」而非含后端默认值的 paramValues，
  // 避免策略定义加载完成前后指纹变化导致快照误判失效
  const condKey = JSON.stringify([selected, limit, top, overrides[selected] ?? {}]);

  const { data: result, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['screen', selected, limit, top, paramValues],
    queryFn: () => runScreen(selected, limit, paramValues, top),
    enabled: false,
  });

  const handleRun = async () => {
    setRan(true);
    const { data } = await refetch();
    if (data) {
      setScreenSnapshot({
        key: condKey,
        strategy: selected,
        limit,
        top,
        overrides,
        result: data,
        ranAt: Date.now(),
      });
    }
  };

  // 展示优先级：本次查询结果 > 与当前条件一致的快照
  const shown = result ?? (snapshot && snapshot.key === condKey ? snapshot.result : null);
  // 条件被改动过、但还没重新跑
  const stale = !result && !!snapshot && snapshot.key !== condKey;
  const ranAtText = snapshot
    ? new Date(snapshot.ranAt).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '';

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
        {/* 策略参数（选中策略后展示，默认值为 param_registry 出厂值） */}
        {currentParams.length > 0 && (
          <div className="mb-4 rounded-xl border border-border bg-white/60 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-text-secondary">策略参数</span>
              <button
                type="button"
                onClick={resetParams}
                className="text-xs text-text-muted hover:text-brand-from transition-colors"
              >
                恢复默认
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {currentParams.map((p) => (
                <label key={p.name} className="flex items-center gap-2">
                  <span className="w-28 shrink-0 text-xs text-text-secondary font-mono" title={p.description}>
                    {p.name}
                  </span>
                  <input
                    type="number"
                    value={paramValues[p.name] ?? Number(p.default)}
                    min={p.min}
                    max={p.max}
                    step={p.step}
                    onChange={(e) => setParam(p.name, Number(e.target.value))}
                    className="w-24 rounded border border-border bg-white/80 px-2 py-1 text-sm text-text-primary outline-none focus:border-brand-from focus:ring-2 focus:ring-brand-from/20"
                  />
                  <span className="text-[10px] text-text-muted truncate" title={p.description}>
                    {p.description}
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted" title="从股票池（按代码排序）取前 N 只来跑形态判定；全市场约 5200 只，实测秒级">
              扫描数量
            </span>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded border border-border bg-white/80 px-2 py-1 text-sm text-text-primary"
            >
              {[50, 100, 200, 500, 1000, 2000].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
              <option value={0}>全市场</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted" title="展示多少条命中结果，不影响扫描范围">
              返回条数
            </span>
            <select
              value={top}
              onChange={(e) => setTop(Number(e.target.value))}
              className="rounded border border-border bg-white/80 px-2 py-1 text-sm text-text-primary"
            >
              {[10, 20, 50, 0].map((n) => (
                <option key={n} value={n}>{n === 0 ? '全部' : n}</option>
              ))}
            </select>
          </div>
          <Button onClick={handleRun} disabled={isLoading}>
            {isLoading ? '筛选中...' : shown ? '重新筛选' : '开始筛选'}
          </Button>
          {snapshot && (
            <button
              type="button"
              onClick={() => {
                clearScreenSnapshot();
                setRan(false);
              }}
              className="text-xs text-text-muted hover:text-brand-from transition-colors"
              title="清除已保存的上次结果"
            >
              清除结果
            </button>
          )}
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

      {/* 还没结果时：未跑过显示引导，条件改过显示「已变更」 */}
      {!isLoading && !shown && !isError && (
        <Card>
          {stale ? (
            <div className="flex flex-col items-center text-center py-8">
              <div className="text-3xl mb-3 text-accent-gold opacity-60">↻</div>
              <div className="text-sm font-bold text-text-primary mb-1">筛选条件已变更</div>
              <div className="text-xs text-text-muted max-w-md mb-3">
                当前条件与已保存的结果不一致，点击「重新筛选」更新列表。
              </div>
              <Button onClick={handleRun}>重新筛选</Button>
            </div>
          ) : (
            <div className="flex flex-col items-center text-center py-8">
              <div className="text-3xl mb-3 text-accent-gold opacity-60">◎</div>
              <div className="text-sm font-bold text-text-primary mb-1">选择战法开始筛选</div>
              <div className="text-xs text-text-muted max-w-md">在上方选择战法(如 B1 / B2 / 长安战法 等),设定数量后点击"开始筛选",系统会扫描全市场命中该战法的个股。</div>
            </div>
          )}
        </Card>
      )}

      {shown && !isLoading && (
        <Card
          title={`筛选结果 — ${shown.strategy}（命中 ${shown.matched} 只 / 扫描 ${shown.scanned} 只，展示 ${shown.count} 只${!result && snapshot ? ` · 保存于 ${ranAtText}` : ''}）`}
          action={
            <Button onClick={handleRun} disabled={isLoading}>
              {isLoading ? '筛选中...' : '重新筛选'}
            </Button>
          }
        >
          {shown.stocks.length === 0 ? (
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
                  {shown.stocks.map((s) => (
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
                          onClick={() => {
                            // 把本次选股结果带到详情页，左侧以列表形式逐个查看
                            setScreenResults(
                              (shown?.stocks || []).map((x) => ({
                                ts_code: x.ts_code,
                                name: x.name,
                                score: x.score,
                                rating: x.rating,
                              })),
                            );
                            navigate(`/stock/${s.ts_code}`);
                          }}
                          className="text-xs text-brand-from hover:underline"
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
