import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppStore } from '../stores/appStore';
import { useStockAnalysis, useKlineData } from '../hooks/useStockAnalysis';
import Card from '../components/ui/Card';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import KlineChart from '../components/charts/KlineChart';
import RadarChart from '../components/charts/RadarChart';
import IndicatorPanel from '../components/stock/IndicatorPanel';
import ScoreCard from '../components/stock/ScoreCard';
import SignalTimeline from '../components/stock/SignalTimeline';
import DiagnosisCard from '../components/stock/DiagnosisCard';
import CommentaryCard from '../components/stock/CommentaryCard';
import { formatNumber, formatPct, pctColor } from '../lib/formatters';

export default function StockAnalysis() {
  const { tsCode = '' } = useParams<{ tsCode: string }>();
  const navigate = useNavigate();
  const screenResults = useAppStore((s) => s.screenResults);
  const clearScreenResults = useAppStore((s) => s.clearScreenResults);
  const { data: analysis, isLoading: loadingAnalysis, error: analysisError } = useStockAnalysis(tsCode);
  const { data: klineData, isLoading: loadingKline } = useKlineData(tsCode);
  const [copied, setCopied] = useState(false);

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => console.error('复制股票代码失败'),
    );
  };

  if (loadingAnalysis || loadingKline) {
    return (
      <div className="flex items-center justify-center h-96">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (analysisError || !analysis) {
    return (
      <div className="flex items-center justify-center h-96 text-text-muted">
        加载失败：{analysisError?.message || '未知错误'}
      </div>
    );
  }

  const priceChange = analysis.prev_close > 0
    ? ((analysis.price - analysis.prev_close) / analysis.prev_close) * 100
    : (analysis.pct_chg || 0);

  return (
    <div className="flex gap-5 items-start">
      {/* ============ 左侧：上次选股结果列表（可逐个切换） ============ */}
      {screenResults.length > 0 && (
        <aside className="w-60 shrink-0 sticky top-2 max-h-[calc(100vh-5rem)] overflow-y-auto glass-card p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-bold text-text-primary">选股结果 · {screenResults.length}</div>
            <button
              type="button"
              onClick={clearScreenResults}
              title="收起列表"
              className="text-xs text-text-muted hover:text-accent-red transition-colors"
            >
              收起
            </button>
          </div>
          <div className="space-y-1">
            {screenResults.map((item, idx) => {
              const active = item.ts_code === tsCode;
              return (
                <button
                  key={item.ts_code}
                  type="button"
                  onClick={() => navigate(`/stock/${item.ts_code}`)}
                  className={`w-full text-left px-2.5 py-2 rounded-lg border transition-all ${
                    active
                      ? 'brand-gradient-bg text-white border-transparent shadow-[0_8px_20px_-10px_rgba(102,126,234,0.95)]'
                      : 'border-transparent hover:bg-[rgba(102,126,234,0.10)]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`font-mono text-[10px] ${active ? 'text-white/85' : 'text-text-muted'}`}>
                      {String(idx + 1).padStart(2, '0')} {item.ts_code}
                    </span>
                    <span
                      className={`font-mono text-[11px] font-bold ${active ? 'text-white' : 'text-brand-from'}`}
                    >
                      {item.score}
                    </span>
                  </div>
                  <div className={`text-sm truncate ${active ? 'text-white' : 'text-text-primary'}`}>
                    {item.name}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>
      )}

      <div className="flex-1 min-w-0 space-y-5">
      {/* ============ Header - 股票信息 ============ */}
      <div className="glass-card relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(102,126,234,0.16),transparent_55%)]"></div>
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(118,75,162,0.12),transparent_55%)]"></div>
        <div className="relative p-6">
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0">
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <h1 className="text-3xl md:text-4xl font-black text-text-primary tracking-tight font-mono">
                  {analysis.ts_code}
                </h1>
                <span className="text-sm text-text-secondary bg-white/70 px-3 py-1 rounded-md border border-border font-medium">
                  {analysis.name}
                </span>
                <button
                  type="button"
                  onClick={() => copyCode(analysis.ts_code)}
                  title="复制股票代码"
                  className="rounded-md border border-border bg-white/70 px-2.5 py-1 text-xs text-text-secondary hover:text-brand-from hover:border-brand-from/50 transition-colors"
                >
                  {copied ? '已复制' : '复制代码'}
                </button>
              </div>
              <div className="text-xs text-text-muted flex items-center gap-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-green animate-pulse"></span>
                <span className="tracking-wider">DATA AS OF</span>
                <span className="font-mono text-text-secondary">{analysis.trade_date}</span>
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-4xl md:text-5xl font-black text-text-primary tabular-nums tracking-tight leading-none">
                ¥{formatNumber(analysis.price)}
              </div>
              <div className={`text-lg md:text-xl font-bold mt-2 tabular-nums ${pctColor(priceChange)}`}>
                {priceChange >= 0 ? '▲' : '▼'} {formatPct(priceChange)}
              </div>
              {analysis.prev_close > 0 && (
                <div className="text-[10px] text-text-muted mt-1 font-mono">
                  昨收 ¥{formatNumber(analysis.prev_close)}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ============ K 线图 - 全宽 ============ */}
      <Card title="K 线图 · 三区联动（K线 / 成交量 / 副图指标）">
        {klineData && <KlineChart data={klineData} />}
      </Card>

      {/* ============ Z哥点评 - Hero 全宽（位置：从右栏底部 → K线图下方） ============ */}
      <CommentaryCard tsCode={tsCode} />

      {/* ============ Main 2-column Grid ============ */}
      <div className="grid grid-cols-12 gap-5">
        {/* Left: Indicators + Signals */}
        <div className="col-span-8 space-y-5">
          <Card title="技术指标">
            <IndicatorPanel indicators={analysis.indicators} />
          </Card>
          <Card title="战法信号">
            <SignalTimeline signals={analysis.signals} />
          </Card>
        </div>

        {/* Right: Score + Radar + Waves + Diagnosis */}
        <div className="col-span-4 space-y-5">
          <Card title="综合评分">
            <ScoreCard score={analysis.score} />
          </Card>
          <Card title="评分雷达">
            <RadarChart score={analysis.score} height={220} />
          </Card>
          {(analysis.waves || analysis.kirin) && (
            <Card title="主力阶段">
              <div className="space-y-3">
                {analysis.waves && (
                  <div className="flex items-center justify-between p-3 bg-gradient-to-r from-accent-blue/[0.10] to-accent-purple/[0.10] rounded-lg border border-border/30">
                    <div>
                      <div className="text-[10px] text-text-muted mb-1 font-semibold uppercase tracking-wider">三波理论</div>
                      <div className="text-sm font-bold text-text-primary">{analysis.waves.wave}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-text-muted mb-1 font-semibold uppercase tracking-wider">置信度</div>
                      <div className="text-base font-black text-accent-gold tabular-nums">{(analysis.waves.confidence * 100).toFixed(0)}%</div>
                    </div>
                  </div>
                )}
                {analysis.kirin && (
                  <div className="flex items-center justify-between p-3 bg-gradient-to-r from-accent-gold/[0.12] to-accent-red/[0.10] rounded-lg border border-border/60">
                    <div>
                      <div className="text-[10px] text-text-muted mb-1 font-semibold uppercase tracking-wider">麒麟会</div>
                      <div className="text-sm font-bold text-text-primary">{analysis.kirin.phase}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-text-muted mb-1 font-semibold uppercase tracking-wider">置信度</div>
                      <div className="text-base font-black text-accent-gold tabular-nums">{(analysis.kirin.confidence * 100).toFixed(0)}%</div>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}
          <Card title="诊断报告">
            <DiagnosisCard diagnosis={analysis.diagnosis} />
          </Card>
        </div>
      </div>
      </div>
    </div>
  );
}
