import React from 'react';
import ReactECharts from 'echarts-for-react';
import type { KlineChart as KlineDataType } from '../../api/types';
import { SIGNAL_COLORS } from '../../lib/constants';
import { formatVolumeAxis, formatNumber } from '../../lib/formatters';

interface Props {
  data: KlineDataType;
  height?: number;
}

/* ── 浅色主题配色（中式红涨绿跌）── */
const UP = '#e74c3c';
const DOWN = '#2ecc71';
const AXIS = '#dddddd';
const LABEL = '#666666';
const SPLIT = 'rgba(0,0,0,0.08)';
const WHITE_LINE = '#2d3436'; // 白线在浅底上改用深灰蓝
const YELLOW_LINE = '#f39c12';
const BBI_LINE = '#9b59b6';
const BOLL_LINE = '#95a5a6';

type BgMode = 'none' | 'kirin' | 'waves';
type SubIndicator = 'KDJ' | 'MACD' | '砖形' | '呼吸波';

const KIRIN_COLORS: Record<string, string> = {
  吸筹: 'rgba(52, 152, 219, 0.07)',
  拉升: 'rgba(231, 76, 60, 0.07)',
  派发: 'rgba(255, 159, 67, 0.09)',
  回落: 'rgba(46, 204, 113, 0.07)',
};

const WAVE_COLORS: Record<string, string> = {
  建仓波: 'rgba(155, 89, 182, 0.07)',
  拉升波: 'rgba(231, 76, 60, 0.07)',
  冲刺波: 'rgba(192, 57, 43, 0.10)',
};

