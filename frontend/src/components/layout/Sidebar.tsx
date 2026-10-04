import { useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import { NAV_ITEMS } from '../../lib/constants';
import { useAppStore } from '../../stores/appStore';
import { useResponsiveSidebar } from '../../lib/hooks';

export default function Sidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed);
  const initialAutoApplied = useRef(false);

  // 监听窄屏事件自动收起(< 768px),且只触发一次
  useResponsiveSidebar(768);
  useEffect(() => {
    const onNarrow = () => {
      if (!initialAutoApplied.current) {
        setSidebarCollapsed(true);
        initialAutoApplied.current = true;
      } else if (window.innerWidth >= 768) {
        // 回到宽屏:还原
        setSidebarCollapsed(false);
        initialAutoApplied.current = false;
      }
    };
    window.addEventListener('zg:narrow-screen', onNarrow);
    window.addEventListener('resize', onNarrow);
    return () => {
      window.removeEventListener('zg:narrow-screen', onNarrow);
      window.removeEventListener('resize', onNarrow);
    };
  }, [setSidebarCollapsed]);

  return (
    <aside
      className={`glass-bar flex flex-col z-50 overflow-hidden transition-[width] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className="flex h-14 items-center gap-2 border-b border-border/60 px-3 shrink-0">
        <span className="text-lg font-bold brand-gradient-text shrink-0">Z</span>
        {!collapsed && (
          <span className="text-sm font-bold text-text-primary whitespace-nowrap">哥量化</span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 text-sm transition-all duration-200 whitespace-nowrap ${
                isActive
                  ? 'mx-2 my-0.5 rounded-xl brand-gradient-bg text-white font-medium shadow-[0_8px_20px_-10px_rgba(102,126,234,0.95)]'
                  : 'text-text-secondary hover:bg-[rgba(102,126,234,0.10)] hover:text-brand-from rounded-xl mx-2 my-0.5'
              }`
            }
          >
            <span className="text-base shrink-0">{item.icon}</span>
            {!collapsed && <span className="truncate">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="border-t border-border p-3 text-xs text-text-muted shrink-0">
          v1.0.0
        </div>
      )}
    </aside>
  );
}
