import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AppState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  searchCode: string;
  setSearchCode: (code: string) => void;
  searchHistory: string[];
  addSearchHistory: (code: string) => void;
  clearSearchHistory: () => void;
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
    }),
    {
      name: 'zg-app-store',
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, searchHistory: s.searchHistory }),
    },
  ),
);
