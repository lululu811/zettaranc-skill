import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { fetchWatchlist, addToWatchlist, removeFromWatchlist, scanWatchlist } from '../api/watchlist';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ApiErrorState from '../components/ui/ApiErrorState';

export default function Watchlist() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [newCode, setNewCode] = useState('');
  const [newTags, setNewTags] = useState('');

  const { data: watchlist, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
  });

  const { data: scanResult, isLoading: scanning } = useQuery({
    queryKey: ['watchlist-scan'],
    queryFn: scanWatchlist,
    enabled: false,
  });

  const addMutation = useMutation({
    mutationFn: (code: string) => addToWatchlist(code, newTags),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setNewCode('');
      setNewTags('');
    },
  });

  const removeMutation = useMutation({
    mutationFn: removeFromWatchlist,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist'] }),
  });

  const handleScan = () => {
    queryClient.invalidateQueries({ queryKey: ['watchlist-scan'] });
  };

  if (isLoading) {
    return <div className="flex items-center justify-center h-96"><LoadingSpinner size="lg" /></div>;
  }

  if (isError) {
    return (
      <ApiErrorState
        message={(error as Error)?.message || '加载自选股失败'}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">自选股管理</h1>
        <Button onClick={handleScan} disabled={scanning}>
          {scanning ? '扫描中...' : '信号扫描'}
        </Button>
      </div>

      {/* Add */}
      <Card title="添加自选股">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
            placeholder="股票代码，如 600487.SH"
            className="min-w-0 flex-1 basis-48 rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold"
          />
          <input
            type="text"
            value={newTags}
            onChange={(e) => setNewTags(e.target.value)}
            placeholder="标签（逗号分隔）"
            className="w-48 rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold"
          />
          <Button onClick={() => addMutation.mutate(newCode)} disabled={!newCode.trim()} className="shrink-0">
            添加
          </Button>
        </div>
      </Card>

      {/* Scan Results */}
      {scanResult && scanResult.alerts.length > 0 && (
        <Card title={`扫描结果 — ${scanResult.total} 只，${scanResult.alerts.length} 个信号`}>
          <div className="space-y-2">
            {scanResult.alerts.map((a, i) => (
              <div key={i} className="flex items-center gap-3 p-2 rounded bg-bg-hover/50">
                <Badge variant={a.level === 'CRITICAL' ? 'danger' : a.level === 'WARNING' ? 'warning' : 'info'}>
                  {a.level}
                </Badge>
                <span className="text-xs font-mono text-accent-gold">{a.ts_code}</span>
                <span className="text-xs text-text-secondary">{a.alert_type}</span>
                <span className="text-xs text-text-muted flex-1">{a.message}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* List */}
      <Card title={`自选股列表 (${watchlist?.count || 0})`}>
        {!watchlist || watchlist.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-text-muted">
            <div className="text-2xl mb-2 opacity-60">☆</div>
            <div className="text-sm">暂无自选股</div>
            <div className="text-xs mt-1 text-text-muted/70">在上方输入股票代码即可加入观察池</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-muted">
                  <th className="text-left py-2 px-2">代码</th>
                  <th className="text-left py-2 px-2">名称</th>
                  <th className="text-left py-2 px-2">标签</th>
                  <th className="text-left py-2 px-2">添加日期</th>
                  <th className="text-right py-2 px-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.items.map((item) => (
                  <tr key={item.ts_code} className="border-b border-border/50 hover:bg-bg-hover/50">
                    <td className="py-2 px-2 font-mono text-accent-gold">{item.ts_code}</td>
                    <td className="py-2 px-2 text-text-primary">{item.name || '--'}</td>
                    <td className="py-2 px-2">
                      {item.tags ? item.tags.split(',').map((t, i) => (
                        <Badge key={i}>{t.trim()}</Badge>
                      )) : '--'}
                    </td>
                    <td className="py-2 px-2 text-text-muted text-xs">{item.added_date || '--'}</td>
                    <td className="py-2 px-2 text-right space-x-2">
                      <button
                        onClick={() => navigate(`/stock/${item.ts_code}`)}
                        className="text-xs text-accent-blue hover:underline"
                      >
                        分析
                      </button>
                      <button
                        onClick={() => removeMutation.mutate(item.ts_code)}
                        className="text-xs text-accent-red hover:underline"
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
