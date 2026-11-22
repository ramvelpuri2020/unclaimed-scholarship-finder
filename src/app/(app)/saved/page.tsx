'use client';

import Link from 'next/link';
import { Heart } from 'lucide-react';
import { useStore } from '@/lib/store';
import { useHydrated } from '@/lib/useHydrated';
import { formatMoney } from '@/lib/format';
import { MatchCard } from '@/components/match/MatchCard';

export default function SavedPage() {
  const hydrated = useHydrated();
  const programs = useStore((state) => state.programs);
  const savedIds = useStore((state) => state.savedIds);
  const saved = programs.filter((program) => savedIds.includes(program.id));
  const savedTotal = saved.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);

  if (!hydrated) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-8 w-48 animate-pulse rounded-xl bg-bg" />
        <section className="card-surface p-8 text-center text-sm text-muted">Loading saved awards…</section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section>
        <h1 className="flex items-center gap-2 text-2xl font-extrabold">
          <Heart size={22} className="text-brand" /> Saved awards
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
          Everything you starred, kept on this device. Saving never sends your data anywhere.
        </p>
      </section>

      {saved.length === 0 ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">Nothing saved yet</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">
            {programs.length
              ? 'Tap the heart on any match to keep it here for later.'
              : 'Run a hunt first, then tap the heart on a match to keep it here.'}
          </p>
          <Link href={programs.length ? '/matches' : '/start'} className="btn-primary mt-5">
            {programs.length ? 'Review matches' : 'Start a hunt'}
          </Link>
        </section>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-muted">
              {saved.length} saved {saved.length === 1 ? 'award' : 'awards'}
            </p>
            {savedTotal > 0 ? (
              <p className="text-sm font-semibold text-money">
                {formatMoney(savedTotal)} in listed amounts
              </p>
            ) : null}
          </div>
          <div className="space-y-4">
            {saved.map((program) => (
              <MatchCard key={program.id} program={program} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
