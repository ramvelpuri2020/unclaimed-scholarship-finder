'use client';

import { Globe2 } from 'lucide-react';
import { formatMoney } from '@/lib/format';
import { useStore } from '@/lib/store';

export function HeroPreview() {
  const programs = useStore((state) => state.programs);
  const sites = useStore((state) => state.sites);
  const siteOrder = useStore((state) => state.siteOrder);
  const total = programs.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);
  const placeholders = Math.max(0, 8 - siteOrder.length);

  return (
    <div className="relative hidden lg:block" aria-hidden="true">
      <div className="absolute -left-10 -top-8 size-40 rounded-full bg-brand-tint blur-2xl" />
      <div className="absolute -bottom-10 -right-8 size-48 rounded-full bg-brand-tint blur-2xl" />

      <div className="animate-float relative z-10 rounded-hero border border-border bg-white p-5 shadow-pop">
        <div className="rounded-2xl bg-[#0B3B38] p-5 text-white">
          <p className="text-xs font-bold uppercase tracking-wider text-white/70">Mission control</p>
          <p className="mt-3 text-3xl font-extrabold leading-none text-gold">{programs.length}</p>
          <p className="mt-2 text-sm text-white/80">awards found for you</p>
          {total > 0 ? (
            <p className="mt-1 text-sm text-white/80">{formatMoney(total)} in listed amounts</p>
          ) : null}
        </div>

        <div className="mt-4 grid grid-cols-4 gap-2">
          {siteOrder.map((id) => {
            const site = sites[id];
            const found = programs.filter((program) => program.sourceSiteId === id).length;
            return (
              <div key={id} className="rounded-xl border border-border bg-white p-2.5">
                <Globe2 size={15} className="text-brand" />
                <p className="mt-1.5 truncate text-[10px] font-semibold text-ink" title={site?.name ?? id}>
                  {site?.name ?? id}
                </p>
                <p className="mt-0.5 text-[10px] text-muted">{found} found</p>
              </div>
            );
          })}
          {Array.from({ length: placeholders }, (_, index) => (
            <div key={`placeholder-${index}`} className="rounded-xl border border-border bg-white p-2.5">
              <Globe2 size={15} className="text-border" />
              <div className="mt-2 h-2 rounded-full bg-bg" />
              <div className="mt-1.5 h-2 w-2/3 rounded-full bg-bg" />
            </div>
          ))}
        </div>
      </div>

      <p className="relative z-10 mt-3 text-center text-xs text-muted">
        {programs.length ? 'Live results from your latest hunt' : 'Your live results will appear here'}
      </p>
    </div>
  );
}