export default function KlineChart({ data, height = 936 }: Props) {
  const {
    dates,
    ohlc,
    volumes,
    pct_chgs,
    overlays,
    signal_markers,
    kdj,
    macd,
    brick,
    waves_sequence,
    kirin_sequence,
    breathing_wave,
  } = data;

  const [bgMode, setBgMode] = React.useState<BgMode>('kirin');
  const [subIndicator, setSubIndicator] = React.useState<SubIndicator>('KDJ');
  // 图例点击的显示/隐藏状态：ECharts 默认支持点击切换，但 notMerge 重绘会重置，
  // 这里把选择结果存起来并回写 legend.selected，保证切换背景/副图后仍保持。
  const [legendSelected, setLegendSelected] = React.useState<Record<string, boolean> | null>(null);

  const lastValid = (arr: (number | null)[]): number | null => {
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] !== null && arr[i] !== undefined) return arr[i];
    }
    return null;
  };

  const lastWhite = lastValid(overlays.white_line);
  const lastYellow = lastValid(overlays.yellow_line);
  const lastBbi = lastValid(overlays.bbi);
  const lastDate = dates[dates.length - 1];

  const makeMarkers = (action: 'BUY' | 'SELL') =>
    signal_markers
      .filter((m) => m.action === action)
      .map((m) => ({
        name: m.type,
        coord: [m.date, m.price],
        value: m.type,
        itemStyle: { color: SIGNAL_COLORS[m.type] || SIGNAL_COLORS[action === 'BUY' ? 'BUY' : 'SELL'] },
      }));

  /* ── 背景色块（麒麟四阶段 / 主力三波）── */
  const generateMarkArea = (sequence: string[] | undefined, colors: Record<string, string>) => {
    if (!sequence || sequence.length === 0) return undefined;
    const areas: Array<[Record<string, unknown>, Record<string, unknown>]> = [];
    let startIdx = 0;
    let currentVal: string | null = sequence[0];

    for (let i = 1; i <= sequence.length; i++) {
      const val = i < sequence.length ? sequence[i] : null;
      if (val !== currentVal) {
        if (currentVal && currentVal !== '未知' && colors[currentVal]) {
          areas.push([
            {
              name: currentVal,
              xAxis: dates[startIdx],
              itemStyle: { color: colors[currentVal] },
              label: {
                show: true,
                position: 'insideTop',
                color: '#7f8c8d',
                fontSize: 9,
                opacity: 0.75,
                fontWeight: 'bold',
                offset: [0, 6],
              },
            },
            { xAxis: dates[Math.min(i - 1, dates.length - 1)] },
          ]);
        }
        startIdx = i;
        currentVal = val;
      }
    }
    return areas.length > 0 ? { data: areas } : undefined;
  };

  const markAreaConfig =
    bgMode === 'kirin'
      ? generateMarkArea(kirin_sequence, KIRIN_COLORS)
      : bgMode === 'waves'
        ? generateMarkArea(waves_sequence, WAVE_COLORS)
        : undefined;

  /* ── 副图（grid 2）可切换指标 ── */
  const subSeries = (() => {
    switch (subIndicator) {
      case 'MACD':
        return [
          {
            name: 'DIF',
            type: 'line',
            data: macd.dif,
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            lineStyle: { width: 1.4, color: YELLOW_LINE },
            symbol: 'none',
          },
          {
            name: 'DEA',
            type: 'line',
            data: macd.dea,
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            lineStyle: { width: 1.4, color: '#3498db' },
            symbol: 'none',
          },
          {
            name: 'MACD',
            type: 'bar',
            data: macd.hist.map((v) => ({
              value: v,
              itemStyle: { color: (v ?? 0) >= 0 ? `${UP}b3` : `${DOWN}b3` },
            })),
            xAxisIndex: 2,
            yAxisIndex: 2,
            barWidth: '55%',
          },
        ];
      case '砖形':
        return [
          {
            name: '砖形图',
            type: 'bar',
            data: (brick.values || []).map((v, i) => {
              const c = (brick.colors || [])[i];
              return { value: v, itemStyle: { color: c === 1 ? UP : c === -1 ? DOWN : '#bdc3c7' } };
            }),
            xAxisIndex: 2,
            yAxisIndex: 2,
            barWidth: '60%',
          },
          {
            name: '砖值',
            type: 'line',
            data: brick.values,
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            lineStyle: { width: 1.6, color: YELLOW_LINE },
            symbol: 'none',
          },
        ];
      case '呼吸波':
        return [
          {
            name: '主力呼气',
            type: 'line',
            data: (breathing_wave || []).map((v) => (v > 0 ? v : 0)),
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            symbol: 'none',
            lineStyle: { width: 1.5, color: UP },
            areaStyle: {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(231, 76, 60, 0.30)' },
                  { offset: 1, color: 'rgba(231, 76, 60, 0.02)' },
                ],
              },
            },
          },
          {
            name: '主力吸气',
            type: 'line',
            data: (breathing_wave || []).map((v) => (v < 0 ? v : 0)),
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            symbol: 'none',
            lineStyle: { width: 1.5, color: DOWN },
            areaStyle: {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(46, 204, 113, 0.02)' },
                  { offset: 1, color: 'rgba(46, 204, 113, 0.30)' },
                ],
              },
            },
          },
        ];
      default:
        return [
          {
            name: 'K',
            type: 'line',
            data: kdj.k,
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            lineStyle: { width: 1.4, color: YELLOW_LINE },
            symbol: 'none',
          },
          {
            name: 'D',
            type: 'line',
            data: kdj.d,
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            lineStyle: { width: 1.4, color: '#3498db' },
            symbol: 'none',
          },
          {
            name: 'J',
            type: 'line',
            data: kdj.j,
            xAxisIndex: 2,
            yAxisIndex: 2,
            smooth: true,
            lineStyle: { width: 1.4, color: BBI_LINE },
            symbol: 'none',
          },
        ];
    }
  })();

  const subLegend =
    subIndicator === 'MACD'
      ? ['DIF', 'DEA', 'MACD']
      : subIndicator === '砖形'
        ? ['砖形图', '砖值']
        : subIndicator === '呼吸波'
          ? ['主力呼气', '主力吸气']
          : ['K', 'D', 'J'];

  const priceLabel = (value: number, color: string) => ({
    symbol: 'roundRect',
    symbolSize: [46, 18],
    symbolOffset: [30, 0],
    data: [
      {
        coord: [lastDate, value],
        value: formatNumber(value),
        itemStyle: { color: '#ffffff', borderColor: color, borderWidth: 1 },
        label: { color, fontSize: 10, fontWeight: 'bold' },
      },
    ],
  });

  const option = {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: AXIS,
      borderWidth: 1,
      textStyle: { color: '#333333', fontSize: 12 },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.12); border-radius: 12px; padding: 10px 12px;',
      formatter: (params: Array<{ seriesName: string; dataIndex: number; data: number[] }>) => {
        const k = params.find((p) => p.seriesName === 'K线');
        if (!k || !k.data) return '';
        const [open, close, low, high] = k.data;
        const idx = k.dataIndex;
        const pct = pct_chgs[idx];
        const color = close >= open ? UP : DOWN;
        const row = (label: string, val: string, cls = '') =>
          `<div style="display:flex;justify-content:space-between;gap:16px;font-size:12px;${cls}">` +
          `<span style="color:#888">${label}</span><span>${val}</span></div>`;
        return (
          `<div style="font-weight:700;margin-bottom:6px;color:#333">${dates[idx]}</div>` +
          row('开盘', open.toFixed(2)) +
          row('收盘', `<span style="color:${color};font-weight:700">${close.toFixed(2)}</span>`) +
          row('最高', high.toFixed(2)) +
          row('最低', low.toFixed(2)) +
          row('涨跌幅', `<span style="color:${color};font-weight:700">${pct.toFixed(2)}%</span>`) +
          row('成交量', formatVolumeAxis(volumes[idx]))
        );
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }], label: { backgroundColor: '#667eea' } },
    legend: {
      data: ['K线', '白线', '黄线', 'BBI', '布林上', '布林中', '布林下', ...subLegend],
      selected: legendSelected ?? undefined,
      top: 4,
      textStyle: { color: LABEL, fontSize: 11 },
      inactiveColor: '#c0c4cc',
      itemWidth: 14,
      itemHeight: 3,
    },
    // 三区 grid：主图 K线 / 成交量 / 副图指标
    // 副图指标区较上一版扩大一倍（13% → 20%），主图占比同步放大以拉长蜡烛
    grid: [
      { left: '7%', right: '5%', top: '5%', height: '47%' },
      { left: '7%', right: '5%', top: '55%', height: '14%' },
      { left: '7%', right: '5%', top: '71%', height: '20%' },
    ],
    xAxis: [0, 1, 2].map((i) => ({
      type: 'category',
      data: dates,
      gridIndex: i,
      boundaryGap: i === 0,
      axisLine: { lineStyle: { color: AXIS } },
      axisTick: { show: false },
      axisLabel: { show: i === 2, color: LABEL, fontSize: 10 },
      splitLine: { show: false },
      axisPointer: { label: { show: i === 2 } },
    })),
    yAxis: [
      {
        scale: true,
        gridIndex: 0,
        splitLine: { lineStyle: { color: SPLIT } },
        axisLabel: { color: LABEL, fontSize: 10 },
        axisLine: { show: false },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        splitLine: { show: false },
        axisLabel: { color: LABEL, fontSize: 10, formatter: (v: number) => formatVolumeAxis(v) },
        axisLine: { show: false },
        name: '成交量',
        nameTextStyle: { color: '#999', fontSize: 10, align: 'left' },
      },
      {
        scale: true,
        gridIndex: 2,
        splitNumber: 2,
        splitLine: { lineStyle: { color: SPLIT } },
        axisLabel: { color: LABEL, fontSize: 10 },
        axisLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], start: 60, end: 100 },
      {
        type: 'slider',
        xAxisIndex: [0, 1, 2],
        bottom: 4,
        height: 16,
        borderColor: AXIS,
        fillerColor: 'rgba(102,126,234,0.12)',
        handleStyle: { color: '#667eea' },
        textStyle: { color: LABEL, fontSize: 10 },
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN },
        markArea: markAreaConfig,
        markPoint: {
          symbol: 'triangle',
          symbolSize: 10,
          data: [
            ...makeMarkers('BUY').map((m) => ({ ...m, symbolRotate: 0, symbolOffset: [0, 10] })),
            ...makeMarkers('SELL').map((m) => ({ ...m, symbolRotate: 180, symbolOffset: [0, -10] })),
          ],
          label: { show: false },
        },
      },
      {
        name: '白线',
        type: 'line',
        data: overlays.white_line,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1.8, color: WHITE_LINE },
        symbol: 'none',
        markPoint: lastWhite !== null ? priceLabel(lastWhite, WHITE_LINE) : undefined,
      },
      {
        name: '黄线',
        type: 'line',
        data: overlays.yellow_line,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1.8, color: YELLOW_LINE },
        symbol: 'none',
        markPoint: lastYellow !== null ? priceLabel(lastYellow, YELLOW_LINE) : undefined,
      },
      {
        name: 'BBI',
        type: 'line',
        data: overlays.bbi,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1.4, color: BBI_LINE, type: 'dashed' },
        symbol: 'none',
        markPoint: lastBbi !== null ? priceLabel(lastBbi, BBI_LINE) : undefined,
      },
      {
        name: '布林上',
        type: 'line',
        data: overlays.boll_upper,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1, color: BOLL_LINE, type: 'dotted', opacity: 0.8 },
        symbol: 'none',
      },
      {
        name: '布林中',
        type: 'line',
        data: overlays.boll_mid,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1, color: BOLL_LINE, type: 'dotted', opacity: 0.8 },
        symbol: 'none',
      },
      {
        name: '布林下',
        type: 'line',
        data: overlays.boll_lower,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1, color: BOLL_LINE, type: 'dotted', opacity: 0.8 },
        symbol: 'none',
      },
      {
        name: '成交量',
        type: 'bar',
        data: volumes.map((v, i) => ({
          value: v,
          itemStyle: { color: pct_chgs[i] >= 0 ? `${UP}b3` : `${DOWN}b3` },
        })),
        xAxisIndex: 1,
        yAxisIndex: 1,
        barWidth: '60%',
      },
      ...subSeries,
    ],
  };

  const segBtn = (active: boolean) =>
    `px-3 py-1 text-[11px] font-bold rounded-md transition-all ${
      active
        ? 'brand-gradient-bg text-white shadow-[0_6px_16px_-8px_rgba(102,126,234,0.9)]'
        : 'text-text-muted hover:text-brand-from hover:bg-[rgba(102,126,234,0.10)]'
    }`;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-border/60">
        <div className="flex items-center gap-1.5 bg-white/60 border border-border rounded-lg p-1">
          {(['none', 'kirin', 'waves'] as const).map((t) => (
            <button key={t} type="button" onClick={() => setBgMode(t)} className={segBtn(bgMode === t)}>
              {t === 'none' ? '无背景' : t === 'kirin' ? '麒麟四阶段' : '主力三波'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 bg-white/60 border border-border rounded-lg p-1">
          {(['KDJ', 'MACD', '砖形', '呼吸波'] as const).map((t) => (
            <button key={t} type="button" onClick={() => setSubIndicator(t)} className={segBtn(subIndicator === t)}>
              {t}
            </button>
          ))}
        </div>
      </div>
      <ReactECharts
        option={option}
        style={{ height }}
        notMerge
        onEvents={{
          legendselectchanged: (params: { selected?: Record<string, boolean> }) => {
            if (params?.selected) setLegendSelected(params.selected);
          },
        }}
      />
    </div>
  );
}
