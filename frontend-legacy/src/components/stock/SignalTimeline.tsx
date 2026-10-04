import type { StrategySignal } from '../../api/types';
import { SIGNAL_COLORS } from '../../lib/constants';

interface Props {
  signals: StrategySignal[];
}

export default function SignalTimeline({ signals }: Props) {
  if (!signals || signals.length === 0) {
    return <div className="text-sm text-text-muted text-center py-8">暂无信号</div>;
  }

  // 按日期分组
  const groupedSignals: Record<string, StrategySignal[]> = {};
  signals.forEach((sig) => {
    if (!groupedSignals[sig.date]) {
      groupedSignals[sig.date] = [];
    }
    groupedSignals[sig.date].push(sig);
  });

  const sortedDates = Object.keys(groupedSignals).sort((a, b) => b.localeCompare(a));

  return (
    <div className="space-y-2.5 max-h-[600px] overflow-y-auto pr-1">
      {sortedDates.map((date) => {
        const daySignals = groupedSignals[date];
        const hasCritical = daySignals.some((s) => s.priority === 'CRITICAL');
        const hasOpportunity = daySignals.some((s) => s.priority === 'OPPORTUNITY');
        const borderColor = hasCritical ? '#ef4444' : hasOpportunity ? '#22c55e' : '#64748b';

        return (
          <div key={date} className="rounded-lg bg-bg-hover/20 border-l-[3px] overflow-hidden" style={{ borderLeftColor: borderColor }}>
            {/* 日期标题 */}
            <div className="px-3 py-1.5 bg-bg-hover/40 border-b border-border/20">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-text-muted font-medium">{date}</span>
                <span className="text-[10px] text-text-secondary bg-bg-card px-2 py-0.5 rounded-full">{daySignals.length} 个信号</span>
              </div>
            </div>

            {/* 信号列表 */}
            <div className="p-3 space-y-2.5">
              {daySignals.map((sig, i) => {
                const color = SIGNAL_COLORS[sig.strategy] || SIGNAL_COLORS[sig.action] || '#64748b';
                const priorityColor = sig.priority === 'CRITICAL' ? '#ef4444' : sig.priority === 'OPPORTUNITY' ? '#22c55e' : '#64748b';

                return (
                  <div key={i} className="flex items-start gap-3">
                    {/* 信号类型 */}
                    <div
                      className="flex-shrink-0 w-16 text-center py-1.5 rounded-md text-xs font-bold"
                      style={{ backgroundColor: `${color}15`, color }}
                    >
                      {sig.strategy}
                    </div>

                    {/* 详情 */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] px-1.5 py-0.5 rounded font-bold" style={{ backgroundColor: `${priorityColor}15`, color: priorityColor }}>
                          {sig.priority}
                        </span>
                        <span className="text-xs text-text-secondary font-medium">{sig.action}</span>
                      </div>
                      <div className="text-xs text-text-secondary leading-relaxed">{sig.description}</div>
                      {sig.target_price && (
                        <div className="text-xs text-text-muted mt-1 font-mono">
                          目标: {sig.target_price.toFixed(2)}
                          {sig.stop_loss && ` | 止损: ${sig.stop_loss.toFixed(2)}`}
                        </div>
                      )}
                    </div>

                    {/* 置信度 */}
                    <div className="flex-shrink-0 text-xs font-bold text-text-muted tabular-nums">
                      {(sig.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
