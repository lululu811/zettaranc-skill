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
      className={`flex flex-col border-r border-border/40 bg-bg-secondary/40 backdrop-blur-xl z-50 overflow-hidden transition-[width] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className="flex h-12 items-center gap-2 border-b border-border px-3 shrink-0">
        <span className="text-lg text-accent-gold shrink-0">Z</span>
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
              `flex items-center gap-3 px-3 py-2.5 text-sm transition-colors whitespace-nowrap ${
                isActive
                  ? 'bg-bg-hover text-accent-gold border-r-2 border-accent-gold'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
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
