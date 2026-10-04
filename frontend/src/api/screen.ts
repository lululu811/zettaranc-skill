import api from './client';
import type { ScreenResult, StrategyInfo } from './types';

export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const { data } = await api.get<StrategyInfo[]>('/screen/strategies');
  return data;
}

export async function runScreen(
  strategy: string,
  limit = 100,
  params?: Record<string, number>,
  top = 0,
): Promise<ScreenResult> {
  const { data } = await api.post<ScreenResult>('/screen/run', {
    strategy,
    limit, // 扫描多少只股票
    top, // 返回条数（0=全部命中）
    use_parallel: true,
    params: params ?? {},
  });
  return data;
}
