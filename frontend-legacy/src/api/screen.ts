import api from './client';
import type { ScreenResult, StrategyInfo } from './types';

export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const { data } = await api.get<StrategyInfo[]>('/screen/strategies');
  return data;
}

export async function runScreen(strategy: string, limit = 20): Promise<ScreenResult> {
  const { data } = await api.post<ScreenResult>('/screen/run', { strategy, limit, use_parallel: true });
  return data;
}
