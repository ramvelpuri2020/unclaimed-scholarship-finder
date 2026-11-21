'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

type FieldExtras = {
  label?: string;
  helper?: string;
  error?: string;
  containerClassName?: string;
};

export type InputProps = React.ComponentProps<'input'> & FieldExtras;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, helper, error, className, containerClassName, id, ...props },
  ref,
) {
  const generatedId = React.useId();
  const inputId = id ?? generatedId;
  const describedBy = error ? `${inputId}-error` : helper ? `${inputId}-helper` : undefined;

  return (
    <div className={cn('w-full', containerClassName)}>
      {label ? (
        <label htmlFor={inputId} className="mb-2 block text-sm font-semibold text-ink">
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          'h-12 w-full rounded-xl border bg-white px-4 text-base text-ink outline-none transition',
          'placeholder:text-[#6B7690] placeholder:opacity-70',
          '[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none',
          error
            ? 'border-danger focus:border-danger focus:ring-4 focus:ring-danger/15'
            : 'border-border focus:border-brand focus:ring-4 focus:ring-brand/15',
          'disabled:cursor-not-allowed disabled:bg-bg disabled:opacity-100',
          className,
        )}
        {...props}
      />
      {error ? (
        <p id={`${inputId}-error`} className="mt-1.5 text-[13px] font-medium text-danger">
          {error}
        </p>
      ) : helper ? (
        <p id={`${inputId}-helper`} className="mt-1.5 text-[13px] text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
});
