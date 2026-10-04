import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { useAppStore } from '../../stores/appStore';
import { useGlobalShortcuts } from '../../lib/hooks';
import StockSearchBox from '../stock/StockSearchBox';

const SEARCH_INPUT_ID = 'global-stock-search';

export default function Header() {
  const location = useLocation();
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);

  const isDashboard = location.pathname === '/';

  // ⌘K / Ctrl+K 聚焦搜索框
  useGlobalShortcuts(
    useMemo(
      () => [
        {
          key: 'k',
          meta: true,
          handler: () => document.getElementById(SEARCH_INPUT_ID)?.focus(),
        },
        {
          key: 'k',
          ctrl: true,
          handler: () => document.getElementById(SEARCH_INPUT_ID)?.focus(),
        },
      ],
      [],
    ),
  );

  return (
    <header className="relative flex h-14 items-center justify-between border-b border-border/60 bg-white/60 backdrop-blur-xl px-6 z-40 sticky top-0">
      {/* 底部品牌渐变高光条 */}
      <div className="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-brand-from via-brand-to to-brand-from opacity-80" />
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          className="text-text-muted hover:text-text-primary transition-colors px-1"
        >
          {sidebarCollapsed ? '☰' : '⟨'}
        </button>
        {/* 全局搜索框：Dashboard 页用 Hero 搜索框，这里隐藏避免重复 */}
        {!isDashboard && <StockSearchBox variant="sm" inputId={SEARCH_INPUT_ID} />}
      </div>
      <div className="text-xs text-text-muted flex items-center gap-3">
        {!isDashboard && (
          <kbd className="hidden md:inline rounded border border-border/60 bg-white/70 px-1.5 py-0.5 text-[10px] text-text-muted font-mono">⌘K</kbd>
        )}
        <span>Z哥量化工具</span>
      </div>
    </header>
  );
}
