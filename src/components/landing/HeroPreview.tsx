import { Briefcase, GraduationCap, Landmark, MapPin, PiggyBank, Receipt, Search, Users } from 'lucide-react';
import { formatMoney, totalFound } from '@/lib/format';
import { mockPrograms, sites } from '@/lib/mockPrograms';

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

export function HeroPreview() {
  const total = totalFound(mockPrograms);

  return (
    <div className="relative hidden lg:block" aria-hidden="true">
      <div className="absolute -left-10 -top-8 size-40 rounded-full bg-brand-tint blur-2xl" />
      <div className="absolute -bottom-10 -right-8 size-48 rounded-full bg-brand-tint blur-2xl" />

      <div className="animate-float relative z-10 rounded-hero border border-border bg-white p-5 shadow-pop">
        <div className="rounded-2xl bg-[#0B3B38] p-5 text-white">
          <p className="text-xs font-bold uppercase tracking-wider text-white/70">Mission control</p>
          <p className="mt-3 text-3xl font-extrabold leading-none text-gold">{formatMoney(total)}</p>
          <p className="mt-2 text-sm text-white/80">in programs you may qualify for</p>
        </div>

        <div className="mt-4 grid grid-cols-4 gap-2">
          {sites.map((site) => {
            const Icon = icons[site.id];
            const found = mockPrograms.filter((program) => program.sourceSiteId === site.id).length;
            return (
              <div key={site.id} className="rounded-xl border border-border bg-white p-2.5">
                <Icon size={15} aria-hidden="true" className="text-brand" />
                <p className="mt-1.5 truncate text-[10px] font-semibold text-ink" title={site.name}>
                  {site.name}
                </p>
                <p className="mt-0.5 text-[10px] text-muted">{found} found</p>
              </div>
            );
          })}
        </div>
      </div>

      <p className="relative z-10 mt-3 text-center text-xs text-muted">Sample results from demo mode</p>
    </div>
  );
}
