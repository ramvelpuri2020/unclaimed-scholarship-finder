'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, Globe2, Search } from 'lucide-react';
import { useStore, type HuntStatus, type SiteState } from '@/lib/store';
import { connectToHunt } from '@/lib/huntClient';
import { formatMoney, relativeTime } from '@/lib/format';
import { HuntLaunch } from '@/components/hunt/HuntLaunch';

function formatElapsed(seconds: number): string {
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function useElapsedSeconds(startedAt: string | null, finishedAt: string | null, status: HuntStatus): number {
  const [now, setNow] = useState(0);

  useEffect(() => {
    setNow(Date.now());
    if (status !== 'running') return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status, startedAt]);

  if (!startedAt) return 0;
  const start = new Date(startedAt).getTime();
  const end =
    status === 'running'
      ? now
      : finishedAt
        ? new Date(finishedAt).getTime()
        : now;
  return Math.max(0, Math.floor((end - start) / 1000));
}

function siteStatusLabel(site: SiteState | undefined): string {
  if (!site) return 'Queued';
  if (site.status === 'done') {
    if (site.id === 'search') return `${site.count} queries`;
    if (site.id === 'read') return `${site.count} pages`;
    if (site.id === 'verify') return `${site.count} awards`;
    return `${site.count} programs`;
  }
  if (site.status === 'failed') return "Couldn't reach";
  if (site.status === 'reading') {
    if (!site.count) return 'Reading';
    if (site.id === 'search') return `${site.count} queries`;
    if (site.id === 'read') return `${site.count} pages`;
    if (site.id === 'verify') return `${site.count} awards`;
    return `${site.count} programs`;
  }
  if (site.status === 'visiting') return 'Visiting';
  return 'Queued';
}

function AgentFallback({ site }: { site: SiteState | undefined }) {
  return (
    <div className="flex min-h-[360px] flex-col items-center justify-center px-6 text-center">
      <div className="grid size-20 place-items-center rounded-full bg-brand-tint text-brand">
        <Search size={32} aria-hidden="true" />
      </div>
      <h2 className="mt-5 text-xl font-bold">{site?.name || 'Preparing your hunt'}</h2>
      <p className="mt-2 text-sm text-muted">
        {site?.message || 'Agents are getting ready to visit scholarship websites.'}
      </p>
      <div className="mt-8 w-full max-w-sm space-y-3" aria-hidden="true">
        {[80, 65, 90].map((width) => (
          <div key={width} className="h-3 animate-pulse rounded-full bg-bg" style={{ width: `${width}%` }} />
        ))}
      </div>
    </div>
  );
}

function AgentBrowser({ site }: { site: SiteState | undefined }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const loadedRef = useRef(false);

  useEffect(() => {
    loadedRef.current = false;
    setLoaded(false);
    setFailed(false);
    if (!site?.streamingUrl) return;

    const timer = window.setTimeout(() => {
      if (!loadedRef.current) setFailed(true);
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [site?.streamingUrl]);

  if (!site?.streamingUrl || failed) return <AgentFallback site={site} />;

  return (
    <div className="relative min-h-[360px] bg-bg">
      <iframe
        key={site.streamingUrl}
        src={site.streamingUrl}
        title={`Live browser for ${site.name}`}
        className="h-[360px] w-full border-0"
        onLoad={() => {
          loadedRef.current = true;
          setLoaded(true);
        }}
        onError={() => setFailed(true)}
        allow="clipboard-read; clipboard-write"
        referrerPolicy="no-referrer"
      />
      {!loaded ? (
        <div className="pointer-events-none absolute inset-0 grid place-items-center bg-bg/70">
          <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-muted shadow-card">
            <Globe2 size={16} className="text-brand" aria-hidden="true" />
            Loading the live page…
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function HuntView() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const huntId = params.id;
  const status = useStore((state) => state.status);
  const siteMap = useStore((state) => state.sites);
  const siteOrder = useStore((state) => state.siteOrder);
  const activeId = useStore((state) => state.activeSiteId);
  const selectSite = useStore((state) => state.selectSite);
  const feed = useStore((state) => state.feed);
  const programs = useStore((state) => state.programs);
  const profile = useStore((state) => state.profile);
  const startedAt = useStore((state) => state.startedAt);
  const finishedAt = useStore((state) => state.finishedAt);
  const huntError = useStore((state) => state.huntError);
  const [launchTimedOut, setLaunchTimedOut] = useState(false);

  useEffect(() => {
    if (!huntId) return;
    useStore.getState().adopt(huntId);
    if (useStore.getState().status === 'running') connectToHunt(huntId);
  }, [huntId]);

  useEffect(() => {
    setLaunchTimedOut(false);
    const timer = window.setTimeout(() => setLaunchTimedOut(true), 20000);
    return () => window.clearTimeout(timer);
  }, [huntId]);

  const seconds = useElapsedSeconds(startedAt, finishedAt, status);
  const active = activeId ? siteMap[activeId] : undefined;
  const totalSites = siteOrder.length;
  const checked = siteOrder.filter((id) => {
    const siteStatus = siteMap[id]?.status;
    return siteStatus === 'done' || siteStatus === 'failed';
  }).length;
  const firstName = profile?.fullName?.trim().split(/\s+/)[0] || 'there';
  const showLaunch = status !== 'complete' && status !== 'error' && totalSites === 0 && !launchTimedOut;
  const verifiedCount = programs.filter((program) => program.verification !== 'unconfirmed').length;
  const unconfirmedCount = programs.length - verifiedCount;
  const listedTotal = programs.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);
  const unlistedCount = programs.filter((program) => program.amountMax === null).length;

  return (
    <AnimatePresence mode="wait" initial={false}>
      {showLaunch ? (
        <HuntLaunch key={`launch-${huntId}`} firstName={firstName} />
      ) : (
        <motion.div
          key="live-hunt"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
        >
          <section className="grid gap-5 rounded-hero bg-[#0B3B38] p-6 text-white md:grid-cols-3 md:items-center">
            <div>
              <h1 className="text-lg font-bold">Hunting for {firstName}</h1>
              <p className="mt-1 text-sm text-white/75">{formatElapsed(seconds)} elapsed</p>
            </div>
            <div className="text-center">
              <strong className="text-5xl font-extrabold text-gold">{programs.length}</strong>
              <p className="text-sm text-white/75">awards found so far</p>
              {listedTotal > 0 ? (
                <p className="text-sm text-white/75">{formatMoney(listedTotal)} in listed amounts</p>
              ) : null}
              {unlistedCount > 0 ? (
                <p className="text-sm text-white/75">{unlistedCount} awards list no amount</p>
              ) : null}
            </div>
            <div>
              <p className="text-sm font-semibold">
                Stages complete: {checked} / {totalSites}
              </p>
              <div className="mt-2 h-2 rounded-full bg-white/25">
                <div
                  className="h-full rounded-full bg-white transition-all"
                  style={{ width: `${totalSites ? (checked / totalSites) * 100 : 0}%` }}
                />
              </div>
            </div>
          </section>

          {status === 'error' ? (
            <section
              role="alert"
              className="mt-5 rounded-card border border-danger/30 bg-danger-tint p-5 text-ink"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 shrink-0 text-danger" size={20} aria-hidden="true" />
                <div className="min-w-0">
                  <h2 className="font-bold text-danger">Hunt stopped</h2>
                  <p className="mt-1 text-sm leading-6">{huntError || 'The hunt could not finish.'}</p>
                  <button
                    type="button"
                    onClick={() => router.push('/start')}
                    className="mt-4 inline-flex h-10 items-center justify-center rounded-xl bg-danger px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                  >
                    Try again
                  </button>
                </div>
              </div>
            </section>
          ) : null}

          {status === 'complete' && programs.length === 0 ? (
            <section className="card-surface mt-5 p-8 text-center">
              <h2 className="text-xl font-bold">No matches found this time</h2>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">
                We checked {totalSites} sources and nothing matched your answers. Try changing your program or school.
              </p>
              <button
                type="button"
                onClick={() => router.push('/start')}
                className="btn-primary mt-5"
              >
                Start over
              </button>
            </section>
          ) : null}

          <div className="mt-6 grid gap-5 lg:grid-cols-[3fr_2fr]">
            <section className="card-surface overflow-hidden">
              <div className="flex items-center gap-3 border-b border-border p-4">
                <div className="flex gap-1" aria-hidden="true">
                  <i className="size-2.5 rounded-full bg-[#D7DDE8]" />
                  <i className="size-2.5 rounded-full bg-[#D7DDE8]" />
                  <i className="size-2.5 rounded-full bg-[#D7DDE8]" />
                </div>
                <div className="flex min-w-0 flex-1 items-center gap-2 rounded-xl bg-bg px-3 py-2 text-sm text-muted">
                  <span aria-hidden="true">🔒</span>
                  <span className="truncate">{active?.name || 'Waiting for agent'}</span>
                </div>
                <span className="text-xs text-muted">Agent is working</span>
              </div>

              <AgentBrowser site={active} />

              <div className="flex flex-wrap gap-2 border-t border-border p-4">
                {siteOrder.map((id) => {
                  const site = siteMap[id];
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => selectSite(id)}
                      className={`rounded-full border px-3 py-2 text-xs font-semibold transition-colors ${
                        activeId === id
                          ? 'border-brand bg-brand text-white'
                          : 'border-border bg-white text-muted hover:border-brand'
                      }`}
                    >
                      {site?.name || id}
                    </button>
                  );
                })}
              </div>
            </section>

            <aside className="space-y-5">
              <section className="card-surface p-5">
                <h2 className="font-bold">Agents</h2>
                {siteOrder.length ? (
                  siteOrder.map((id) => {
                    const site = siteMap[id];
                    return (
                      <div key={id} className="flex items-center gap-2 border-t border-border py-3 first:mt-3">
                        <Globe2 size={17} className="text-muted" aria-hidden="true" />
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                          {site?.name || id}
                        </span>
                        <span className="text-xs text-muted">{siteStatusLabel(site)}</span>
                      </div>
                    );
                  })
                ) : (
                  <p className="mt-3 text-sm text-muted">Agents will appear here as they start.</p>
                )}
              </section>

              <section className="card-surface p-5">
                <h2 className="font-bold">Activity</h2>
                {feed.length ? (
                  feed.map((item) => (
                    <p key={item.id} className="mt-3 border-t border-border pt-3 text-sm">
                      <span>{item.text}</span>
                      <span className="mt-1 block text-xs text-muted">{relativeTime(item.at)}</span>
                    </p>
                  ))
                ) : (
                  <p className="mt-3 text-sm text-muted">Your agents’ activity will appear here.</p>
                )}
                {status === 'complete' && programs.length > 0 ? (
                  <div className="mt-4 rounded-xl bg-money-tint p-3 text-sm font-semibold text-money">
                    Found {programs.length} awards: {verifiedCount} with a confirmed deadline,{' '}
                    {unconfirmedCount} to check.{' '}
                    <Link href="/matches" className="underline">
                      See my matches
                    </Link>
                  </div>
                ) : null}
              </section>
            </aside>
          </div>

          <p className="sr-only">Hunt ID {huntId}</p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
