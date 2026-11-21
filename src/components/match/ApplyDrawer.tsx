'use client';

import { useEffect, useRef, useState } from 'react';
import { Copy, ExternalLink, Sparkles, X } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '@/lib/store';
import { Input } from '@/components/shared/Input';
import { Select } from '@/components/shared/Select';
import { Textarea } from '@/components/shared/Textarea';
import type { Program } from '@/lib/types';

const focusable =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

export function ApplyDrawer({
  program,
  onClose,
}: {
  program: Program | null;
  onClose: () => void;
}) {
  const profile = useStore((state) => state.profile);
  const drafts = useStore((state) => state.drafts);
  const setDraft = useStore((state) => state.setDraft);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [shown, setShown] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!program) return;
    const next: Record<string, string> = {};
    for (const field of program.formFields) {
      const draft = drafts[program.id]?.[field.id];
      const prefill =
        field.prefillKey && profile ? String(profile[field.prefillKey] ?? '') : '';
      next[field.id] = draft ?? prefill;
    }
    setValues(next);
    setErrors({});
    setShown(false);
    const frame = requestAnimationFrame(() => setShown(true));
    const focusFrame = requestAnimationFrame(() => closeRef.current?.focus());
    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(focusFrame);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [program?.id]);

  useEffect(() => {
    if (!program) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [program]);

  useEffect(() => {
    if (!program) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(focusable)).filter(
        (node) => node.offsetParent !== null,
      );
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [program, onClose]);

  if (!program) return null;

  function update(fieldId: string, value: string) {
    setValues((current) => ({ ...current, [fieldId]: value }));
    if (program) setDraft(program.id, fieldId, value);
    setErrors((current) => {
      if (!current[fieldId]) return current;
      const next = { ...current };
      delete next[fieldId];
      return next;
    });
  }

  function validate() {
    const next: Record<string, string> = {};
    for (const field of program!.formFields) {
      if (field.required && !(values[field.id] ?? '').trim()) {
        next[field.id] = 'This field is required';
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function copyDetails() {
    const lines = [
      program!.name,
      `Amount: ${program!.amountLabel}`,
      `Deadline: ${program!.deadline ?? program!.deadlineLabel ?? 'Rolling'}`,
      '',
      ...program!.formFields.map((field) => `${field.label}: ${values[field.id] || '—'}`),
    ];
    navigator.clipboard
      .writeText(lines.join('\n'))
      .then(() => toast.success('Application details copied'))
      .catch(() => toast.error('Could not copy details'));
  }

  function openOfficial() {
    if (!validate()) return;
    window.open(program!.url, '_blank', 'noopener,noreferrer');
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close application"
        onClick={onClose}
        className={`absolute inset-0 bg-ink/40 transition-opacity duration-300 ${shown ? 'opacity-100' : 'opacity-0'}`}
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="apply-drawer-title"
        className={`relative flex h-full w-full flex-col bg-white shadow-pop transition-transform duration-300 sm:w-[480px] ${
          shown ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="rounded-b-2xl bg-brand-tint p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-wider text-brand">Apply</p>
              <h2 id="apply-drawer-title" className="mt-1 truncate text-lg font-extrabold text-ink">
                {program.name}
              </h2>
              <p className="mt-1 text-sm font-bold text-gold-dark">{program.amountLabel}</p>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close application"
              className="grid size-9 shrink-0 place-items-center rounded-xl border border-border bg-white text-muted transition-colors hover:text-ink"
            >
              <X size={17} />
            </button>
          </div>
          <p className="mt-3 line-clamp-2 flex gap-1.5 text-sm text-ink">
            <Sparkles size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-brand" />
            {program.whyQualify}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          <p className="rounded-xl bg-bg p-3 text-sm leading-6 text-ink">
            <b>Next step:</b> {program.nextStep}
          </p>

          {program.formFields.length ? (
            <div className="mt-5 space-y-4">
              <p className="text-sm font-bold">Your details</p>
              {program.formFields.map((field) => {
                const error = errors[field.id];
                const common = {
                  label: field.required ? `${field.label} *` : field.label,
                  error,
                  value: values[field.id] ?? '',
                  onChange: (
                    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
                  ) => update(field.id, event.target.value),
                };
                if (field.type === 'textarea') {
                  return (
                    <Textarea
                      key={field.id}
                      {...common}
                      maxLength={field.maxChars}
                      rows={5}
                    />
                  );
                }
                if (field.type === 'select') {
                  return (
                    <Select key={field.id} {...common}>
                      <option value="">Select an option</option>
                      {field.options?.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </Select>
                  );
                }
                return <Input key={field.id} {...common} maxLength={field.maxChars} />;
              })}
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted">
              This one doesn&apos;t need a form. Follow the next step and keep your details handy.
            </p>
          )}
        </div>

        <div className="sticky bottom-0 flex items-center gap-2 border-t border-border bg-white p-4">
          <button
            type="button"
            onClick={copyDetails}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-border px-4 text-sm font-semibold text-ink transition-colors hover:border-brand"
          >
            <Copy size={16} />
            Copy details
          </button>
          <button
            type="button"
            onClick={openOfficial}
            className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-brand px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-dark"
          >
            Open official site
            <ExternalLink size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
