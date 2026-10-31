import { useQuery } from '@tanstack/react-query';
import { fetchStockAnalysis, fetchKlineData, fetchCommentary } from '../api/stock';

export function useStockAnalysis(tsCode: string, days = 120) {
  return useQuery({
    queryKey: ['stock', tsCode, days],
    queryFn: () => fetchStockAnalysis(tsCode, days),
    enabled: !!tsCode,
    staleTime: 5 * 60 * 1000,
  });
}

export function useKlineData(tsCode: string, days = 120) {
  return useQuery({
    queryKey: ['kline', tsCode, days],
    queryFn: () => fetchKlineData(tsCode, days),
    enabled: !!tsCode,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCommentary(tsCode: string, days = 120) {
  return useQuery({
    queryKey: ['commentary', tsCode, days],
    queryFn: () => fetchCommentary(tsCode, days),
    enabled: !!tsCode,
    staleTime: 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    retry: 1,
  });
}
