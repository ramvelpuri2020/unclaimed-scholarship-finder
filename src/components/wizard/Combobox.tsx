'use client';

import * as React from 'react';
import { Check, Search } from 'lucide-react';
import { Input } from '@/components/shared/Input';
import { cn } from '@/lib/utils';

type ComboboxProps = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder?: string;
  helper?: string;
  error?: string;
  autoFocus?: boolean;
  onEnter?: () => void;
};

export function Combobox({
  label,
  value,
  onChange,
  options,
  placeholder = 'Search schools',
  helper = "Don't see your school? Type its name and choose 'Use…'.",
  error,
  autoFocus,
  onEnter,
}: ComboboxProps) {
  const [query, setQuery] = React.useState(value);
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const optionRefs = React.useRef<Array<HTMLButtonElement | null>>([]);
  const listId = React.useId();

  const term = query.trim();
  const matches = React.useMemo(
    () => options.filter((option) => option.toLowerCase().includes(term.toLowerCase())),
    [options, term],
  );
  const exact = matches.some((option) => option.toLowerCase() === term.toLowerCase());
  const items = React.useMemo(
    () => (term && !exact ? [...matches, `Use "${term}"`] : matches),
    [matches, term, exact],
  );

  React.useEffect(() => {
    if (active > items.length - 1) setActive(Math.max(items.length - 1, 0));
  }, [items.length, active]);

  React.useEffect(() => {
    optionRefs.current[active]?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  React.useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  function commit(option: string) {
    const chosen = option.startsWith('Use "') ? term : option;
    setQuery(chosen);
    onChange(chosen);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(0);
        return;
      }
      setActive((current) => Math.min(current + 1, items.length - 1));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(0);
        return;
      }
      setActive((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (open && items[active]) {
        commit(items[active]);
      } else {
        setOpen(false);
        onEnter?.();
      }
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === 'Tab') setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative w-full">
      <div className="relative">
        <Search
          size={18}
          aria-hidden="true"
          className="pointer-events-none absolute left-4 top-1/2 z-10 -translate-y-1/2 text-muted"
        />
        <Input
          autoFocus={autoFocus}
          label={label}
          error={error}
          value={query}
          placeholder={placeholder}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && items[active] ? `${listId}-option-${active}` : undefined}
          className="pl-11 pr-10"
          onFocus={() => {
            setOpen(true);
            setActive(0);
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            onChange('');
            setOpen(true);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
        />
        {value ? (
          <Check
            size={18}
            aria-hidden="true"
            className="pointer-events-none absolute right-4 top-1/2 z-10 -translate-y-1/2 text-money"
          />
        ) : null}
      </div>

      {open ? (
        <div
          id={listId}
          role="listbox"
          aria-label="Schools"
          className="absolute left-0 right-0 top-[calc(100%+8px)] z-30 max-h-[260px] overflow-y-auto rounded-2xl border border-border bg-white p-1 shadow-pop"
        >
          {items.length === 0 ? (
            <p className="px-3 py-2.5 text-sm text-muted">No schools found.</p>
          ) : (
            items.map((item, index) => (
              <button
                key={`${item}-${index}`}
                ref={(node) => {
                  optionRefs.current[index] = node;
                }}
                id={`${listId}-option-${index}`}
                type="button"
                role="option"
                aria-selected={active === index}
                tabIndex={-1}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(index)}
                onClick={() => commit(item)}
                className={cn(
                  'flex h-11 w-full items-center rounded-xl px-3 text-left text-sm text-ink',
                  active === index && 'bg-brand-tint',
                )}
              >
                <span className="truncate">{item}</span>
              </button>
            ))
          )}
        </div>
      ) : null}

      {helper ? <p className="mt-1.5 text-[13px] text-muted">{helper}</p> : null}
    </div>
  );
}
