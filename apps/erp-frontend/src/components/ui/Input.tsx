import { useId, type ComponentPropsWithRef, type ReactNode } from 'react';

export interface InputProps extends ComponentPropsWithRef<'input'> {
  label?: string;
  error?: string;
  hint?: string;
  leadingIcon?: ReactNode;
}

export function Input({
  label,
  error,
  hint,
  leadingIcon,
  id,
  className = '',
  ref,
  ...rest
}: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') ||
    undefined;

  const inputClasses = [
    'h-9 w-full rounded-sm border bg-surface px-3 text-body text-text placeholder:text-text-muted',
    'transition-colors focus:border-primary focus:ring-2 focus:ring-primary/25 focus:outline-none',
    'disabled:cursor-not-allowed disabled:bg-background disabled:text-text-muted',
    leadingIcon ? 'pl-9' : '',
    error ? 'border-danger' : 'border-border-strong',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="flex flex-col gap-1.5">
      {label ? (
        <label htmlFor={inputId} className="text-body text-text font-semibold">
          {label}
        </label>
      ) : null}
      <div className="relative">
        {leadingIcon ? (
          <span className="text-text-muted pointer-events-none absolute top-1/2 left-3 -translate-y-1/2">
            {leadingIcon}
          </span>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          className={inputClasses}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...rest}
        />
      </div>
      {error ? (
        <p
          id={errorId}
          role="alert"
          className="text-body-sm text-danger font-medium"
        >
          {error}
        </p>
      ) : null}
      {hint && !error ? (
        <p id={hintId} className="text-body-sm text-text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
