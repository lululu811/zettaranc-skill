// API TypeScript 类型定义（对应后端 Pydantic 模型）

// ── 通用 ──
export interface ErrorResponse {
  error: string;
  detail: string;
}

// ── 股票分析 ──
export interface StockAnalysis {
  ts_code: string;
  name: string;
  price: number;
  prev_close: number;
  pct_chg: number;
  trade_date: string;
  indicators: IndicatorDetail;
  waves: WaveInfo | null;
  kirin: KirinInfo | null;
  signals: StrategySignal[];
  score: ScoreDetail;
  diagnosis: DiagnosisSummary;
}

export interface IndicatorDetail {
  kdj: { k: number; d: number; j: number };
  macd: {
    dif: number; dea: number; hist: number; veto: boolean;
    gold_cross: boolean; dead_cross: boolean;
    top_divergence: boolean; bottom_divergence: boolean;
  };
  bbi: number;
  rsi: { rsi6: number; rsi12: number; rsi24: number };
  bollinger: { mid: number; upper: number; lower: number; width: number; position: number };
  ma: { ma5: number; ma10: number; ma20: number; ma60: number; high_52w: number; high_52w_dist: number };
  wr: { wr5: number; wr10: number };
  vol_ratio: number;
  double_line: { white: number; yellow: number; is_gold_cross: boolean; is_dead_cross: boolean };
  brick: { value: number; trend: string; count: number; trend_up: boolean; is_fanbao: boolean };
  dmi: { plus: number; minus: number; adx: number };
  signal: string;
  sell_score: number;
  sell_items: Record<string, boolean>;
}

export interface StrategySignal {
  strategy: string;
  date: string;
  confidence: number;
  action: string;
  description: string;
  priority: string;
  target_price: number | null;
  stop_loss: number | null;
}

export interface ScoreDetail {
  total: number;
  b1_score: number;
  trend_score: number;
  volume_score: number;
  risk_score: number;
  rating: string;
  reasons: string[];
  warnings: string[];
}

export interface DiagnosisSummary {
  price_position: string;
  trend_status: string;
  sell_score: number;
  sell_score_desc: string;
  kirin_phase: string;
  bull_rope: string;
  sandglass_score: number;
  is_centipede: boolean;
  risk_level: string;
  recommendation: string;
}

export interface WaveInfo {
  wave: string;
  confidence: number;
  suggestion: string;
}

export interface KirinInfo {
  phase: string;
  sub_type: string;
  confidence: number;
  operation: string;
}

// ── K 线图表 ──
export interface KlineChart {
  ts_code: string;
  name: string;
  dates: string[];
  ohlc: number[][];
  volumes: number[];
  pct_chgs: number[];
  overlays: ChartOverlays;
  signal_markers: SignalMarker[];
  kdj: { k: (number | null)[]; d: (number | null)[]; j: (number | null)[] };
  macd: { dif: (number | null)[]; dea: (number | null)[]; hist: (number | null)[] };
  brick: { values: (number | null)[]; colors: (number | null)[] };
  waves_sequence?: string[];
  kirin_sequence?: string[];
  breathing_wave?: number[];
}

export interface ChartOverlays {
  ma5: (number | null)[];
  ma10: (number | null)[];
  ma20: (number | null)[];
  ma60: (number | null)[];
  bbi: (number | null)[];
  boll_upper: (number | null)[];
  boll_mid: (number | null)[];
  boll_lower: (number | null)[];
  white_line: (number | null)[];
  yellow_line: (number | null)[];
}

export interface SignalMarker {
  date: string;
  type: string;
  price: number;
  action: string;
}

// ── 选股 ──
export interface StrategyInfo {
  alias: string;
  criteria: string;
  description: string;
}

export interface ScreenResult {
  strategy: string;
  criteria: string;
  count: number;
  stocks: StockScore[];
}

export interface StockScore {
  ts_code: string;
  name: string;
  score: number;
  b1_score: number;
  trend_score: number;
  volume_score: number;
  risk_score: number;
  rating: string;
  reasons: string[];
  warnings: string[];
}

// ── 自选股 ──
export interface WatchlistItem {
  id: number;
  ts_code: string;
  name: string;
  tags: string;
  notes: string;
  added_date: string;
  alert_enabled: boolean;
}

