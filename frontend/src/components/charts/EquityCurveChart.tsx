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
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#dddddd',
      borderWidth: 1,
      textStyle: { color: '#333333', fontSize: 11 },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.12); border-radius: 10px;',
    },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#dddddd' } },
      axisTick: { show: false },
      axisLabel: { color: '#666666', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: 'rgba(0,0,0,0.08)' } },
      axisLabel: { color: '#666666', fontSize: 10 },
      axisLine: { show: false },
    },
    series: [
      {
        type: 'line',
        data: values,
        smooth: true,
        lineStyle: { color: '#667eea', width: 2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(102, 126, 234, 0.28)' },
              { offset: 1, color: 'rgba(102, 126, 234, 0.02)' },
            ],
          },
        },
        symbol: 'none',
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} notMerge />;
}
