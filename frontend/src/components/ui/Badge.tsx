interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}

// 浅色底上的徽章：低饱和背景 + 加深的文字色，保证对比度
const variantClasses = {
  default: 'bg-[rgba(0,0,0,0.05)] text-text-secondary border-[rgba(0,0,0,0.12)]',
  success: 'bg-[rgba(46,204,113,0.14)] text-[#1e8449] border-[rgba(46,204,113,0.35)]',
  warning: 'bg-[rgba(255,159,67,0.16)] text-[#b9770e] border-[rgba(255,159,67,0.38)]',
  danger: 'bg-[rgba(231,76,60,0.14)] text-[#b93221] border-[rgba(231,76,60,0.35)]',
  info: 'bg-[rgba(52,152,219,0.14)] text-[#1f6fa8] border-[rgba(52,152,219,0.35)]',
};

export default function Badge({ children, variant = 'default' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium border ${variantClasses[variant]}`}
    >
      {children}
    </span>
  );
}
