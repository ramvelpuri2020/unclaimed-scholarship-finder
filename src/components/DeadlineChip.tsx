import { CalendarDays } from 'lucide-react';
import { deadlineText } from '@/lib/format';
import type { Program } from '@/lib/types';

export function DeadlineChip({ program }: { program: Program }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" suppressHydrationWarning>
      <CalendarDays size={13} aria-hidden="true" />
      {deadlineText(program)}
    </span>
  );
}
