'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { HuntEvent, Profile, Program } from './types';

export type SiteStatus = 'queued' | 'visiting' | 'reading' | 'done' | 'failed';
export type SiteState = {
  id: string;
  name: string;
  status: SiteStatus;
  count: number;
  message: string;
  streamingUrl?: string;
};
export type HuntStatus = 'idle' | 'running' | 'complete' | 'error';
export type HuntRecord = {
  id: string;
  startedAt: string;
  finishedAt: string;
  total: number;
  count: number;
  verified?: number;
  unconfirmed?: number;
};
type FeedLine = { id: string; text: string; at: string };

type Store = {
  profile: Profile | null;
  programs: Program[];
  savedIds: string[];
  hunts: HuntRecord[];
  status: HuntStatus;
  huntId: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  huntError: string | null;
  sites: Record<string, SiteState>;
  siteOrder: string[];
  feed: FeedLine[];
  total: number;
  activeSiteId: string | null;
  manualSite: boolean;
  setProfile: (profile: Profile) => void;
  toggleSaved: (id: string) => void;
  prepare: () => void;
  cancel: () => void;
  start: (huntId: string) => void;
  adopt: (huntId: string) => void;
  event: (event: HuntEvent) => void;
  selectSite: (id: string) => void;
  setPrograms: (programs: Program[]) => void;
  reset: () => void;
};

const initial = {
  profile: null,
  programs: [],
  savedIds: [],
  hunts: [],
  status: 'idle' as const,
  huntId: null,
  startedAt: null,
  finishedAt: null,
  huntError: null,
  sites: {},
  siteOrder: [],
  feed: [],
  total: 0,
  activeSiteId: null,
  manualSite: false,
};

const emptyRun = {
  status: 'running' as const,
  huntId: null,
  startedAt: null,
  finishedAt: null,
  huntError: null,
  sites: {},
  siteOrder: [],
  feed: [],
  total: 0,
  activeSiteId: null,
  manualSite: false,
  programs: [],
};

function totalOf(programs: Program[]): number {
  return programs.reduce((sum, program) => sum + (program.amountMax ?? 0), 0);
}

export const useStore = create<Store>()(
  persist(
    (set) => ({
      ...initial,
      setProfile: (profile) => set({ profile }),
      toggleSaved: (id) =>
        set((state) => ({
          savedIds: state.savedIds.includes(id)
            ? state.savedIds.filter((savedId) => savedId !== id)
            : [...state.savedIds, id],
        })),
      prepare: () =>
        set({
          ...emptyRun,
          huntId: null,
          startedAt: null,
        }),
      cancel: () => set({ status: 'idle' }),
      start: (huntId) =>
        set((state) => ({
          ...emptyRun,
          huntId,
          startedAt: new Date().toISOString(),
          hunts: state.hunts,
        })),
      adopt: (huntId) =>
        set((state) => {
          if (state.huntId === huntId) return state;
          return {
            ...emptyRun,
            huntId,
            startedAt: new Date().toISOString(),
          };
        }),
      event: (event) =>
        set((state) => {
          const now = new Date().toISOString();
          const addFeed = (text: string) => [
            { id: crypto.randomUUID(), text, at: now },
            ...state.feed,
          ].slice(0, 10);

          const sites = { ...state.sites };
          let activeSiteId = state.activeSiteId;
          let feed = state.feed;
          let programs = state.programs;
          let status = state.status;
          let hunts = state.hunts;
          let siteOrder = state.siteOrder;
          let finishedAt = state.finishedAt;
          let huntError = state.huntError;

          if (event.type === 'site_started') {
            const existing = sites[event.siteId];
            const isNew = !existing;
            if (isNew) siteOrder = [...siteOrder, event.siteId];
            sites[event.siteId] = {
              id: event.siteId,
              name: event.siteName,
              status: existing && existing.status !== 'queued' ? existing.status : 'visiting',
              count: existing?.count ?? 0,
              message: existing && existing.status !== 'queued' ? existing.message : `Opening ${event.siteName}`,
              streamingUrl: event.streamingUrl ?? existing?.streamingUrl,
            };
            if (!state.manualSite && (event.streamingUrl || isNew || activeSiteId === null)) {
              activeSiteId = event.siteId;
            }
          } else if (event.type === 'site_progress') {
            const existing = sites[event.siteId];
            if (existing) {
              sites[event.siteId] = {
                ...existing,
                status: 'reading',
                message: event.message,
                count: event.count ?? existing.count,
              };
              feed = addFeed(`${event.message} · ${existing.name}`);
            } else {
              feed = addFeed(event.message);
            }
          } else if (event.type === 'program_found') {
            if (!programs.some((program) => program.id === event.program.id)) {
              programs = [...programs, event.program];
            }
            feed = addFeed(`Found: ${event.program.name} · ${event.program.amountLabel}`);
          } else if (event.type === 'site_done') {
            const existing = sites[event.siteId];
            sites[event.siteId] = {
              id: event.siteId,
              name: existing?.name ?? event.siteId,
              status: 'done',
              count: event.count,
              message: existing?.message ?? '',
              streamingUrl: existing?.streamingUrl,
            };
          } else if (event.type === 'site_failed') {
            const existing = sites[event.siteId];
            sites[event.siteId] = {
              id: event.siteId,
              name: existing?.name ?? event.siteId,
              status: 'failed',
              count: existing?.count ?? 0,
              message: 'Could not reach this page',
              streamingUrl: existing?.streamingUrl,
            };
          } else if (event.type === 'hunt_complete') {
            status = 'complete';
            finishedAt = now;
            hunts = [
              {
                id: state.huntId ?? 'hunt',
                startedAt: state.startedAt ?? now,
                finishedAt: now,
                total: event.totalAmount,
                count: event.programCount,
                verified: event.verifiedCount,
                unconfirmed: event.unconfirmedCount,
              },
              ...hunts,
            ];
            feed = addFeed(
              `Found ${event.programCount} awards: ${event.verifiedCount} with a confirmed deadline, ${event.unconfirmedCount} to check`,
            );
          } else {
            status = 'error';
            finishedAt = now;
            huntError = event.message;
            feed = addFeed(`Hunt stopped · ${event.message}`);
          }

          return {
            sites,
            siteOrder,
            activeSiteId,
            feed,
            programs,
            total: totalOf(programs),
            status,
            hunts,
            finishedAt,
            huntError,
          };
        }),
      selectSite: (id) => set({ activeSiteId: id, manualSite: true }),
      setPrograms: (programs) =>
        set({
          programs,
          total: totalOf(programs),
          status: 'complete',
        }),
      reset: () => set({ ...initial, hunts: [] }),
    }),
    {
      name: 'unclaimed-v2',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Never put a whole PDF into localStorage. The in-memory profile keeps
        // the data URL for the active hunt; a reload asks for the file again.
        profile: state.profile
          ? {
              ...state.profile,
              resume: state.profile.resume
                ? { name: state.profile.resume.name, size: state.profile.resume.size }
                : null,
            }
          : null,
        programs: state.programs,
        savedIds: state.savedIds,
        hunts: state.hunts,
        status: state.status,
        huntId: state.huntId,
        startedAt: state.startedAt,
        finishedAt: state.finishedAt,
        huntError: state.huntError,
        sites: state.sites,
        siteOrder: state.siteOrder,
        total: state.total,
        activeSiteId: state.activeSiteId,
      }) as Store,
    },
  ),
);
