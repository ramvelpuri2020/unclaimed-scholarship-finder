'use client';

import Link from 'next/link';
import { Activity } from 'lucide-react';
import { useStore } from '@/lib/store';
import { useHydrated } from '@/lib/useHydrated';
import { TimeAgo } from '@/components/shared/TimeAgo';

export default function ActivityPage() {
  const hydrated = useHydrated();
  const feed = useStore((state) => state.feed);
  const hunts = useStore((state) => state.hunts);
  const status = useStore((state) => state.status);
  const huntId = useStore((state) => state.huntId);

  if (!hydrated) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-8 w-52 animate-pulse rounded-xl bg-bg" />
        <section className="card-surface p-8 text-center text-sm text-muted">Loading activity…</section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-extrabold">
            <Activity size={22} className="text-brand" /> Activity
          </h1>
          <p className="mt-1 text-sm text-muted">What your agents did on this device.</p>
        </div>
        {status === 'running' && huntId ? (
          <Link href={`/hunt/${huntId}`} className="btn-primary">
            Watch live
          </Link>
        ) : null}
      </section>

      {feed.length === 0 && hunts.length === 0 ? (
        <section className="card-surface p-8 text-center">
          <h2 className="text-lg font-bold">No activity yet</h2>
          <p className="mt-2 text-sm text-muted">
            Start a hunt and every search, page read and verification shows up here.
          </p>
          <Link href="/start" className="btn-primary mt-5">
            Start a hunt
          </Link>
        </section>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <section className="card-surface p-5">
            <h2 className="font-bold">Recent hunt events</h2>
            {feed.length ? (
              feed.map((item) => (
                <p key={item.id} className="mt-3 border-t border-border pt-3 text-sm">
                  {item.text}
                  <span className="mt-1 block text-xs text-muted">
                    <TimeAgo value={item.at} />
                  </span>
                </p>
              ))
            ) : (
              <p className="mt-3 text-sm text-muted">No events from the current hunt yet.</p>
            )}
          </section>

          <section className="card-surface p-5">
            <h2 className="font-bold">Past hunts</h2>
            {hunts.length ? (
              hunts.map((record) => (
                <div key={`${record.id}-${record.finishedAt}`} className="mt-3 border-t border-border pt-3">
                  <p className="text-sm font-semibold">
                    {record.count} {record.count === 1 ? 'award' : 'awards'} ·{' '}
                    {record.verified ?? 0} with a confirmed deadline
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    Finished <TimeAgo value={record.finishedAt} />
                  </p>
                  <Link href={`/hunt/${record.id}`} className="mt-2 inline-block text-xs font-semibold text-brand">
                    Open hunt
                  </Link>
                </div>
              ))
            ) : (
              <p className="mt-3 text-sm text-muted">Finished hunts will be listed here.</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
