import { daysUntil } from '@/lib/format';
import type { Program } from '@/lib/types';

const MAX_DAYS = 45;

function urgency(days: number) {
  if (days <= 7) return 'bg-danger';
  if (days <= 21) return 'bg-warn';
  return 'bg-brand';
}

export function DeadlineTimeline({ programs }: { programs: Program[] }) {
  const dated = programs
    .map((program) => ({ program, days: daysUntil(program.deadline) }))
    .filter((item): item is { program: Program; days: number } => item.days !== null && item.days >= 0 && item.days <= MAX_DAYS)
    .sort((a, b) => a.days - b.days);
  const undated = programs.filter((program) => !program.deadline);

  return (
    <section className="rounded-hero border border-border bg-white p-5 shadow-card">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-bold">Deadline timeline</h2>
          <p className="mt-1 text-xs text-muted">Next 45 days</p>

          <div className="relative mt-8 h-14">
            <div className="absolute inset-x-0 top-2 h-px bg-border" />
            {dated.map(({ program, days }) => {
              const left = Math.min(Math.max((days / MAX_DAYS) * 100, 2), 98);
              const tooltipPosition =
                left < 18 ? 'left-0' : left > 82 ? 'right-0' : 'left-1/2 -translate-x-1/2';
              return (
                <button
                  key={program.id}
                  type="button"
                  aria-label={`${program.name}, ${program.amountLabel}, ${days} days left`}
                  className="group absolute top-2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full p-1.5 focus-visible:outline-none"
                  style={{ left: `${left}%` }}
                >
                  <span className={`block size-3 rounded-full ring-2 ring-white ${urgency(days)}`} />
                  <span
                    className={`pointer-events-none absolute bottom-full z-20 mb-2 hidden w-[220px] rounded-xl bg-ink px-3 py-2 text-left text-xs text-white shadow-pop group-hover:block group-focus-visible:block ${tooltipPosition}`}
                  >
                    <span className="block truncate font-semibold">{program.name}</span>
                    <span className="mt-0.5 block text-white/70">
                      {program.amountLabel} · {program.deadline ?? ''} · {days === 0 ? 'due today' : `${days} days left`}
                    </span>
                  </span>
                </button>
              );
            })}
            <span className="absolute left-0 top-6 text-[11px] text-muted">0d</span>
            <span className="absolute right-0 top-6 text-[11px] text-muted">45d</span>
          </div>

          {dated.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No deadlines in the next 45 days.</p>
          ) : null}
        </div>

        <div className="shrink-0 sm:max-w-[200px]">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">No deadline</p>
          {undated.length ? (
            <ul className="mt-2 space-y-1">
              {undated.map((program) => (
                <li key={program.id} className="truncate text-xs text-muted" title={program.name}>
                  {program.name}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted">—</p>
          )}
        </div>
      </div>
    </section>
  );
}
