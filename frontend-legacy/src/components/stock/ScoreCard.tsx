import type { ScoreDetail } from '../../api/types';
import { formatNumber } from '../../lib/formatters';

interface Props {
  score: ScoreDetail;
}

export default function ScoreCard({ score }: Props) {
  const ratingColor = score.total >= 80 ? '#22c55e' : score.total >= 65 ? '#3b82f6' : score.total >= 50 ? '#f59e0b' : score.total >= 35 ? '#f97316' : '#ef4444';

  const scoreItems = [
    { label: 'B1', value: score.b1_score, color: '#22c55e' },
    { label: '趋势', value: score.trend_score, color: '#3b82f6' },
    { label: '量价', value: score.volume_score, color: '#f59e0b' },
    { label: '风险', value: score.risk_score, color: '#ef4444' },
  ];

  return (
    <div className="space-y-4">
      {/* 总分 */}
      <div className="text-center">
        <div className="text-5xl font-black tabular-nums" style={{ color: ratingColor }}>
          {formatNumber(score.total, 1)}
        </div>
        <div className="text-xs text-text-muted mt-1 font-medium">{score.rating}</div>
      </div>

      {/* 分项评分 */}
      <div className="space-y-2.5">
        {scoreItems.map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <span className="text-xs text-text-muted w-8 font-medium">{item.label}</span>
            <div className="flex-1 h-2 rounded-full bg-bg-hover overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{ width: `${item.value}%`, backgroundColor: item.color }}
              />
            </div>
            <span className="text-xs font-mono tabular-nums w-8 text-right font-bold" style={{ color: item.color }}>
              {formatNumber(item.value, 0)}
            </span>
          </div>
        ))}
      </div>

      {/* 理由 */}
      {score.reasons.length > 0 && (
        <div className="pt-3 border-t border-border/40">
          <div className="text-[10px] text-text-muted mb-2 font-semibold uppercase tracking-wider">理由</div>
          <ul className="space-y-1">
            {score.reasons.map((r, i) => (
              <li key={i} className="text-xs text-accent-green leading-relaxed flex items-start gap-1.5">
                <span className="text-accent-green/60 mt-0.5">+</span> {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 警告 */}
      {score.warnings.length > 0 && (
        <div className="pt-2 border-t border-border/40">
          <div className="text-[10px] text-text-muted mb-2 font-semibold uppercase tracking-wider">警告</div>
          <ul className="space-y-1">
            {score.warnings.map((w, i) => (
              <li key={i} className="text-xs text-accent-red leading-relaxed flex items-start gap-1.5">
                <span className="text-accent-red/60 mt-0.5">!</span> {w}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
