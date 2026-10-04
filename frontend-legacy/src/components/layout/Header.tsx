import { useState, useRef, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppStore } from '../../stores/appStore';
import { useGlobalShortcuts } from '../../lib/hooks';

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const searchHistory = useAppStore((s) => s.searchHistory);
  const addSearchHistory = useAppStore((s) => s.addSearchHistory);
  const [input, setInput] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const isDashboard = location.pathname === '/';

  // ⌘K / Ctrl+K 聚焦搜索框
  useGlobalShortcuts(
    useMemo(
      () => [
        {
          key: 'k',
          meta: true,
          handler: () => inputRef.current?.focus(),
        },
        {
          key: 'k',
          ctrl: true,
          handler: () => inputRef.current?.focus(),
        },
      ],
      [],
    ),
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const code = input.trim();
    if (!code) return;
    // 自动补全后缀
    let tsCode = code.toUpperCase();
    if (/^\d{6}$/.test(tsCode)) {
      tsCode = tsCode.startsWith('6') ? `${tsCode}.SH` : `${tsCode}.SZ`;
    }
    addSearchHistory(tsCode);
    navigate(`/stock/${tsCode}`);
    setInput('');
    setHistoryOpen(false);
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-border/40 bg-bg-secondary/60 backdrop-blur-xl px-6 z-40 sticky top-0">
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          className="text-text-muted hover:text-text-primary transition-colors px-1"
        >
          {sidebarCollapsed ? '☰' : '⟨'}
        </button>
        {/* 全局搜索框:Dashboard 页用 Hero 搜索框,这里隐藏避免重复 */}
        {!isDashboard && (
          <form onSubmit={handleSearch} className="flex items-center gap-2 relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={() => setHistoryOpen(true)}
              onBlur={() => setTimeout(() => setHistoryOpen(false), 150)}
              placeholder="输入股票代码，如 600487 或 600487.SH (⌘K)"
              className="w-72 rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold transition-colors"
            />
            {historyOpen && searchHistory.length > 0 && (
              <div className="absolute top-full mt-1 left-0 w-72 rounded-md border border-border bg-bg-secondary shadow-lg z-50 overflow-hidden">
                <div className="px-3 py-1.5 text-xs text-text-muted border-b border-border/40 flex items-center justify-between">
                  <span>最近查询</span>
                  <button
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); useAppStore.getState().clearSearchHistory(); }}
                    className="text-text-muted hover:text-accent-red transition-colors"
                  >
                    清除
                  </button>
                </div>
                {searchHistory.slice(0, 6).map((code) => (
                  <button
                    key={code}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setInput(code);
                      navigate(`/stock/${code}`);
                      setInput('');
                      setHistoryOpen(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-sm font-mono text-text-secondary hover:bg-bg-hover hover:text-accent-gold transition-colors"
                  >
                    {code}
                  </button>
                ))}
              </div>
            )}
            <button
              type="submit"
              className="rounded bg-accent-gold/20 px-3 py-1.5 text-sm text-accent-gold hover:bg-accent-gold/30 transition-colors"
            >
              分析
            </button>
          </form>
        )}
      </div>
      <div className="text-xs text-text-muted flex items-center gap-3">
        {!isDashboard && (
          <kbd className="hidden md:inline rounded border border-border/60 bg-bg-primary px-1.5 py-0.5 text-[10px] text-text-muted font-mono">⌘K</kbd>
        )}
        <span>Z哥量化工具</span>
      </div>
    </header>
  );
}
