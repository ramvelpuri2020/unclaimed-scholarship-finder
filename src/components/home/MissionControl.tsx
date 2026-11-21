'use client';

import Link from 'next/link';
import { Briefcase, GraduationCap, Landmark, MapPin, PiggyBank, Receipt, Search, Target, Users } from 'lucide-react';
import { useStore } from '@/lib/store';
import { formatMoney } from '@/lib/format';
import { sites } from '@/lib/mockPrograms';

const icons = {
  community: Users,
  employer: Briefcase,
  university: GraduationCap,
  directory: Search,
  municipal: Landmark,
  provincial: MapPin,
  tax: Receipt,
  savings: PiggyBank,
} as const;

const dotColor: Record<string, string> = {
  queued: 'bg-muted/50',
  visiting: 'bg-brand',
  reading: 'bg-brand',
  done: 'bg-money',
  cached: 'bg-warn',
  failed: 'bg-danger',
};

export function MissionControl() {
  const programs = useStore((s) => s.programs);
  const saved = useStore((s) => s.savedIds.length);
  const running = useStore((s) => s.status === 'running');
  const siteState = useStore((s) => s.sites);
  const total = programs.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);

  return (
    <section className="grid gap-5 rounded-hero border border-border bg-white p-4 shadow-card md:grid-cols-[minmax(0,340px)_1fr] md:p-5">
      <div className="flex flex-col justify-between rounded-2xl bg-[#0B3B38] p-6 text-white">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-white/70">Mission control</p>
          <p className="mt-4 text-4xl font-extrabold text-gold">{formatMoney(total)}</p>
          <p className="mt-1 text-sm text-white/80">in programs you may qualify for</p>
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
          href={running ? '/hunt/demo' : '/matches'}
          className="mt-6 inline-flex h-11 items-center justify-center rounded-xl bg-white px-4 text-sm font-bold text-brand transition-colors hover:bg-brand-tint"
        >
          {running ? 'Watch live' : 'Review matches'}
        </Link>
      </div>

      <div>
        <div className="flex items-center gap-2 px-1">
          <Target size={16} className="text-brand" />
          <h2 className="text-sm font-bold">Agents</h2>
          {running ? <span className="text-xs text-muted">working…</span> : null}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {sites.map((site) => {
            const Icon = icons[site.id];
            const state = siteState[site.id];
            const fallbackCount = programs.filter((p) => p.sourceSiteId === site.id).length;
            const status = state?.status ?? 'idle';
            const label = state
              ? status === 'done'
                ? `Done · ${state.count}`
                : status === 'cached'
                  ? 'Cached'
                  : status === 'failed'
                    ? "Couldn't reach"
                    : status === 'reading'
                      ? 'Reading'
                      : status === 'visiting'
                        ? 'Visiting'
                        : 'Queued'
              : `${fallbackCount} found`;

            return (
              <div key={site.id} className="rounded-xl border border-border bg-white p-3">
                <div className="flex items-center justify-between">
                  <Icon size={16} className="text-brand" />
                  <span
                    className={`size-2 rounded-full ${dotColor[state?.status ?? 'queued'] ?? 'bg-border'}`}
                    aria-hidden="true"
                  />
                </div>
                <p className="mt-2 truncate text-xs font-semibold" title={site.name}>
                  {site.name}
                </p>
                <p className="mt-0.5 text-[11px] text-muted">{label}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
