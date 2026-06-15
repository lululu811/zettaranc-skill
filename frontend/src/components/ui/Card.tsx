import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  /** highlight 模式：金色边框强调（用于 Hero 卡片已自带样式，此处备用） */
  highlight?: boolean;
}

export default function Card({ title, children, className = '', highlight = false }: CardProps) {
  const baseClasses = 'rounded-xl border border-border/40 bg-bg-card backdrop-blur-xl transition-all duration-300 hover:border-border/80 hover:-translate-y-1 hover:shadow-2xl hover:shadow-black/50';
  const highlightClasses = 'border-accent-gold/40 bg-gradient-to-br from-bg-card to-[rgba(245,158,11,0.05)] shadow-[0_0_30px_-15px_rgba(245,158,11,0.3)] hover:shadow-[0_0_40px_-15px_rgba(245,158,11,0.4)]';

  return (
    <div className={`${baseClasses} ${highlight ? highlightClasses : ''} ${className}`}>
      {title && (
        <div className={`border-b border-border/30 px-5 py-3 ${highlight ? 'bg-gradient-to-r from-accent-gold/[0.06] to-transparent' : ''}`}>
          <h3 className="text-xs font-bold text-text-primary tracking-[0.15em] uppercase">{title}</h3>
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}
