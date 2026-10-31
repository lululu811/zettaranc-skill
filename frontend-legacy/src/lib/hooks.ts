import { useEffect } from 'react';

interface ShortcutHandler {
  key: string;
  meta?: boolean;
  ctrl?: boolean;
  shift?: boolean;
  handler: () => void;
}

/**
 * 注册全局键盘快捷键(Cmd/Ctrl + key)
 * 当前用于 ⌘K 聚焦 Header 搜索框
 */
export function useGlobalShortcuts(shortcuts: ShortcutHandler[]) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // 忽略输入框 / textarea 内的按键
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        // 但 ⌘K 例外:任何页面都能唤起
        if (!(e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey))) return;
      }
      for (const s of shortcuts) {
        const matchesKey = e.key.toLowerCase() === s.key.toLowerCase();
        const matchesMeta = s.meta ? e.metaKey : !e.metaKey;
        const matchesCtrl = s.ctrl ? e.ctrlKey : !e.ctrlKey;
        const matchesShift = s.shift ? e.shiftKey : !e.shiftKey;
        if (matchesKey && matchesMeta && matchesCtrl && matchesShift) {
          e.preventDefault();
          s.handler();
          break;
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [shortcuts]);
}

/**
 * 监听视口宽度变化,自动收起 sidebar(< 768px)
 */
export function useResponsiveSidebar(breakpoint = 768) {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const apply = () => {
      const isNarrow = window.innerWidth < breakpoint;
      // 仅在用户未手动设置时生效:用 mediaQuery 监听,触发 setSidebarCollapsed
      // 这里通过 dispatch CustomEvent 让 Sidebar 监听
      if (isNarrow) {
        window.dispatchEvent(new CustomEvent('zg:narrow-screen'));
      }
    };
    apply();
    window.addEventListener('resize', apply);
    return () => window.removeEventListener('resize', apply);
  }, [breakpoint]);
}
