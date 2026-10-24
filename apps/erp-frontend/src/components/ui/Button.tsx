import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader } from 'lucide-react';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  isLoading?: boolean;
  fullWidth?: boolean;
  leadingIcon?: ReactNode;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-white hover:bg-primary-hover',
  secondary:
    'border border-border-strong bg-surface text-text hover:bg-background',
  ghost: 'text-text-secondary hover:bg-background hover:text-text',
  danger: 'bg-danger text-white hover:brightness-95',
};

export function Button({
  variant = 'primary',
  isLoading = false,
  fullWidth = false,
  leadingIcon,
  disabled,
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    'inline-flex min-h-9 items-center justify-center gap-2 rounded-sm px-3.5 text-body font-semibold transition-colors',
    'focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:outline-none',
    'disabled:cursor-not-allowed disabled:opacity-60',
    VARIANT_CLASSES[variant],
    fullWidth ? 'w-full' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...rest}
    >
      {isLoading ? (
        <Loader className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : (
        leadingIcon
      )}
      {children}
    </button>
  );
}
