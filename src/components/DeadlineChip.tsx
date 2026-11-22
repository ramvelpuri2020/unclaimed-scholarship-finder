'use client';

import { useEffect, useState } from 'react';
import { CalendarDays, CheckCircle2, HelpCircle } from 'lucide-react';
import { deadlineText } from '@/lib/format';
import type { Program } from '@/lib/types';

export function DeadlineChip({ program }: { program: Program }) {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    setLabel(deadlineText(program));
  }, [program]);

  if (program.verification === 'unconfirmed') {
    return (
      <span className="inline-flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <CalendarDays size={13} aria-hidden="true" />
        Deadline not confirmed on the page
        <span className="inline-flex items-center gap-1 rounded-full bg-warn-tint px-2 py-0.5 text-[11px] font-semibold text-warn">
          <HelpCircle size={11} aria-hidden="true" />
          Check before applying
        </span>
      </span>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs text-muted">
      <CalendarDays size={13} aria-hidden="true" />
      {label ?? program.deadlineLabel ?? 'Date not stated'}
      <span className="inline-flex items-center gap-1 rounded-full bg-money-tint px-2 py-0.5 text-[11px] font-semibold text-money">
        <CheckCircle2 size={11} aria-hidden="true" />
        Verified on page
      </span>
    </span>
  );
}
