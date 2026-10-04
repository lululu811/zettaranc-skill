import type { DiagnosisSummary } from '../../api/types';
import { riskColor } from '../../lib/formatters';

interface Props {
  diagnosis: DiagnosisSummary;
}

function DiagnosisRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-bg-hover/30 transition-colors">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs font-medium" style={{ color: color || 'var(--color-text-primary)' }}>
        {value}
      </span>
    </div>
  );
}

export default function DiagnosisCard({ diagnosis }: Props) {
  return (
    <div className="space-y-1 text-xs">
      {/* 风险等级 */}
      <div className="flex items-center justify-between pb-3 border-b border-border/40">
        <span className="text-text-muted font-semibold uppercase tracking-wider text-[10px]">风险等级</span>
        <span className="font-bold px-3 py-1 rounded-full text-xs" style={{ backgroundColor: `${riskColor(diagnosis.risk_level)}15`, color: riskColor(diagnosis.risk_level) }}>
          {diagnosis.risk_level}
        </span>
      </div>

      {/* 价格位置 */}
      <DiagnosisRow label="价格位置" value={diagnosis.price_position || '--'} />

      {/* 趋势状态 */}
      <DiagnosisRow label="趋势状态" value={diagnosis.trend_status || '--'} />

      {/* 防卖飞评分 */}
      <DiagnosisRow
        label="防卖飞"
        value={`${diagnosis.sell_score}/5 ${diagnosis.sell_score_desc}`}
        color={diagnosis.sell_score >= 3 ? '#ef4444' : diagnosis.sell_score >= 2 ? '#f59e0b' : '#22c55e'}
      />

      {/* 麒麟会 */}
      <DiagnosisRow label="麒麟会" value={diagnosis.kirin_phase || '--'} />

      {/* 牛绳 */}
      <DiagnosisRow label="牛绳" value={diagnosis.bull_rope || '--'} />

      {/* 蜈蚣图 */}
      {diagnosis.is_centipede && (
        <DiagnosisRow label="蜈蚣图" value="是" color="#ef4444" />
      )}

      {/* 操作建议 */}
      <div className="pt-3 mt-2 border-t border-border/40">
        <div className="text-text-muted font-semibold uppercase tracking-wider text-[10px] mb-2">操作建议</div>
        <div className="text-text-primary leading-relaxed bg-bg-hover/20 p-3 rounded-lg text-xs">{diagnosis.recommendation || '--'}</div>
      </div>
    </div>
  );
}
