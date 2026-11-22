'use client';

import Link from 'next/link';
import { TrendingUp } from 'lucide-react';
import { useStore } from '@/lib/store';
import { useHydrated } from '@/lib/useHydrated';
import { formatDate, formatMoney } from '@/lib/format';

export default function FutureMePage() {
  const hydrated = useHydrated();
  const programs = useStore((state) => state.programs);

  const verified = programs.filter((program) => program.verification !== 'unconfirmed');
  const total = verified.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);
  const timeline = verified
    .filter((program) => program.deadline)
    .sort((a, b) => (a.deadline ?? '').localeCompare(b.deadline ?? ''));

  if (!hydrated) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-8 w-56 animate-pulse rounded-xl bg-bg" />
        <section className="card-surface p-8 text-center text-sm text-muted">Loading your plan…</section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section>
        <h1 className="flex items-center gap-2 text-2xl font-extrabold">
          <TrendingUp size={22} className="text-brand" /> Future me
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
          The funding your current matches could put behind next year, with the deadlines that make it
          real.
        </p>
      </section>

      {verified.length === 0 ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">Nothing to project yet</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">
            {programs.length
              ? 'Your current hunt has no award with a confirmed deadline. Open Matches to review the ones that still need a date check.'
              : 'Run a hunt and your confirmed awards become a funding plan here.'}
          </p>
          <Link href={programs.length ? '/matches' : '/start'} className="btn-primary mt-5">
            {programs.length ? 'Review matches' : 'Start a hunt'}
          </Link>
        </section>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-3">
            <div className="card-surface p-5">
              <p className="text-xs font-bold uppercase tracking-wider text-muted">Funding in play</p>
              <p className="mt-2 text-2xl font-extrabold text-money">
                {total > 0 ? formatMoney(total) : 'Amounts vary'}
              </p>
            </div>
            <div className="card-surface p-5">
              <p className="text-xs font-bold uppercase tracking-wider text-muted">Confirmed awards</p>
              <p className="mt-2 text-2xl font-extrabold">{verified.length}</p>
            </div>
            <div className="card-surface p-5">
              <p className="text-xs font-bold uppercase tracking-wider text-muted">Next deadline</p>
              <p className="mt-2 text-lg font-extrabold">
                {timeline.length ? formatDate(timeline[0].deadline) : 'Rolling'}
              </p>
            </div>
          </section>

          <section className="card-surface p-5">
            <h2 className="font-bold">Application calendar</h2>
            {timeline.length ? (
              timeline.map((program) => (
                <div
                  key={program.id}
                  className="mt-3 flex flex-wrap items-baseline justify-between gap-2 border-t border-border pt-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{program.name}</p>
                    <p className="mt-0.5 text-xs text-muted">{program.provider}</p>
                  </div>
                  <p className="text-xs font-semibold text-brand">{formatDate(program.deadline)}</p>
                </div>
              ))
            ) : (
              <p className="mt-3 text-sm text-muted">
                Every confirmed award is rolling or on an unstated cycle, so there is no fixed date to
                plan around.
              </p>
            )}
          </section>

          <p className="text-center text-[13px] text-muted">
            Estimates only. Confirm each deadline on the official page before applying.
          </p>
        </>
      )}
    </div>
  );
}
