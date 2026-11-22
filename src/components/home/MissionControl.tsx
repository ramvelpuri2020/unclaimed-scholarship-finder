'use client';

import Link from 'next/link';
import { Globe2, Target } from 'lucide-react';
import { useStore } from '@/lib/store';
import { formatMoney } from '@/lib/format';

const dotColor: Record<string, string> = {
  queued: 'bg-muted/50',
  visiting: 'bg-brand',
  reading: 'bg-brand',
  done: 'bg-money',
  failed: 'bg-danger',
};

export function MissionControl() {
  const programs = useStore((s) => s.programs);
  const saved = useStore((s) => s.savedIds.length);
  const running = useStore((s) => s.status === 'running');
  const huntId = useStore((s) => s.huntId);
  const siteState = useStore((s) => s.sites);
  const siteOrder = useStore((s) => s.siteOrder);
  const total = programs.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);
  const unlisted = programs.filter((program) => program.amountMax === null).length;

  return (
    <section className="grid gap-5 rounded-hero border border-border bg-white p-4 shadow-card md:grid-cols-[minmax(0,340px)_1fr] md:p-5">
      <div className="flex flex-col justify-between rounded-2xl bg-[#0B3B38] p-6 text-white">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-white/70">Mission control</p>
          <p className="mt-4 text-4xl font-extrabold text-gold">{programs.length}</p>
          <p className="mt-1 text-sm text-white/80">awards found for you</p>
          {total > 0 ? (
            <p className="mt-1 text-sm text-white/80">{formatMoney(total)} in listed amounts</p>
          ) : null}
          {unlisted > 0 ? (
            <p className="mt-1 text-sm text-white/80">{unlisted} awards list no amount</p>
          ) : null}
          <div className="mt-5 flex flex-wrap gap-2">
            <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold">
              {programs.length} matches
            </span>
            <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold">
              {saved} saved
            </span>
          </div>
        </div>
        <Link
          href={running && huntId ? `/hunt/${huntId}` : '/matches'}
          className="mt-6 inline-flex h-11 items-center justify-center rounded-xl bg-white px-4 text-sm font-bold text-brand transition-colors hover:bg-brand-tint"
        >
          {running ? 'Watch live' : 'Review matches'}
        </Link>
      </div>

      <div>
        <div className="flex items-center gap-2 px-1">
          <Target size={16} className="text-brand" />
          <h2 className="text-sm font-bold">Pipeline</h2>
          {running ? <span className="text-xs text-muted">working…</span> : null}
        </div>
        {siteOrder.length ? (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {siteOrder.map((id) => {
              const site = siteState[id];
              const status = site?.status ?? 'queued';
              const label =
                status === 'done'
                  ? `Done · ${site?.count ?? 0}`
                  : status === 'failed'
                    ? "Couldn't reach"
                    : status === 'reading'
                      ? 'Reading'
                      : status === 'visiting'
                        ? 'Visiting'
                        : 'Queued';

              return (
                <div key={id} className="rounded-xl border border-border bg-white p-3">
                  <div className="flex items-center justify-between">
                    <Globe2 size={16} className="text-brand" aria-hidden="true" />
                    <span
                      className={`size-2 rounded-full ${dotColor[status] ?? 'bg-border'}`}
                      aria-hidden="true"
                    />
                  </div>
                  <p className="mt-2 truncate text-xs font-semibold" title={site?.name ?? id}>
                    {site?.name ?? id}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted">{label}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="mt-3 px-1 text-sm text-muted">Search, reading, verification and agent stages appear here.</p>
        )}
      </div>
    </section>
  );
}
