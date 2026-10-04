import api from './client';
import type { WatchlistList, WatchlistScan } from './types';

export async function fetchWatchlist(): Promise<WatchlistList> {
  const { data } = await api.get<WatchlistList>('/watchlist/');
  return data;
}

export async function addToWatchlist(tsCode: string, tags = '', notes = '') {
  const { data } = await api.post('/watchlist/', { ts_code: tsCode, tags, notes });
  return data;
}

export async function removeFromWatchlist(tsCode: string) {
  const { data } = await api.delete(`/watchlist/${tsCode}`);
  return data;
}

export async function scanWatchlist(): Promise<WatchlistScan> {
  const { data } = await api.post<WatchlistScan>('/watchlist/scan');
  return data;
}

export async function fetchReport(): Promise<{ report: string }> {
  const { data } = await api.get<{ report: string }>('/watchlist/report');
  return data;
}
