import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ApiErrorState from '../components/ui/ApiErrorState';

export default function Settings() {
  const { data: health, isLoading: loadingHealth, isError: healthError, error: healthErr, refetch: refetchHealth } = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data } = await api.get('/system/health');
      return data;
    },
  });

  const { data: syncStatus, isLoading: loadingSync, isError: syncError, error: syncErr, refetch: refetchSync } = useQuery({
    queryKey: ['sync-status'],
    queryFn: async () => {
      const { data } = await api.get('/system/sync/status');
      return data;
    },
  });

  if (loadingHealth || loadingSync) {
    return <div className="flex items-center justify-center h-96"><LoadingSpinner size="lg" /></div>;
  }

  if (healthError || syncError) {
    const err = (healthErr || syncErr) as Error | null;
    return (
      <ApiErrorState
        message={err?.message || '加载系统状态失败'}
        onRetry={() => { refetchHealth(); refetchSync(); }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">系统设置</h1>

      {/* System Info */}
      <Card title="系统状态">
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-text-muted">状态</span>
            <Badge variant="success">{health?.status || 'unknown'}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">数据模式</span>
            <span className="text-text-primary">{health?.data_mode || '--'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">数据库</span>
            <Badge variant={health?.db_exists ? 'success' : 'danger'}>
              {health?.db_exists ? '已连接' : '未找到'}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">API 版本</span>
            <span className="text-text-primary">{health?.version || '--'}</span>
          </div>
        </div>
      </Card>

      {/* Sync Status */}
      <Card title="数据同步记录">
        {!syncStatus || syncStatus.logs.length === 0 ? (
          <div className="text-center py-8 text-text-muted">暂无同步记录</div>
        ) : (
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-bg-card">
                <tr className="border-b border-border text-text-muted">
                  <th className="text-left py-1.5 px-2">类型</th>
                  <th className="text-left py-1.5 px-2">代码</th>
                  <th className="text-left py-1.5 px-2">最后日期</th>
                  <th className="text-left py-1.5 px-2">状态</th>
                  <th className="text-left py-1.5 px-2">消息</th>
                </tr>
              </thead>
              <tbody>
                {syncStatus.logs.map((log: Record<string, string>, i: number) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-1.5 px-2 text-text-secondary">{log.data_type}</td>
                    <td className="py-1.5 px-2 font-mono text-accent-gold">{log.ts_code || '--'}</td>
                    <td className="py-1.5 px-2 text-text-secondary">{log.last_date || '--'}</td>
                    <td className="py-1.5 px-2">
                      <Badge variant={log.status === 'success' ? 'success' : 'danger'}>
                        {log.status}
                      </Badge>
                    </td>
                    <td className="py-1.5 px-2 text-text-muted max-w-64 truncate">{log.message || '--'}</td>
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
