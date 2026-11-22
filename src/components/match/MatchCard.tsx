'use client';

import { ExternalLink, Heart, ShieldCheck, Sparkles } from 'lucide-react';
import { useStore } from '@/lib/store';
import { formatMoney } from '@/lib/format';
import { MatchBadge } from '@/components/MatchBadge';
import { DeadlineChip } from '@/components/DeadlineChip';
import type { Program } from '@/lib/types';

export function MatchCard({ program }: { program: Program }) {
  const saved = useStore((state) => state.savedIds.includes(program.id));
  const toggle = useStore((state) => state.toggleSaved);
  const applyUrl = program.applyUrl || program.url;
  const applyLabel = program.applyUrlIsAggregator ? 'Open source page' : 'Apply on official site';
  const evidence = Array.from(new Set([program.deadlineQuote, ...program.evidenceQuotes].filter(Boolean))) as string[];

  return (
    <article className="card-surface p-4 transition hover:shadow-md md:p-5">
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex w-full shrink-0 flex-col items-center justify-center rounded-2xl bg-brand-tint p-3 text-center sm:w-36">
          <p className="text-xl font-extrabold leading-tight text-gold-dark">
            {program.amountMax ? formatMoney(program.amountMax) : program.amountLabel}
          </p>
          <span className="mt-2 block">
            <MatchBadge confidence={program.confidence} />
          </span>
          <span className="mt-2 text-[11px] font-bold uppercase tracking-wider text-brand">{program.fit} fit</span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <DeadlineChip program={program} />
            <span className="rounded-full bg-bg px-3 py-1 text-xs font-semibold text-ink">{program.provider}</span>
            <span className="rounded-full bg-brand-tint px-3 py-1 text-xs font-semibold text-brand">
              {program.sourceSite}
            </span>
          </div>

          {program.verification === 'unconfirmed' ? (
            <p className="mt-2 inline-flex items-center rounded-full bg-warn-tint px-2.5 py-1 text-[11px] font-bold text-warn">
              Deadline not confirmed on the page — check before applying
            </p>
          ) : null}

          <h3 className="mt-2 text-[18px] font-bold leading-snug">
            <a href={program.url} target="_blank" rel="noreferrer" className="hover:text-brand hover:underline">
              {program.name}
            </a>
          </h3>

          <p className="mt-2 flex gap-1.5 text-sm leading-6 text-ink">
            <Sparkles size={15} aria-hidden="true" className="mt-1 shrink-0 text-brand" />
            <span className="line-clamp-3">{program.whyQualify}</span>
          </p>

          {program.resumeEvidence?.length ? (
            <div className="mt-3 rounded-xl bg-brand-tint/60 p-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-brand">Why it fits you</p>
              <ul className="mt-1 space-y-1">
                {program.resumeEvidence.map((line) => (
                  <li key={line} className="flex gap-1.5 text-xs leading-5 text-ink">
                    <span aria-hidden="true">•</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {program.matchedOn.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {program.matchedOn.map((fact) => (
                <span key={fact} className="rounded-full bg-money-tint px-2.5 py-1 text-xs font-medium text-money">
                  {fact}
                </span>
              ))}
            </div>
          ) : null}

          {program.gaps.length ? (
            <p className="mt-3 text-xs leading-5 text-muted">
              <b className="text-ink">Check:</b> {program.gaps.join(' · ')}
            </p>
          ) : null}

          <div className="mt-3 flex flex-wrap gap-1.5">
            {program.requirements.slice(0, 3).map((requirement) => (
              <span key={requirement} className="rounded-full bg-bg px-2.5 py-1 text-xs text-ink">
                {requirement}
              </span>
            ))}
          </div>

          <details className="mt-3 rounded-xl border border-border bg-bg/60 p-3">
            <summary className="cursor-pointer text-xs font-bold text-brand">Evidence</summary>
            <div className="mt-2 space-y-2">
              {evidence.length ? (
                evidence.slice(0, 6).map((quote) => (
                  <blockquote key={quote} className="border-l-2 border-brand/30 pl-2 text-xs leading-5 text-muted">
                    “{quote}”
                  </blockquote>
                ))
              ) : (
                <p className="text-xs text-muted">No verbatim quote was captured for this program.</p>
              )}
              <a
                href={program.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
              >
                Open source page <ExternalLink size={12} />
              </a>
            </div>
          </details>

          <div className="mt-4 flex items-end justify-between gap-3">
            <p className="line-clamp-2 min-w-0 flex-1 text-sm text-muted">
              <b className="text-ink">Next step:</b> {program.nextStep}
            </p>
            <div className="flex shrink-0 items-center gap-2">
              <a
                href={applyUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl bg-brand px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-dark"
              >
                {applyLabel}
                <ExternalLink size={14} />
              </a>
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
          <p className="mt-2 flex items-center gap-1 text-[11px] text-muted">
            <ShieldCheck size={12} /> Deadline and eligibility details are verified against the source page.
          </p>
        </div>
      </div>
    </article>
  );
}
