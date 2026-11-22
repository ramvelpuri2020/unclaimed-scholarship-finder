'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Clock3 } from 'lucide-react';
import { useStore } from '@/lib/store';
import { useHydrated } from '@/lib/useHydrated';
import { deadlineText, daysUntil } from '@/lib/format';
import { MissionControl } from '@/components/home/MissionControl';
import { DeadlineTimeline } from '@/components/home/DeadlineTimeline';
import { MatchCard } from '@/components/match/MatchCard';
import { TimeAgo } from '@/components/shared/TimeAgo';

export default function Home() {
  const hydrated = useHydrated();
  const programs = useStore((s) => s.programs);
  const profile = useStore((s) => s.profile);
  const [greeting, setGreeting] = useState('day');

  useEffect(() => {
    const hour = new Date().getHours();
    setGreeting(hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening');
  }, []);

  const sorted = useMemo(
    () =>
      [...programs]
        .filter((program) => program.verification !== 'unconfirmed')
        .sort((a, b) => b.confidence - a.confidence)
        .slice(0, 3),
    [programs],
  );
  const soon = useMemo(
    () =>
      programs
        .filter(
          (program) =>
            program.verification !== 'unconfirmed' &&
            program.deadline &&
            daysUntil(program.deadline) !== null,
        )
        .sort((a, b) => (daysUntil(a.deadline) ?? 0) - (daysUntil(b.deadline) ?? 0))
        .slice(0, 4),
    [programs],
  );
  const recent = useMemo(
    () => [...programs].sort((a, b) => b.foundAt.localeCompare(a.foundAt)).slice(0, 4),
    [programs],
  );

  if (!hydrated) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-8 w-64 animate-pulse rounded-xl bg-bg" />
        <div className="h-48 animate-pulse rounded-hero bg-bg" />
        <section className="card-surface p-8 text-center text-sm text-muted">Loading your funding…</section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">
        Good {greeting}
        {profile?.fullName ? `, ${profile.fullName.split(' ')[0]}` : ''}
      </h1>

      <MissionControl />

      {programs.length === 0 ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">No matches yet</h2>
          <p className="mt-2 text-sm text-muted">Run a hunt and your matches will appear here.</p>
          <Link href="/start" className="btn-primary mt-5">
            Start a hunt
          </Link>
        </section>
      ) : (
        <>
          <DeadlineTimeline programs={programs} />

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-extrabold">Top matches</h2>
              <Link href="/matches" className="text-sm font-semibold text-brand">
                View all
              </Link>
            </div>
            {sorted.length ? (
              <div className="space-y-4">
                {sorted.map((program) => (
                  <MatchCard key={program.id} program={program} />
                ))}
              </div>
            ) : (
              <section className="card-surface p-6 text-center">
                <p className="text-sm text-muted">
                  This hunt found no award with a confirmed deadline yet. Open Matches to review the
                  programs that still need a deadline check.
                </p>
                <Link href="/matches" className="btn-primary mt-4">
                  Review matches
                </Link>
              </section>
            )}
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <section className="card-surface p-5">
              <h2 className="font-bold">Recently found</h2>
              {recent.length ? (
                recent.map((program) => (
                  <div key={program.id} className="mt-4 border-t border-border pt-3">
                    <p className="truncate text-sm font-semibold">{program.name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {program.amountLabel} · checked <TimeAgo value={program.checkedAt} />
                    </p>
                  </div>
                ))
              ) : (
                <p className="mt-4 text-sm text-muted">New finds will show up here.</p>
              )}
            </section>

            <section className="card-surface p-5">
              <h2 className="flex items-center gap-2 font-bold">
                <Clock3 size={17} className="text-brand" />
                Closing soon
              </h2>
              {soon.length ? (
                soon.map((program) => (
                  <div key={program.id} className="mt-4 border-t border-border pt-3">
                    <p className="truncate text-sm font-semibold">{program.name}</p>
                    <p className="mt-1 text-xs text-danger">
                      {program.amountLabel} · {deadlineText(program)}
                    </p>
                  </div>
                ))
              ) : (
                <p className="mt-4 text-sm text-muted">No upcoming deadlines yet.</p>
              )}
            </section>
          </div>

          <p className="text-center text-[13px] text-muted">
            Details can change. Always confirm on the official page.
          </p>
        </>
      )}
    </div>
  );
}
