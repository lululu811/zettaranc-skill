import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchStockSearch } from '../api/stock';
import type { StockSearchResult } from '../api/types';

/** 输入防抖：避免逐字符请求后端 */
function useDebounced<T>(value: T, delay = 200): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/**
 * 股票联想搜索
 * 关键词为空时不发请求；股票清单稳定，缓存 30 分钟复用
 */
export function useStockSearch(query: string, limit = 10) {
  const keyword = useDebounced(query.trim(), 200);

  const result = useQuery<StockSearchResult>({
    queryKey: ['stockSearch', keyword, limit],
    queryFn: () => fetchStockSearch(keyword, limit),
    enabled: keyword.length > 0,
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });

  return {
    ...result,
    keyword,
    items: result.data?.items ?? [],
    total: result.data?.total ?? 0,
    /** 正在输入（防抖未落定）也视为加载中，避免面板闪烁 */
    isSearching: keyword.length > 0 && (result.isLoading || result.isFetching || keyword !== query.trim()),
  };
}
