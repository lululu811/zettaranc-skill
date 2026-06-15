interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}

const variantClasses = {
  default: 'bg-bg-hover text-text-secondary',
  success: 'bg-accent-green/20 text-accent-green',
  warning: 'bg-accent-gold/20 text-accent-gold',
  danger: 'bg-accent-red/20 text-accent-red',
  info: 'bg-accent-blue/20 text-accent-blue',
};

export default function Badge({ children, variant = 'default' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium border border-current/20 ${variantClasses[variant]}`}>
      {children}
    </span>
  );
}
