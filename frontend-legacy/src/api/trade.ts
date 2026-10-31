import api from './client';
import type { TradeList, TradeStats } from './types';

export async function fetchTrades(page = 1, pageSize = 20): Promise<TradeList> {
  const { data } = await api.get<TradeList>('/trade/', { params: { page, page_size: pageSize } });
  return data;
}

export async function addTrade(text: string) {
  const { data } = await api.post('/trade/', { text });
  return data;
}

export async function parseTrade(text: string) {
  const { data } = await api.post('/trade/parse', { text });
  return data;
}

export async function deleteTrade(tradeId: number) {
  const { data } = await api.delete(`/trade/${tradeId}`);
  return data;
}

export async function fetchTradeStats(): Promise<TradeStats> {
  const { data } = await api.get<TradeStats>('/trade/stats');
  return data;
}
