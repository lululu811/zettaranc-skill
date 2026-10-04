// 策略列表（覆盖 modules/cli.py STRATEGY_ALIAS 的全部 14 个 criteria）
// 说明：CLI 有 16 个别名，其中「牵牛/牛绳」「沙漏/沙漏评分」各指向同一个 criteria，
// 前端按 criteria 去重，只保留主别名，避免出现两个结果完全相同的按钮。
export const STRATEGIES = [
  { alias: 'B1', label: 'B1 买点' },
  { alias: 'B2', label: 'B2 确认' },
  { alias: 'B3', label: 'B3 共识' },
  { alias: '完美图形', label: '完美图形' },
  { alias: '超级B1', label: '超级B1' },
  { alias: '长安战法', label: '长安战法' },
  { alias: '建仓波', label: '建仓波' },
  { alias: '吸筹', label: '吸筹' },
  { alias: '安全', label: '安全' },
  { alias: '超跌', label: '超跌' },
  { alias: '突破', label: '突破' },
  { alias: '牵牛', label: '牵牛（牛绳）' },
  { alias: '沙漏', label: '沙漏完美图形' },
  { alias: '量比战法', label: '量比战法' },
  { alias: '简单完美图形-1', label: '简单完美图形-1 经典' },
  { alias: '简单完美图形-2', label: '简单完美图形-2 异动横盘' },
  { alias: '简单完美图形-3', label: '简单完美图形-3 完美绿帽' },
] as const;

// 信号颜色映射（浅色玻璃底：饱和度适中、明度压低以保证对比度）
export const SIGNAL_COLORS: Record<string, string> = {
  B1: '#27ae60',
  B2: '#2980b9',
  B3: '#8e44ad',
  SB1: '#16a085',
  S1: '#c0392b',
  S2: '#d35400',
  S3: '#b7950b',
  BUY: '#27ae60',
  SELL: '#c0392b',
  HOLD: '#d68910',
  WATCH: '#7f8c8d',
};

// 风险等级颜色
export const RISK_COLORS: Record<string, string> = {
  LOW: '#27ae60',
  MEDIUM: '#d68910',
  HIGH: '#d35400',
  CRITICAL: '#c0392b',
  UNKNOWN: '#7f8c8d',
};

// 图表通用色板（浅色主题）
export const CHART_COLORS = {
  up: '#e74c3c',
  down: '#2ecc71',
  ma5: '#f39c12',
  ma10: '#3498db',
  ma20: '#9b59b6',
  ma60: '#16a085',
  bbi: '#9b59b6',
  volume: '#95a5a6',
  axis: '#999999',
  split: 'rgba(0,0,0,0.08)',
  text: '#666666',
} as const;

// 导航菜单
export const NAV_ITEMS = [
  { path: '/', label: '总览', icon: '◈' },
  { path: '/screen', label: '选股', icon: '◎' },
  { path: '/watchlist', label: '自选', icon: '★' },
  { path: '/backtest', label: '回测', icon: '⟲' },
  { path: '/simulator', label: '模拟', icon: '∿' },
  { path: '/trades', label: '交易', icon: '⇄' },
  { path: '/settings', label: '设置', icon: '⚙' },
] as const;
