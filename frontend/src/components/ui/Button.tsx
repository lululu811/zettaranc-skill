import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

const variantClasses = {
  primary:
    'brand-gradient-bg text-white border-transparent shadow-[0_6px_18px_-8px_rgba(102,126,234,0.9)] hover:brightness-110',
  secondary: 'bg-white/70 text-text-secondary border-border hover:bg-white hover:text-text-primary',
  ghost: 'text-text-secondary border-transparent hover:bg-white/70 hover:text-text-primary',
};

const sizeClasses = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-1.5 text-sm',
  lg: 'px-5 py-2 text-base',
};

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  ...props
}: ButtonProps) {
  return (
    <button
      className={`rounded-lg border font-medium transition-all duration-200 active:scale-95 focus:outline-none focus:ring-2 focus:ring-brand-from/40 ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
