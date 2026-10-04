// 数字格式化
export function formatNumber(n: number, decimals = 2): string {
  if (n === null || n === undefined) return '--';
  return n.toFixed(decimals);
}

// 价格格式化（带 ¥ 前缀）
export function formatPrice(n: number | null | undefined): string {
  if (n === null || n === undefined) return '--';
  return `¥${n.toFixed(2)}`;
}

// 百分比格式化
export function formatPct(n: number, decimals = 2): string {
  if (n === null || n === undefined) return '--';
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`;
}

// 涨跌颜色 class
export function pctColor(n: number): string {
  if (n > 0) return 'text-up';
  if (n < 0) return 'text-down';
  return 'text-text-secondary';
}

// 大数字缩写
export function formatVolume(n: number): string {
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (Math.abs(n) >= 1e4) return `${(n / 1e4).toFixed(2)}万`;
  return n.toFixed(0);
}

/**
 * 用于 ECharts Y 轴的成交量格式化（更紧凑，无小数）
 * 3500000 → "350万"   12000000000 → "12亿"
 */
export function formatVolumeAxis(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(abs >= 1e10 ? 0 : 1)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(0)}万`;
  return n.toFixed(0);
}

// 评分星级
export function ratingStars(rating: string): string {
  const match = rating.match(/★+/);
  return match ? match[0] : '☆☆☆☆☆';
}

// 风险等级颜色
export function riskColor(level: string): string {
  const map: Record<string, string> = {
    LOW: '#22c55e',
    MEDIUM: '#f59e0b',
    HIGH: '#f97316',
    CRITICAL: '#ef4444',
  };
  return map[level] || '#64748b';
}
