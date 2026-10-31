import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  /** highlight 模式：琥珀色描边强调 */
  highlight?: boolean;
  /** 标题栏右侧操作区（如「重新筛选」按钮） */
  action?: ReactNode;
}

export default function Card({ title, children, className = '', highlight = false, action }: CardProps) {
  const baseClasses = 'glass-card glass-card-hover overflow-hidden';
  const highlightClasses =
    'border-[rgba(255,159,67,0.55)] shadow-[0_10px_36px_-12px_rgba(255,159,67,0.45)] hover:shadow-[0_16px_40px_-12px_rgba(255,159,67,0.55)]';

  return (
    <div className={`${baseClasses} ${highlight ? highlightClasses : ''} ${className}`}>
      {title && (
        <div
          className={`flex items-center justify-between gap-3 border-b border-border px-5 py-3 ${highlight ? 'bg-[rgba(255,159,67,0.10)]' : ''}`}
        >
          <h3 className="text-sm font-bold text-text-primary tracking-wide">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}
