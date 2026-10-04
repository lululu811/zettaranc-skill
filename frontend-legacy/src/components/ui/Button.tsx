import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

const variantClasses = {
  primary: 'bg-accent-gold/20 text-accent-gold hover:bg-accent-gold/30',
  secondary: 'bg-bg-hover text-text-secondary hover:bg-bg-hover/80',
  ghost: 'text-text-secondary hover:bg-bg-hover hover:text-text-primary',
};

const sizeClasses = {
  sm: 'px-2 py-1 text-xs',
  md: 'px-3 py-1.5 text-sm',
  lg: 'px-4 py-2 text-base',
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
      className={`rounded-lg border border-border/50 font-medium transition-all duration-200 active:scale-95 focus:outline-none focus:ring-2 focus:ring-accent-gold/50 ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
