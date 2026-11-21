'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

type FieldExtras = {
  label?: string;
  helper?: string;
  error?: string;
  containerClassName?: string;
};

export type TextareaProps = React.ComponentProps<'textarea'> & FieldExtras;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, helper, error, className, containerClassName, id, ...props },
  ref,
) {
  const generatedId = React.useId();
  const textareaId = id ?? generatedId;
  const describedBy = error ? `${textareaId}-error` : helper ? `${textareaId}-helper` : undefined;

  return (
    <div className={cn('w-full', containerClassName)}>
      {label ? (
        <label htmlFor={textareaId} className="mb-2 block text-sm font-semibold text-ink">
          {label}
        </label>
      ) : null}
      <textarea
        ref={ref}
        id={textareaId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          'min-h-[120px] w-full rounded-xl border bg-white px-4 py-3 text-base text-ink outline-none transition',
          'placeholder:text-[#6B7690] placeholder:opacity-70',
          error
            ? 'border-danger focus:border-danger focus:ring-4 focus:ring-danger/15'
            : 'border-border focus:border-brand focus:ring-4 focus:ring-brand/15',
          'disabled:cursor-not-allowed disabled:bg-bg disabled:opacity-100',
          className,
        )}
        {...props}
      />
      {error ? (
        <p id={`${textareaId}-error`} className="mt-1.5 text-[13px] font-medium text-danger">
          {error}
        </p>
      ) : helper ? (
        <p id={`${textareaId}-helper`} className="mt-1.5 text-[13px] text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
});
