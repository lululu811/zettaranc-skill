import ReactECharts from 'echarts-for-react';
import type { ScoreDetail } from '../../api/types';

interface Props {
  score: ScoreDetail;
  height?: number;
}

export default function RadarChart({ score, height = 220 }: Props) {
  const option = {
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: 'B1', max: 100 },
        { name: '趋势', max: 100 },
        { name: '量价', max: 100 },
        { name: '风险', max: 100 },
      ],
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: '#666666', fontSize: 12, fontWeight: 500 },
      splitLine: { lineStyle: { color: '#e3e8ef', width: 1 } },
      splitArea: {
        areaStyle: {
          color: ['rgba(255,255,255,0.55)', 'rgba(102,126,234,0.04)', 'rgba(255,255,255,0.55)', 'rgba(102,126,234,0.04)'],
        },
      },
      axisLine: { lineStyle: { color: '#e3e8ef', width: 1 } },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [score.b1_score, score.trend_score, score.volume_score, score.risk_score],
            name: '评分',
            areaStyle: {
              color: {
                type: 'radial',
                x: 0.5,
                y: 0.5,
                r: 0.5,
                colorStops: [
                  { offset: 0, color: 'rgba(102, 126, 234, 0.35)' },
                  { offset: 1, color: 'rgba(118, 75, 162, 0.12)' },
                ],
              },
            },
            lineStyle: { color: '#667eea', width: 2 },
            itemStyle: { color: '#667eea', borderColor: '#ffffff', borderWidth: 1 },
          },
        ],
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} notMerge />;
}
