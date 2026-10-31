import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStockSearch } from '../../hooks/useStockSearch';
import { useAppStore } from '../../stores/appStore';
import type { StockSearchItem } from '../../api/types';

interface Props {
  /** sm = 顶栏紧凑版；lg = 首页 Hero 大搜索框 */
  variant?: 'sm' | 'lg';
  placeholder?: string;
  className?: string;
  limit?: number;
  /** 输入框 id，供外部（如 ⌘K 快捷键）聚焦 */
  inputId?: string;
}

/** 把 6 位代码补全为 ts_code（沪市 6 开头，其余深市） */
function normalizeCode(raw: string): string {
  const code = raw.trim().toUpperCase();
  if (/^\d{6}$/.test(code)) {
    return code.startsWith('6') ? `${code}.SH` : `${code}.SZ`;
  }
  return code;
}

/** 关键词高亮：命中片段用品牌色加粗 */
function Highlight({ text, keyword }: { text: string; keyword: string }) {
  if (!keyword) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(keyword.toLowerCase());
  if (idx < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <span className="text-brand-from font-bold">
        {text.slice(idx, idx + keyword.length)}
      </span>
      {text.slice(idx + keyword.length)}
    </>
  );
}

export default function StockSearchBox({
  variant = 'sm',
  placeholder = '输入代码 / 名称 / 拼音，如 600487、亨通、payh',
  className = '',
  limit = 10,
  inputId,
}: Props) {
  const navigate = useNavigate();
  const addSearchHistory = useAppStore((s) => s.addSearchHistory);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { items, isSearching } = useStockSearch(query, limit);

  // 点击组件外部关闭下拉
  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    return () => document.removeEventListener('mousedown', onDocMouseDown);
  }, []);

  const goto = (item: StockSearchItem) => {
    addSearchHistory(item.ts_code);
    setOpen(false);
    setQuery('');
    navigate(`/stock/${item.ts_code}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const code = normalizeCode(query);
    if (!code) return;
    setOpen(false);
    navigate(`/stock/${code}`);
  };

  const showPanel = open && query.trim().length > 0;
  const isLarge = variant === 'lg';

  const inputClasses = isLarge
    ? 'w-full rounded-xl border border-border bg-white/80 px-5 py-4 text-base text-text-primary placeholder-text-muted outline-none focus:border-brand-from focus:ring-4 focus:ring-brand-from/20 transition-all'
    : 'w-72 rounded-lg border border-border bg-white/80 px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-brand-from focus:ring-2 focus:ring-brand-from/25 transition-colors';

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <input
          id={inputId}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className={inputClasses}
        />
        <button
          type="submit"
          className={
            isLarge
              ? 'rounded-xl brand-gradient-bg px-6 py-4 text-base text-white font-bold shadow-[0_10px_30px_-10px_rgba(102,126,234,0.9)] hover:brightness-110 transition-all'
              : 'rounded-lg brand-gradient-bg px-3.5 py-1.5 text-sm text-white font-medium shadow-[0_6px_18px_-8px_rgba(102,126,234,0.9)] hover:brightness-110 transition-all'
          }
        >
          分析
        </button>
      </form>

      {showPanel && (
        <div className="glass-panel absolute top-full mt-2 left-0 right-0 z-50 max-h-80 overflow-y-auto animate-[fadeIn_120ms_ease-out]">
          {isSearching && items.length === 0 && (
            <div className="px-4 py-3 text-xs text-text-muted">搜索中...</div>
          )}

          {!isSearching && items.length === 0 && (
            <div className="px-4 py-3 text-xs text-text-muted">未找到匹配的股票</div>
          )}

          {items.map((item) => (
            <button
              key={item.ts_code}
              type="button"
              onClick={() => goto(item)}
              className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left cursor-pointer transition-colors hover:bg-[rgba(102,126,234,0.10)]"
            >
              <span className="flex items-center gap-3 min-w-0">
                <span className="font-mono text-xs text-text-secondary shrink-0">
                  <Highlight text={item.ts_code} keyword={query.trim()} />
                </span>
                <span className="text-sm font-medium text-text-primary truncate">
                  <Highlight text={item.name} keyword={query.trim()} />
                </span>
              </span>
              <span className="flex items-center gap-1.5 shrink-0">
                {item.industry && (
                  <span className="rounded-md bg-[rgba(52,152,219,0.12)] text-[#1f6fa8] border border-[rgba(52,152,219,0.3)] px-1.5 py-0.5 text-[10px]">
                    {item.industry}
                  </span>
                )}
                {item.market && (
                  <span className="rounded-md bg-[rgba(0,0,0,0.05)] text-text-secondary border border-[rgba(0,0,0,0.12)] px-1.5 py-0.5 text-[10px]">
                    {item.market}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
