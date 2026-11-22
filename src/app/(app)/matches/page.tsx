'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowRight, Sparkles } from 'lucide-react';
import { useStore } from '@/lib/store';
import { useHydrated } from '@/lib/useHydrated';
import { fetchHuntMeta, fetchHuntResults } from '@/lib/huntClient';
import { formatMoney } from '@/lib/format';
import { MatchCard } from '@/components/match/MatchCard';

const FIT_ORDER = { strong: 0, good: 1, weak: 2 } as const;

type Rankable = {
  fit: keyof typeof FIT_ORDER;
  confidence: number;
  amountMax: number | null;
  name: string;
  verification: string;
};

function sortMatches<T extends Rankable>(items: T[]): T[] {
  const group = (program: T) => (program.verification === 'unconfirmed' ? 1 : 0);
  return [...items].sort(
    (a, b) =>
      group(a) - group(b) ||
      FIT_ORDER[a.fit] - FIT_ORDER[b.fit] ||
      b.confidence - a.confidence ||
      (b.amountMax ?? 0) - (a.amountMax ?? 0) ||
      a.name.localeCompare(b.name),
  );
}

function formatStarted(value: string): string {
  return new Intl.DateTimeFormat('en-CA', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  );
}

function LoadingMatches() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="h-6 w-40 animate-pulse rounded-full bg-brand-tint" />
      <div className="h-8 w-72 animate-pulse rounded-xl bg-bg" />
      <section className="card-surface p-8 text-center text-sm text-muted">Loading your matches…</section>
    </div>
  );
}

function MatchesContent() {
  const hydrated = useHydrated();
  const searchParams = useSearchParams();
  const savedHuntId = searchParams.get('hunt');
  const programs = useStore((state) => state.programs);
  const storeHuntId = useStore((state) => state.huntId);
  const huntStatus = useStore((state) => state.status);
  const storeStartedAt = useStore((state) => state.startedAt);
  const setPrograms = useStore((state) => state.setPrograms);
  const huntId = savedHuntId || storeHuntId;
  const isSavedHunt = Boolean(savedHuntId && savedHuntId !== storeHuntId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedLabel, setStartedLabel] = useState('');
  const fetchedFor = useRef<string | null>(null);

  useEffect(() => {
    if (storeStartedAt) {
      setStartedLabel(formatStarted(storeStartedAt));
      return;
    }
    setStartedLabel('');
  }, [storeStartedAt]);

  useEffect(() => {
    if (!hydrated || !huntId) return;
    if (!isSavedHunt && (programs.length > 0 || huntStatus === 'running')) return;
    if (fetchedFor.current === huntId) return;
    fetchedFor.current = huntId;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchHuntResults(huntId)
      .then((items) => {
        if (!cancelled) setPrograms(items);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not load matches.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    fetchHuntMeta(huntId)
      .then((meta) => {
        if (!cancelled && meta.startedAt) setStartedLabel(formatStarted(meta.startedAt));
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [hydrated, huntId, isSavedHunt, huntStatus, programs.length, setPrograms]);

  const matches = useMemo(() => sortMatches(programs), [programs]);
  const verified = useMemo(
    () => matches.filter((program) => program.tier !== 'B' && program.verification !== 'unconfirmed'),
    [matches],
  );
  const unconfirmed = useMemo(
    () => matches.filter((program) => program.tier === 'B' || program.verification === 'unconfirmed'),
    [matches],
  );
  const listedTotal = matches.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);
  const unlisted = matches.filter((program) => program.amountMax === null).length;

  if (!hydrated) return <LoadingMatches />;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-brand-tint px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-brand">
            <Sparkles size={14} /> Ranked for you
          </p>
          <h1 className="mt-3 text-2xl font-extrabold">Your verified matches</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
            Real scholarships, bursaries and awards from external organizations and your university.
            Every verified result has a source quote and a deadline or cycle confirmed on the page.
          </p>
          {startedLabel ? (
            <p className="mt-2 text-xs font-semibold text-muted">
              Results from the hunt started at {startedLabel}
            </p>
          ) : null}
        </div>
        <div className="text-right">
          <p className="text-3xl font-extrabold text-money">{matches.length}</p>
          <p className="text-xs text-muted">awards for you</p>
          {listedTotal > 0 ? (
            <p className="text-xs font-semibold text-muted">
              {formatMoney(listedTotal)} in listed amounts
            </p>
          ) : null}
          {unlisted > 0 ? (
            <p className="text-xs text-muted">{unlisted} awards list no amount</p>
          ) : null}
        </div>
      </section>

      {loading ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">Loading your matches</h2>
          <p className="mt-2 text-sm text-muted">Fetching the latest verified results.</p>
        </section>
      ) : error ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">Could not load matches</h2>
          <p className="mt-2 text-sm text-muted">{error}</p>
          <Link href="/start" className="btn-primary mt-5">
            Start a hunt <ArrowRight size={17} />
          </Link>
        </section>
      ) : matches.length === 0 ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">No verified matches yet</h2>
          <p className="mt-2 text-sm text-muted">
            Run a hunt and we&apos;ll show every scholarship that survives verification.
          </p>
          <Link href="/start" className="btn-primary mt-5">
            Start a hunt <ArrowRight size={17} />
          </Link>
        </section>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-muted">
              {verified.length} with a confirmed deadline
            </p>
            <Link href="/start" className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand">
              Run another hunt <ArrowRight size={15} />
            </Link>
          </div>

          {verified.length ? (
            <div className="space-y-4">
              {verified.map((program) => (
                <MatchCard key={program.id} program={program} />
              ))}
            </div>
          ) : (
            <section className="card-surface p-8 text-center">
              <h2 className="text-lg font-bold">No award with a confirmed deadline yet</h2>
              <p className="mt-2 text-sm text-muted">
                This hunt found programs that need a deadline check. They are listed below.
              </p>
            </section>
          )}

          {unconfirmed.length ? (
            <section className="space-y-4 border-t border-border pt-6">
              <div>
                <h2 className="text-lg font-extrabold">
                  Deadline not confirmed on the page: check before applying
                </h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
                  These passed the eligibility checks, but the page did not state a future deadline.
                  Confirm the date on the official page before you spend time on the application.
                </p>
              </div>
              {unconfirmed.map((program) => (
                <MatchCard key={program.id} program={program} />
              ))}
            </section>
          ) : null}

          <p className="text-center text-[13px] text-muted">
            Details can change. Always confirm eligibility and deadlines on the official page.
          </p>
        </>
      )}
    </div>
  );
}

export default function MatchesPage() {
  return (
    <Suspense fallback={<LoadingMatches />}>
      <MatchesContent />
    </Suspense>
  );
}
