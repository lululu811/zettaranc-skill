import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTrades, addTrade, deleteTrade, fetchTradeStats } from '../api/trade';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatNumber } from '../lib/formatters';

export default function Trades() {
  const queryClient = useQueryClient();
  const [inputText, setInputText] = useState('');
  const [page, setPage] = useState(1);

  const { data: tradeList, isLoading } = useQuery({
    queryKey: ['trades', page],
    queryFn: () => fetchTrades(page),
  });

  const { data: stats } = useQuery({
    queryKey: ['trade-stats'],
    queryFn: fetchTradeStats,
  });

  const addMutation = useMutation({
    mutationFn: (text: string) => addTrade(text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trades'] });
      queryClient.invalidateQueries({ queryKey: ['trade-stats'] });
      setInputText('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTrade,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['trades'] }),
  });

  if (isLoading) {
    return <div className="flex items-center justify-center h-96"><LoadingSpinner size="lg" /></div>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">交易记录</h1>

      {/* Input */}
      <Card title="记录交易">
        <div className="flex gap-3">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="口语化输入，如：4月25号买了100股茅台，1800块"
            className="flex-1 rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && inputText.trim()) {
                addMutation.mutate(inputText);
              }
            }}
          />
          <Button
            onClick={() => addMutation.mutate(inputText)}
            disabled={!inputText.trim() || addMutation.isPending}
          >
            保存
          </Button>
        </div>
        {addMutation.isSuccess && (
          <div className="mt-2 text-xs text-accent-green">保存成功</div>
        )}
        {addMutation.isError && (
          <div className="mt-2 text-xs text-accent-red">保存失败</div>
        )}
      </Card>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-3">
          <Card>
            <div className="text-xs text-text-muted">买入总额</div>
            <div className="text-lg font-bold text-text-primary mt-1">
              {formatNumber((stats.pnl as Record<string, number>)?.buy_total || 0)}
            </div>
          </Card>
          <Card>
            <div className="text-xs text-text-muted">卖出总额</div>
            <div className="text-lg font-bold text-text-primary mt-1">
              {formatNumber((stats.pnl as Record<string, number>)?.sell_total || 0)}
            </div>
          </Card>
          <Card>
            <div className="text-xs text-text-muted">当前持仓</div>
            <div className="text-lg font-bold text-accent-gold mt-1">
              {(stats.pnl as Record<string, number>)?.current_qty || 0} 股
            </div>
          </Card>
          <Card>
            <div className="text-xs text-text-muted">已实现盈亏</div>
            {(() => {
              const pnl = (stats.pnl as Record<string, number>)?.realized_pnl || 0;
              const hasTrades = ((stats.pnl as Record<string, number>)?.buy_total || 0) > 0
                || ((stats.pnl as Record<string, number>)?.sell_total || 0) > 0;
              const tone = !hasTrades
                ? 'text-text-muted'
                : pnl > 0
                  ? 'text-up'
                  : pnl < 0
                    ? 'text-down'
                    : 'text-text-primary';
              return (
                <div className={`text-lg font-bold mt-1 ${tone}`}>
                  {formatNumber(pnl)}
                </div>
              );
            })()}
          </Card>
        </div>
      )}

      {/* Trade List */}
      <Card title={`交易记录 (${tradeList?.total || 0})`}>
        {!tradeList || tradeList.records.length === 0 ? (
          <div className="text-center py-8 text-text-muted">暂无交易记录</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-2 px-2">日期</th>
                    <th className="text-left py-2 px-2">代码</th>
                    <th className="text-left py-2 px-2">方向</th>
                    <th className="text-right py-2 px-2">价格</th>
                    <th className="text-right py-2 px-2">数量</th>
                    <th className="text-right py-2 px-2">金额</th>
                    <th className="text-left py-2 px-2">原因</th>
                    <th className="text-right py-2 px-2">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {tradeList.records.map((r) => (
                    <tr key={r.id} className="border-b border-border/50 hover:bg-bg-hover/50">
                      <td className="py-2 px-2 text-text-secondary">{r.trade_date}</td>
                      <td className="py-2 px-2 font-mono text-accent-gold">{r.ts_code}</td>
                      <td className="py-2 px-2">
                        <Badge variant={r.action === 'BUY' ? 'success' : 'danger'}>
                          {r.action === 'BUY' ? '买入' : '卖出'}
                        </Badge>
                      </td>
                      <td className="py-2 px-2 text-right font-mono">{formatNumber(r.price)}</td>
                      <td className="py-2 px-2 text-right font-mono">{r.quantity}</td>
                      <td className="py-2 px-2 text-right font-mono">{formatNumber(r.amount)}</td>
                      <td className="py-2 px-2 text-text-muted text-xs max-w-48 truncate">{r.reason}</td>
                      <td className="py-2 px-2 text-right">
                        <button
                          onClick={() => deleteMutation.mutate(r.id)}
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
            {/* Pagination */}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
              <span className="text-xs text-text-muted">
                第 {tradeList.page} 页 / 共 {tradeList.total} 条
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  上一页
                </Button>
                <Button size="sm" variant="ghost" disabled={page * tradeList.page_size >= tradeList.total} onClick={() => setPage(page + 1)}>
                  下一页
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
