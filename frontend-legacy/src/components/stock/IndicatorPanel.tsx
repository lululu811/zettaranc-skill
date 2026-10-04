import type { IndicatorDetail } from '../../api/types';
import { formatNumber } from '../../lib/formatters';

interface Props {
  indicators: IndicatorDetail;
}

/**
 * 单个数据点：左侧小标签（muted uppercase），右侧数值（mono 加粗，可选色）
 */
function Stat({ label, value, color, mono = true }: { label: string; value: string; color?: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-bg-hover/40 transition-colors">
      <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">{label}</span>
      <span className={`text-xs font-bold ${mono ? 'font-mono tabular-nums' : ''}`} style={{ color: color || 'var(--color-text-primary)' }}>
        {value}
      </span>
    </div>
  );
}

/**
 * 区块分组标题（小标签 + 横向渐变线）
 */
function SectionLabel({ children, accent }: { children: React.ReactNode; accent?: 'red' | 'green' | 'blue' | 'gold' | 'purple' | 'cyan' }) {
  const dotColor = {
    red: '#ef4444', green: '#22c55e', blue: '#3b82f6',
    gold: '#f59e0b', purple: '#a855f7', cyan: '#06b6d4',
  }[accent || 'gold'];
  return (
    <div className="flex items-center gap-2 mt-2 first:mt-0 mb-1">
      <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: dotColor }} />
      <span className="text-[10px] font-bold tracking-[0.15em] uppercase" style={{ color: dotColor }}>
        {children}
      </span>
      <div className="flex-1 h-px bg-gradient-to-r from-border/40 to-transparent" />
    </div>
  );
}

export default function IndicatorPanel({ indicators }: Props) {
  const { kdj, macd, bbi, rsi, bollinger, vol_ratio, double_line, brick, dmi, signal, sell_score } = indicators;

  const sellColor = sell_score >= 3 ? '#ef4444' : sell_score >= 2 ? '#f59e0b' : '#22c55e';
  const signalColor = signal === 'B1' || signal === 'B2' ? '#22c55e'
    : signal === 'S1' || signal === 'S2' ? '#ef4444'
    : '#94a3b8';

  return (
    <div className="grid grid-cols-2 gap-x-1 max-h-[600px] overflow-y-auto pr-1">
      {/* 交易信号（横跨两列） */}
      <div className="col-span-2 mb-2 pb-2 border-b border-border/40">
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">交易信号</span>
            {macd.veto && <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent-red/15 text-accent-red font-bold tracking-wide">MACD 否决</span>}
          </div>
          <span className="text-sm font-black font-mono tabular-nums tracking-wide" style={{ color: signalColor }}>
            {signal}
          </span>
        </div>
      </div>

      {/* KDJ */}
      <SectionLabel accent="gold">KDJ</SectionLabel>
      <div className="col-span-2 grid grid-cols-3 gap-x-1">
        <Stat label="K" value={formatNumber(kdj.k)} />
        <Stat label="D" value={formatNumber(kdj.d)} />
        <Stat label="J" value={formatNumber(kdj.j)} color={kdj.j < 0 ? '#22c55e' : kdj.j > 100 ? '#ef4444' : undefined} />
      </div>

      {/* MACD */}
      <SectionLabel accent="blue">MACD</SectionLabel>
      <div className="col-span-2 grid grid-cols-3 gap-x-1">
        <Stat label="DIF" value={formatNumber(macd.dif, 3)} />
        <Stat label="DEA" value={formatNumber(macd.dea, 3)} />
        <Stat label="柱" value={formatNumber(macd.hist, 3)} color={(macd.hist ?? 0) >= 0 ? '#ef4444' : '#22c55e'} />
      </div>
      {(macd.gold_cross || macd.dead_cross) && (
        <div className="col-span-2 px-2 mb-1 flex items-center gap-2">
          {macd.gold_cross && <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent-green/15 text-accent-green font-bold">金叉</span>}
          {macd.dead_cross && <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent-red/15 text-accent-red font-bold">死叉</span>}
        </div>
      )}

      {/* RSI + BBI 合并一行 */}
      <SectionLabel accent="purple">RSI / BBI</SectionLabel>
      <div className="col-span-2 grid grid-cols-4 gap-x-1">
        <Stat label="6"  value={formatNumber(rsi.rsi6)} color={rsi.rsi6 > 70 ? '#ef4444' : rsi.rsi6 < 30 ? '#22c55e' : undefined} />
        <Stat label="12" value={formatNumber(rsi.rsi12)} />
        <Stat label="24" value={formatNumber(rsi.rsi24)} />
        <Stat label="BBI" value={formatNumber(bbi)} />
      </div>

      {/* 布林带 — 一行紧凑 */}
      <SectionLabel accent="cyan">布林带</SectionLabel>
      <div className="col-span-2 grid grid-cols-4 gap-x-1">
        <Stat label="上" value={formatNumber(bollinger.upper)} />
        <Stat label="中" value={formatNumber(bollinger.mid)} />
        <Stat label="下" value={formatNumber(bollinger.lower)} />
        <Stat label="位" value={`${formatNumber(bollinger.position)}%`}
              color={bollinger.position > 80 ? '#ef4444' : bollinger.position < 20 ? '#22c55e' : undefined} />
      </div>

      {/* 双线战法 + 量比 — 单独突出 */}
      <SectionLabel accent="red">双线战法</SectionLabel>
      <div className="col-span-2 grid grid-cols-4 gap-x-1">
        <Stat label="白" value={formatNumber(double_line.white)} color="#ffffff" />
        <Stat label="黄" value={formatNumber(double_line.yellow)} color="#fbbf24" />
        <Stat label="比" value={formatNumber(vol_ratio)} color={(vol_ratio ?? 0) > 2 ? '#f59e0b' : undefined} />
        <Stat label="砖" value={`${brick.count}块`} color={brick.trend === 'RED' ? '#ef4444' : brick.trend === 'GREEN' ? '#22c55e' : undefined} />
      </div>

      {/* DMI */}
      <SectionLabel accent="green">DMI</SectionLabel>
      <div className="col-span-2 grid grid-cols-3 gap-x-1">
        <Stat label="+DI" value={formatNumber(dmi.plus)} color="#22c55e" />
        <Stat label="-DI" value={formatNumber(dmi.minus)} color="#ef4444" />
        <Stat label="ADX" value={formatNumber(dmi.adx)} color={(dmi.adx ?? 0) > 25 ? '#f59e0b' : undefined} />
      </div>

      {/* 卖出评分（横跨两列 + 进度条） */}
      <div className="col-span-2 mt-3 pt-3 border-t border-border/40 px-2">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">卖出评分</span>
          <span className="text-base font-black font-mono tabular-nums" style={{ color: sellColor }}>
            {sell_score}<span className="text-text-muted text-xs font-bold">/5</span>
          </span>
        </div>
        <div className="h-1.5 rounded-full bg-bg-hover overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${(sell_score / 5) * 100}%`, backgroundColor: sellColor }}
          />
        </div>
      </div>
    </div>
  );
}
