'use client';

import Link from 'next/link';
import { useMemo, useRef, useState } from 'react';
import { Clock3 } from 'lucide-react';
import { useStore } from '@/lib/store';
import { formatMoney, deadlineText, daysUntil, relativeTime } from '@/lib/format';
import type { Program } from '@/lib/types';
import { MissionControl } from '@/components/home/MissionControl';
import { DeadlineTimeline } from '@/components/home/DeadlineTimeline';
import { MatchCard } from '@/components/match/MatchCard';
import { ApplyDrawer } from '@/components/match/ApplyDrawer';

export default function Home() {
  const programs = useStore((s) => s.programs);
  const profile = useStore((s) => s.profile);
  const [applyProgram, setApplyProgram] = useState<Program | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  const sorted = useMemo(
    () => [...programs].sort((a, b) => b.confidence - a.confidence).slice(0, 3),
    [programs],
  );
  const soon = useMemo(
    () =>
      programs
        .filter((program) => program.deadline && daysUntil(program.deadline) !== null)
        .sort((a, b) => (daysUntil(a.deadline) ?? 0) - (daysUntil(b.deadline) ?? 0))
        .slice(0, 4),
    [programs],
  );
  const recent = useMemo(
    () => [...programs].sort((a, b) => b.foundAt.localeCompare(a.foundAt)).slice(0, 4),
    [programs],
  );

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening';

  function openApply(program: Program, trigger: HTMLElement) {
    triggerRef.current = trigger;
    setApplyProgram(program);
  }

  function closeApply() {
    setApplyProgram(null);
    requestAnimationFrame(() => triggerRef.current?.focus());
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
            <div className="space-y-4">
              {sorted.map((program) => (
                <MatchCard key={program.id} program={program} onApply={openApply} />
              ))}
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <section className="card-surface p-5">
              <h2 className="font-bold">Recently found</h2>
              {recent.length ? (
                recent.map((program) => (
                  <div key={program.id} className="mt-4 border-t border-border pt-3">
                    <p className="truncate text-sm font-semibold">{program.name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {program.amountLabel} · checked {relativeTime(program.checkedAt)}
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

      <ApplyDrawer program={applyProgram} onClose={closeApply} />
    </div>
  );
}
