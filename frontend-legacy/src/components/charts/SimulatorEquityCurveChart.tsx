import ReactECharts from 'echarts-for-react';
import type { SimulationEquityPoint } from '../../api/types';

interface Props {
  equityCurve: SimulationEquityPoint[];
  benchmarkCurve: Array<{ date: string; close: number }>;
  height?: number;
}

export default function SimulatorEquityCurveChart({
  equityCurve,
  benchmarkCurve,
  height = 360,
}: Props) {
  if (!equityCurve || equityCurve.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-text-muted">暂无数据</div>
    );
  }

  const dates = equityCurve.map((e) => e.date);
  const equities = equityCurve.map((e) => e.equity);

  // 计算回撤序列
  const drawdowns = equities.reduce(
    (acc, val) => {
      if (val > acc.peak) acc.peak = val;
      const dd = acc.peak > 0 ? -((acc.peak - val) / acc.peak) * 100 : 0;
      acc.values.push(dd);
      return acc;
    },
    { peak: equities[0], values: [] as number[] }
  ).values;

  // 对齐基准曲线到 equity 日期
  const benchMap = new Map(benchmarkCurve.map((b) => [b.date, b.close]));
  const firstBench = benchmarkCurve[0]?.close;
  const benchmarkValues = dates.map((date) => {
    const close = benchMap.get(date);
    if (close == null || !firstBench || firstBench === 0) return null;
    return (close / firstBench) * equities[0];
  });

  // 市场环境背景色
  const markAreas: Array<[object, object, object]> = [];
  let currentRegime = equityCurve[0]?.regime;
  let regimeStart = 0;
  equityCurve.forEach((point, idx) => {
    if (point.regime !== currentRegime || idx === equityCurve.length - 1) {
      const endIdx = idx === equityCurve.length - 1 ? idx : idx - 1;
      const color = currentRegime === '强势'
        ? 'rgba(34, 197, 94, 0.04)'
        : currentRegime === '弱势'
          ? 'rgba(239, 68, 68, 0.04)'
          : 'rgba(245, 158, 11, 0.03)';
      markAreas.push([
        {
          xAxis: dates[regimeStart],
          itemStyle: { color },
        },
        {
          xAxis: dates[endIdx],
        },
        {
          name: currentRegime,
        },
      ]);
      currentRegime = point.regime;
      regimeStart = idx;
    }
  });

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2236',
      borderColor: '#2a3a52',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: number | null; axisValue: string }>) => {
        const lines = [`<div class="font-bold">${params[0]?.axisValue}</div>`];
        params.forEach((p) => {
          if (p.value == null) return;
          const label = p.seriesName;
          const val = typeof p.value === 'number' ? p.value.toFixed(2) : p.value;
          lines.push(`${label}: ${val}`);
        });
        return lines.join('<br/>');
      },
    },
    legend: {
      data: ['权益', '基准', '回撤'],
      textStyle: { color: '#94a3b8', fontSize: 11 },
      top: 0,
    },
    grid: [
      { left: 60, right: 20, top: 35, bottom: 110 },
      { left: 60, right: 20, top: 260, bottom: 50 },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        gridIndex: 0,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLine: { lineStyle: { color: '#2a3a52' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        scale: true,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
      {
        type: 'value',
        gridIndex: 1,
        scale: true,
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: {
          color: '#64748b',
          fontSize: 10,
          formatter: '{value}%',
        },
        axisLine: { lineStyle: { color: '#2a3a52' } },
      },
    ],
    dataZoom: [
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        bottom: 10,
        height: 22,
        borderColor: '#2a3a52',
        fillerColor: 'rgba(245, 158, 11, 0.2)',
        handleStyle: { color: '#f59e0b' },
        textStyle: { color: '#64748b' },
      },
    ],
    series: [
      {
        name: '权益',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: equities,
        smooth: true,
        lineStyle: { color: '#3b82f6', width: 2 },
        symbol: 'none',
        markArea: {
          data: markAreas,
          silent: true,
        },
      },
      {
        name: '基准',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: benchmarkValues,
        smooth: true,
        lineStyle: { color: '#f59e0b', width: 1.5, type: 'dashed' },
        symbol: 'none',
      },
      {
        name: '回撤',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: drawdowns,
        smooth: true,
        lineStyle: { color: '#ef4444', width: 1 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(239, 68, 68, 0.4)' },
              { offset: 1, color: 'rgba(239, 68, 68, 0.02)' },
            ],
          },
        },
        symbol: 'none',
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} notMerge />;
}
