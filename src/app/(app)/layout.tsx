'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Activity, Coins, Heart, House, Search, TrendingUp } from 'lucide-react';
import { useStore } from '@/lib/store';
import { useSession, startOver } from '@/lib/auth';

const tabs = [
  ['/home', 'Home', House],
  ['/matches', 'Matches', Search],
  ['/saved', 'Saved', Heart],
  ['/future-me', 'Future Me', TrendingUp],
  ['/activity', 'Activity', Activity],
] as const;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  const router = useRouter();
  const path = usePathname();
  const count = useStore((s) => s.programs.length);
  const saved = useStore((s) => s.savedIds.length);

  useEffect(() => {
    // Read the live store: during hydration the hook can still expose the
    // server snapshot (profile: null) before persisted state is applied.
    if (!useStore.getState().profile) router.replace('/start');
  }, [user, router]);

  function badge(href: string) {
    if (href === '/matches') return count;
    if (href === '/saved') return saved;
    return 0;
  }

  return (
    <div className="min-h-screen bg-bg text-ink">
      <header className="sticky top-0 z-40 border-b border-border bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-[1100px] items-center justify-between gap-4 px-4 md:px-6">
          <Link href="/home" className="flex shrink-0 items-center gap-2.5 text-lg font-extrabold">
            <span className="grid size-8 place-items-center rounded-xl bg-brand text-white">
              <Coins size={18} />
            </span>
            Unclaimed
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
            {tabs.map(([href, label, Icon]) => {
              const active = path === href;
              const n = badge(href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? 'page' : undefined}
                  className={`inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-sm font-semibold transition-colors ${
                    active ? 'bg-brand text-white' : 'text-muted hover:bg-bg hover:text-ink'
                  }`}
                >
                  <Icon size={16} />
                  {label}
                  {n > 0 ? (
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[11px] leading-none ${
                        active ? 'bg-white/20 text-white' : 'bg-brand-tint text-brand'
                      }`}
                    >
                      {n}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </nav>

          <div className="flex shrink-0 items-center gap-2 rounded-full border border-border bg-white py-1 pl-1 pr-2">
            <span className="grid size-8 place-items-center rounded-full bg-brand-tint text-xs font-bold text-brand">
              {user?.initials}
            </span>
            <span className="hidden max-w-[120px] truncate text-sm font-semibold sm:block">
              {user?.name}
            </span>
            <button
              type="button"
              onClick={startOver}
              className="rounded-full px-2 py-1 text-xs font-semibold text-muted transition-colors hover:text-danger"
            >
              Start over
            </button>
          </div>
        </div>

        <nav
          aria-label="Main mobile"
          className="flex items-center gap-1 overflow-x-auto px-4 pb-3 lg:hidden"
        >
          {tabs.map(([href, label, Icon]) => {
            const active = path === href;
            const n = badge(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={`inline-flex h-9 shrink-0 items-center gap-2 rounded-full px-3.5 text-sm font-semibold transition-colors ${
                  active ? 'bg-brand text-white' : 'text-muted hover:bg-bg hover:text-ink'
                }`}
              >
                <Icon size={16} />
                {label}
                {n > 0 ? (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[11px] leading-none ${
                      active ? 'bg-white/20 text-white' : 'bg-brand-tint text-brand'
                    }`}
                  >
                    {n}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1100px] flex-1 px-4 py-8 md:px-6">{children}</main>
    </div>
  );
}
