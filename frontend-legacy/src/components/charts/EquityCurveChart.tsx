import ReactECharts from 'echarts-for-react';

interface Props {
  equityCurve: [string, number][];
  height?: number;
}

export default function EquityCurveChart({ equityCurve, height = 300 }: Props) {
  if (!equityCurve || equityCurve.length === 0) {
    return <div className="flex h-40 items-center justify-center text-text-muted">暂无数据</div>;
  }

  const dates = equityCurve.map((e) => e[0]);
  const values = equityCurve.map((e) => e[1]);

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2236',
      borderColor: '#2a3a52',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
    },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#2a3a52' } },
      axisLabel: { color: '#64748b', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: '#1e293b' } },
      axisLabel: { color: '#64748b', fontSize: 10 },
      axisLine: { lineStyle: { color: '#2a3a52' } },
    },
    series: [
      {
        type: 'line',
        data: values,
        smooth: true,
        lineStyle: { color: '#f59e0b', width: 2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245, 158, 11, 0.3)' },
              { offset: 1, color: 'rgba(245, 158, 11, 0.02)' },
            ],
          },
        },
        symbol: 'none',
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} notMerge />;
}
