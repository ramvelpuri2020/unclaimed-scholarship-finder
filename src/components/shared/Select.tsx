'use client';

import * as React from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

type FieldExtras = {
  label?: string;
  helper?: string;
  error?: string;
  containerClassName?: string;
};

export type SelectProps = React.ComponentProps<'select'> & FieldExtras;

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, helper, error, className, containerClassName, id, children, ...props },
  ref,
) {
  const generatedId = React.useId();
  const selectId = id ?? generatedId;
  const describedBy = error ? `${selectId}-error` : helper ? `${selectId}-helper` : undefined;

  return (
    <div className={cn('w-full', containerClassName)}>
      {label ? (
        <label htmlFor={selectId} className="mb-2 block text-sm font-semibold text-ink">
          {label}
        </label>
      ) : null}
      <div className="relative">
        <select
          ref={ref}
          id={selectId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            'h-12 w-full appearance-none rounded-xl border bg-white py-0 pl-4 pr-10 text-base text-ink outline-none transition',
            error
              ? 'border-danger focus:border-danger focus:ring-4 focus:ring-danger/15'
              : 'border-border focus:border-brand focus:ring-4 focus:ring-brand/15',
            'disabled:cursor-not-allowed disabled:bg-bg disabled:opacity-100',
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          size={18}
          aria-hidden="true"
          className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-muted"
        />
      </div>
      {error ? (
        <p id={`${selectId}-error`} className="mt-1.5 text-[13px] font-medium text-danger">
          {error}
        </p>
      ) : helper ? (
        <p id={`${selectId}-helper`} className="mt-1.5 text-[13px] text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
});
