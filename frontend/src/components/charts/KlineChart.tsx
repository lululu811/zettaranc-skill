import React from 'react';
import ReactECharts from 'echarts-for-react';
import type { KlineChart as KlineDataType } from '../../api/types';
import { SIGNAL_COLORS } from '../../lib/constants';
import { formatVolumeAxis, formatNumber } from '../../lib/formatters';

interface Props {
  data: KlineDataType;
  height?: number;
}

export default function KlineChart({ data, height = 820 }: Props) {
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

  const [bgMode, setBgMode] = React.useState<'none' | 'kirin' | 'waves'>('kirin');

  const upColor = '#ef4444';
  const downColor = '#22c55e';

  // 取每个 series 的最后一个非 null 值，用作右侧点位标签
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

  // 构建 markPoint 数据
  const buyMarkers = signal_markers
    .filter((m) => m.action === 'BUY')
    .map((m) => ({
      name: m.type,
      coord: [m.date, m.price],
      value: m.type,
      itemStyle: { color: SIGNAL_COLORS[m.type] || SIGNAL_COLORS.BUY },
    }));

  const sellMarkers = signal_markers
    .filter((m) => m.action === 'SELL')
    .map((m) => ({
      name: m.type,
      coord: [m.date, m.price],
      value: m.type,
      itemStyle: { color: SIGNAL_COLORS[m.type] || SIGNAL_COLORS.SELL },
    }));

  // ── 背景色块区间压缩逻辑 ──
  const kirinColors: Record<string, string> = {
    '吸筹': 'rgba(59, 130, 246, 0.15)',  // 淡蓝
    '拉升': 'rgba(239, 68, 68, 0.15)',  // 淡红
    '派发': 'rgba(245, 158, 11, 0.15)',  // 淡黄
    '回落': 'rgba(34, 197, 94, 0.12)',  // 淡绿
  };

  const waveColors: Record<string, string> = {
    '建仓波': 'rgba(139, 92, 246, 0.15)', // 紫色
    '拉升波': 'rgba(239, 68, 68, 0.15)', // 红色
    '冲刺波': 'rgba(244, 63, 94, 0.20)', // 粉红
  };

  const generateMarkArea = (sequence: string[] | undefined, colors: Record<string, string>) => {
    const areas: any[] = [];
    if (!sequence || sequence.length === 0) return undefined;

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
              itemStyle: {
                color: colors[currentVal],
              },
              label: {
                show: true,
                position: 'insideTop',
                color: '#94a3b8',
                fontSize: 8,
                opacity: 0.5,
                fontWeight: 'bold',
                offset: [0, 8],
              },
            },
            {
              xAxis: dates[Math.min(i - 1, dates.length - 1)],
            },
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
      ? generateMarkArea(kirin_sequence, kirinColors)
      : bgMode === 'waves'
      ? generateMarkArea(waves_sequence, waveColors)
      : undefined;

  const option = {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: '#1a2236',
      borderColor: '#2a3a52',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
    },
    legend: {
      data: ['K线', '白线', '黄线', 'BBI', '布林上', '布林中', '布林下', '主力呼气', '主力吸气'],
      top: 0,
      textStyle: { color: '#94a3b8', fontSize: 11 },
      itemWidth: 14,
      itemHeight: 2,
    },
    grid: [
      { left: 60, right: 70, top: 30, height: '30%' },
      { left: 60, right: 20, top: '35%', height: '9%' },
      { left: 60, right: 20, top: '47%', height: '11%' },
      { left: 60, right: 20, top: '60%', height: '11%' },
      { left: 60, right: 20, top: '73%', height: '11%' },
      { left: 60, right: 20, top: '86%', height: '9%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        gridIndex: 0,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        splitLine: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 2,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 3,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 4,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 5,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        gridIndex: 0,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
      {
        scale: true,
        gridIndex: 1,
        splitLine: { show: false },
        axisLabel: {
          color: '#64748b',
          fontSize: 10,
          formatter: (v: number) => formatVolumeAxis(v),
        },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
      {
        scale: true,
        gridIndex: 2,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
      {
        scale: true,
        gridIndex: 3,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
      {
        scale: true,
        gridIndex: 4,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
      {
        scale: true,
        gridIndex: 5,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3, 4, 5], start: 60, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3, 4, 5], bottom: 5, height: 15, borderColor: '#2a3a52', fillerColor: 'rgba(245,158,11,0.1)', textStyle: { color: '#64748b' } },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor,
        },
        markArea: markAreaConfig,
        markPoint: {
          symbol: 'triangle',
          symbolSize: 10,
          data: [
            ...buyMarkers.map((m) => ({
              ...m,
              symbol: 'triangle',
              symbolRotate: 0,
              symbolOffset: [0, 10],
            })),
            ...sellMarkers.map((m) => ({
              ...m,
              symbol: 'triangle',
              symbolRotate: 180,
              symbolOffset: [0, -10],
            })),
          ],
          label: { show: false },
        },
      },
      // 白线 (EMA(EMA(C,10),10)) - 短期动能线
      {
        name: '白线',
        type: 'line',
        data: overlays.white_line,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 2, color: '#ffffff' },
        symbol: 'none',
        // 右侧点位标签
        markPoint: lastWhite !== null ? {
          symbol: 'roundRect',
          symbolSize: [44, 18],
          symbolOffset: [28, 0],
          data: [{
            coord: [lastDate, lastWhite],
            value: formatNumber(lastWhite),
            itemStyle: { color: '#0b0f19', borderColor: '#ffffff', borderWidth: 1 },
            label: { color: '#ffffff', fontSize: 10, fontWeight: 'bold' },
          }],
        } : undefined,
      },
      // 黄线 ((MA14+MA28+MA57+MA114)/4) - 多空生命线
      {
        name: '黄线',
        type: 'line',
        data: overlays.yellow_line,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 2, color: '#fbbf24' },
        symbol: 'none',
        markPoint: lastYellow !== null ? {
          symbol: 'roundRect',
          symbolSize: [44, 18],
          symbolOffset: [28, 0],
          data: [{
            coord: [lastDate, lastYellow],
            value: formatNumber(lastYellow),
            itemStyle: { color: '#0b0f19', borderColor: '#fbbf24', borderWidth: 1 },
            label: { color: '#fbbf24', fontSize: 10, fontWeight: 'bold' },
          }],
        } : undefined,
      },
      // BBI 多空指数
      {
        name: 'BBI',
        type: 'line',
        data: overlays.bbi,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1.5, color: '#06b6d4', type: 'dashed' },
        symbol: 'none',
        markPoint: lastBbi !== null ? {
          symbol: 'roundRect',
          symbolSize: [44, 18],
          symbolOffset: [28, 0],
          data: [{
            coord: [lastDate, lastBbi],
            value: formatNumber(lastBbi),
            itemStyle: { color: '#0b0f19', borderColor: '#06b6d4', borderWidth: 1 },
            label: { color: '#06b6d4', fontSize: 10, fontWeight: 'bold' },
          }],
        } : undefined,
      },
      // 布林上轨
      {
        name: '布林上',
        type: 'line',
        data: overlays.boll_upper,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1, color: '#a855f7', type: 'dotted', opacity: 0.6 },
        symbol: 'none',
      },
      // 布林中轨
      {
        name: '布林中',
        type: 'line',
        data: overlays.boll_mid,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1, color: '#a855f7', type: 'dotted', opacity: 0.6 },
        symbol: 'none',
      },
      // 布林下轨
      {
        name: '布林下',
        type: 'line',
        data: overlays.boll_lower,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { width: 1, color: '#a855f7', type: 'dotted', opacity: 0.6 },
        symbol: 'none',
      },
      // 成交量
      {
        name: '成交量',
        type: 'bar',
        data: volumes.map((v, i) => ({
          value: v,
          itemStyle: { color: pct_chgs[i] >= 0 ? `${upColor}80` : `${downColor}80` },
        })),
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      // KDJ
      {
        name: 'K',
        type: 'line',
        data: kdj.k,
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: true,
        lineStyle: { width: 1, color: '#f59e0b' },
        symbol: 'none',
      },
      {
        name: 'D',
        type: 'line',
        data: kdj.d,
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: true,
        lineStyle: { width: 1, color: '#3b82f6' },
        symbol: 'none',
      },
      {
        name: 'J',
        type: 'line',
        data: kdj.j,
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: true,
        lineStyle: { width: 1, color: '#a855f7' },
        symbol: 'none',
      },
      // MACD
      {
        name: 'DIF',
        type: 'line',
        data: macd.dif,
        xAxisIndex: 3,
        yAxisIndex: 3,
        smooth: true,
        lineStyle: { width: 1, color: '#f59e0b' },
        symbol: 'none',
      },
      {
        name: 'DEA',
        type: 'line',
        data: macd.dea,
        xAxisIndex: 3,
        yAxisIndex: 3,
        smooth: true,
        lineStyle: { width: 1, color: '#3b82f6' },
        symbol: 'none',
      },
      {
        name: 'MACD',
        type: 'bar',
        data: macd.hist.map((v) => ({
          value: v,
          itemStyle: { color: (v ?? 0) >= 0 ? `${upColor}80` : `${downColor}80` },
        })),
        xAxisIndex: 3,
        yAxisIndex: 3,
      },
      // 砖型图 - 红绿柱子
      {
        name: '砖型图',
        type: 'bar',
        data: (brick.values || []).map((v, i) => {
          const color = (brick.colors || [])[i];
          const barColor = color === 1 ? upColor : color === -1 ? downColor : '#475569';
          return {
            value: v,
            itemStyle: { color: barColor },
          };
        }),
        xAxisIndex: 4,
        yAxisIndex: 4,
        barWidth: '60%',
      },
      // 砖型图 - 折线叠加
      {
        name: '砖值',
        type: 'line',
        data: brick.values,
        xAxisIndex: 4,
        yAxisIndex: 4,
        smooth: true,
        lineStyle: { width: 2, color: '#f59e0b' },
        symbol: 'none',
      },
      // 呼气波（主力放量上攻，正分值部分）
      {
        name: '主力呼气',
        type: 'line',
        data: (breathing_wave || []).map((v) => (v > 0 ? v : 0)),
        xAxisIndex: 5,
        yAxisIndex: 5,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#ef4444' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(239, 68, 68, 0.35)' },
              { offset: 1, color: 'rgba(239, 68, 68, 0.02)' },
            ],
          },
        },
      },
      // 吸气波（主力缩量调整，负分值部分）
      {
        name: '主力吸气',
        type: 'line',
        data: (breathing_wave || []).map((v) => (v < 0 ? v : 0)),
        xAxisIndex: 5,
        yAxisIndex: 5,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#22c55e' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(34, 197, 94, 0.02)' },
              { offset: 1, color: 'rgba(34, 197, 94, 0.35)' },
            ],
          },
        },
      },
    ],
  };

  return (
    <div className="space-y-4">
      {/* 选项控件 */}
      <div className="flex items-center justify-between pb-2 border-b border-border/20">
        <div className="text-xs text-text-muted font-semibold tracking-wider">主力大势背景渲染</div>
        <div className="flex items-center gap-1.5 bg-bg-secondary p-1 rounded-lg border border-border/30">
          {(
            [
              { key: 'none', label: '无背景' },
              { key: 'kirin', label: '麒麟四阶段' },
              { key: 'waves', label: '主力三波理论' },
            ] as const
          ).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setBgMode(t.key)}
              className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${
                bgMode === t.key
                  ? 'bg-accent-gold text-bg-primary shadow-sm shadow-accent-gold/20'
                  : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <ReactECharts option={option} style={{ height }} notMerge />
    </div>
  );
}
