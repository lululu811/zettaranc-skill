import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ScreenResult } from '../api/types';

export interface ScreenResultItem {
  ts_code: string;
  name: string;
  score: number;
  rating: string;
}

/** 最近一次选股的「条件 + 结果」快照：刷新/返回后仍能还原列表 */
export interface ScreenSnapshot {
  /** 条件指纹（策略+扫描数+返回数+参数覆盖），用于判断快照是否仍然匹配当前条件 */
  key: string;
  strategy: string;
  limit: number;
  top: number;
  overrides: Record<string, Record<string, number>>;
  result: ScreenResult;
  ranAt: number;
}

interface AppState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  searchCode: string;
  setSearchCode: (code: string) => void;
  searchHistory: string[];
  addSearchHistory: (code: string) => void;
  clearSearchHistory: () => void;
  /** 最近一次选股结果：进入详情页后在左侧以列表展示，便于逐个翻看 */
  screenResults: ScreenResultItem[];
  setScreenResults: (items: ScreenResultItem[]) => void;
  clearScreenResults: () => void;
  /** 选股页快照（持久化到 localStorage，刷新/返回不丢结果） */
  screenSnapshot: ScreenSnapshot | null;
  setScreenSnapshot: (snap: ScreenSnapshot) => void;
  clearScreenSnapshot: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      searchCode: '',
      setSearchCode: (code) => set({ searchCode: code }),
      searchHistory: [],
      addSearchHistory: (code) =>
        set((s) => {
          const next = [code, ...s.searchHistory.filter((c) => c !== code)].slice(0, 8);
          return { searchHistory: next };
        }),
      clearSearchHistory: () => set({ searchHistory: [] }),
      screenResults: [],
      setScreenResults: (items) => set({ screenResults: items.slice(0, 100) }),
      clearScreenResults: () => set({ screenResults: [] }),
      screenSnapshot: null,
      // 只存前 200 条，避免 localStorage 配额被大结果集撑爆
      setScreenSnapshot: (snap) =>
        set({
          screenSnapshot: {
            ...snap,
            result: { ...snap.result, stocks: snap.result.stocks.slice(0, 200) },
          },
        }),
      clearScreenSnapshot: () => set({ screenSnapshot: null }),
    }),
    {
      name: 'zg-app-store',
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        searchHistory: s.searchHistory,
        screenResults: s.screenResults,
        screenSnapshot: s.screenSnapshot,
      }),
    },
  ),
);
