import api from './client';
import type { BacktestResult } from './types';

export interface BacktestParams {
  ts_code: string;
  days?: number;
  initial_capital?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  position_pct?: number;
}

export async function runShaofu(params: BacktestParams): Promise<BacktestResult> {
  const { data } = await api.post<BacktestResult>('/backtest/shaofu', params);
  return data;
}

export async function runMulti(params: BacktestParams): Promise<BacktestResult> {
  const { data } = await api.post<BacktestResult>('/backtest/multi', params);
  return data;
}

export async function runPortfolio(tsCodes: string[], params?: Partial<BacktestParams>): Promise<BacktestResult> {
  const { data } = await api.post<BacktestResult>('/backtest/portfolio', {
    ts_codes: tsCodes,
    ...params,
  });
  return data;
}