export interface WatchlistList {
  count: number;
  items: WatchlistItem[];
}

export interface WatchAlert {
  ts_code: string;
  name: string;
  alert_type: string;
  level: string;
  message: string;
}

export interface WatchlistScan {
  total: number;
  b1_count: number;
  b2_count: number;
  exit_count: number;
  break_count: number;
  abnormal_count: number;
  alerts: WatchAlert[];
}

// ── 回测 ──
export interface BacktestResult {
  ts_code: string;
  summary: BacktestSummary;
  equity_curve: [string, number][];
  trades: BacktestTrade[];
}

export interface BacktestSummary {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  total_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  avg_holding_days: number;
  annualized_return: number;
  win_count: number;
  avg_pnl: number;
  max_win: number;
  max_loss: number;
}

export interface BacktestTrade {
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  exit_reason: string;
  pnl_pct: number;
  holding_days: number;
}

// ── 诊断 ──
export interface DiagnosisReport {
  ts_code: string;
  name: string;
  price: number;
  trade_date: string;
  price_position: string;
  trend_status: string;
  sell_score: number;
  sell_score_desc: string;
  kirin_phase: string;
  bull_rope_status: string;
  sandglass_score: number;
  is_centipede: boolean;
  stop_loss: number | null;
  target_price: number | null;
  recommendation: string;
  risk_level: string;
  exit_signals: Array<{ signal_type: string; date: string; description: string; confidence: number }>;
  buy_signals: Array<{ signal_type: string; date: string; description: string; confidence: number; action: string }>;
}

// ── 交易 ──
export interface TradeRecord {
  id: number;
  ts_code: string;
  trade_date: string;
  action: string;
  price: number;
  quantity: number;
  amount: number;
  reason: string;
  signal_type: string;
  zg_review: string;
  tags: string;
  notes: string;
}

export interface TradeList {
  total: number;
  page: number;
  page_size: number;
  records: TradeRecord[];
}

export interface TradeStats {
  summary: Record<string, unknown>;
  pnl: Record<string, unknown>;
}

export interface CommentaryResponse {
  ts_code: string;
  trade_date: string;
  commentary_text: string;
  generated_at: string;
  model_used: string;
  cached: boolean;
  error?: string;
}

// ── 模拟器 ──
export interface SimulationMetrics {
  total_return: number;
  annualized_return: number;
  benchmark_return: number | null;
  alpha: number | null;
  beta: number | null;
  sharpe_ratio: number;
  sortino_ratio: number | null;
  calmar_ratio: number | null;
  max_drawdown: number;
  max_drawdown_duration: number | null;
  win_rate: number;
  profit_factor: number;
  avg_win: number | null;
  avg_loss: number | null;
  gain_loss_ratio: number | null;
  max_consecutive_wins: number | null;
  max_consecutive_losses: number | null;
  volatility_annual: number | null;
}

export interface SimulationTrade {
  action: string;
  ts_code: string;
  date: string;
  price: number;
  shares: number;
  pnl: number | null;
  pnl_pct: number | null;
  fee: number;
  stamp_duty: number;
  transfer_fee: number;
  reason: string;
}

export interface SimulationEquityPoint {
  date: string;
  equity: number;
  cash: number;
  positions: number;
  regime: string;
}

export interface SimulationRequest {
  ts_codes: string[];
  days: number;
  capital: number;
  max_positions: number;
  risk_per_trade: number;
  min_score: number;
  min_signals: number;
  atr_sizing: boolean;
  max_position_pct: number;
  benchmark: string;
  cost_model: string;
  slippage: string;
  no_st: boolean;
  strategy_mode: string;
  strategy_lookback: number;
  min_resonance_score: number;
  walk_forward: boolean;
  wf_train_days: number;
  wf_test_days: number;
  wf_objective: string;
}

export interface SimulationResponse {
  summary: Record<string, unknown>;
  metrics: SimulationMetrics | null;
  equity_curve: SimulationEquityPoint[];
  benchmark_curve: Array<{ date: string; close: number }>;
  trades: SimulationTrade[];
  rejected_entries: Array<Record<string, unknown>>;
  resonance_summary: Record<string, unknown>;
  positions: Array<Record<string, unknown>>;
}
