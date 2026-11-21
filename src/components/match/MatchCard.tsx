'use client';

import { Heart, Sparkles } from 'lucide-react';
import { useStore } from '@/lib/store';
import { formatMoney } from '@/lib/format';
import { MatchBadge } from '@/components/MatchBadge';
import { DeadlineChip } from '@/components/DeadlineChip';
import type { Program } from '@/lib/types';

export function MatchCard({
  program,
  onApply,
}: {
  program: Program;
  onApply: (program: Program, trigger: HTMLElement) => void;
}) {
  const saved = useStore((state) => state.savedIds.includes(program.id));
  const toggle = useStore((state) => state.toggleSaved);

  const tint =
    program.confidence >= 0.85
      ? 'bg-money-tint'
      : program.confidence >= 0.65
        ? 'bg-brand-tint'
        : 'bg-warn-tint';

  return (
    <article className="card-surface p-4 transition hover:shadow-md md:p-5">
      <div className="flex gap-4">
        <div className={`flex w-36 shrink-0 flex-col items-center justify-center rounded-2xl p-3 text-center ${tint}`}>
          <p className="text-xl font-extrabold leading-tight text-gold-dark">
            {program.amountMax !== null ? formatMoney(program.amountMax) : program.amountLabel}
          </p>
          <span className="mt-2 block">
            <MatchBadge confidence={program.confidence} />
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <DeadlineChip program={program} />
            <span className="rounded-full bg-brand-tint px-3 py-1 text-xs font-semibold text-brand">
              {program.sourceSite}
            </span>
            {program.fromCache ? (
              <span className="rounded-full bg-warn-tint px-2.5 py-1 text-xs font-semibold text-warn">Cached</span>
            ) : null}
          </div>

          <h3 className="mt-2 text-[18px] font-bold leading-snug">{program.name}</h3>

          <p className="mt-2 line-clamp-2 flex gap-1.5 text-sm leading-6 text-ink">
            <Sparkles size={15} aria-hidden="true" className="mt-1 shrink-0 text-brand" />
            <span className="line-clamp-2">{program.whyQualify}</span>
          </p>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {program.requirements.slice(0, 3).map((requirement) => (
              <span key={requirement} className="rounded-full bg-bg px-2.5 py-1 text-xs text-ink">
                {requirement}
              </span>
            ))}
          </div>

          <div className="mt-4 flex items-end justify-between gap-3">
            <p className="line-clamp-2 min-w-0 flex-1 text-sm text-muted">
              <b className="text-ink">Next step:</b> {program.nextStep}
            </p>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={(event) => onApply(program, event.currentTarget)}
                className="inline-flex h-10 items-center justify-center rounded-xl bg-brand px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-dark"
              >
                Apply
              </button>
              <button
                type="button"
                aria-label={saved ? 'Remove saved match' : 'Save match'}
                aria-pressed={saved}
                onClick={() => toggle(program.id)}
                className={`grid size-10 place-items-center rounded-xl border transition-colors ${
                  saved ? 'border-danger bg-danger-tint text-danger' : 'border-border text-muted hover:border-brand'
                }`}
              >
                <Heart size={17} fill={saved ? 'currentColor' : 'none'} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
