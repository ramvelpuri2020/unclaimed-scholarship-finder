'use client';

import { useStore } from './store';
import type { HuntEvent, HuntMeta, Profile, Program, ResumePreview } from './types';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

let source: EventSource | null = null;
let sourceHuntId: string | null = null;

function isTerminal(event: HuntEvent): boolean {
  return event.type === 'hunt_complete' || event.type === 'hunt_error';
}

function closeSource() {
  source?.close();
  source = null;
  sourceHuntId = null;
}

export function connectToHunt(huntId: string): void {
  if (typeof window === 'undefined') return;
  if (source && sourceHuntId === huntId) return;
  closeSource();

  const stream = new EventSource(`${API_BASE}/api/hunt/${encodeURIComponent(huntId)}/events`);
  source = stream;
  sourceHuntId = huntId;

  stream.onmessage = (message) => {
    if (source !== stream) return;
    let event: HuntEvent;
    try {
      event = JSON.parse(message.data) as HuntEvent;
    } catch {
      return;
    }
    useStore.getState().event(event);
    if (isTerminal(event)) closeSource();
  };
}

async function startLiveHunt(profile: Profile): Promise<string> {
  // Clear the previous run before the request so no old result can be mixed
  // into the new hunt, even if the request fails.
  useStore.getState().prepare();

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/hunt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
  } catch (error) {
    useStore.getState().cancel();
    throw error;
  }

  if (!response.ok) {
    useStore.getState().cancel();
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === 'string' ? body.detail : null;
    throw new Error(detail ?? `The hunt could not start (${response.status}).`);
  }

  const body = (await response.json()) as { huntId?: string };
  if (!body.huntId) throw new Error('The server did not return a hunt id.');

  useStore.getState().start(body.huntId);
  connectToHunt(body.huntId);
  return body.huntId;
}

export async function startHunt(profile: Profile): Promise<string> {
  return startLiveHunt(profile);
}

export async function previewResume(dataUrl: string, name: string): Promise<ResumePreview> {
  const response = await fetch(`${API_BASE}/api/resume/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, dataUrl }),
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === 'string' ? body.detail : null;
    throw new Error(detail ?? `We couldn't read that resume (${response.status}).`);
  }

  return (await response.json()) as ResumePreview;
}

export async function fetchHuntResults(huntId: string): Promise<Program[]> {
  const response = await fetch(`${API_BASE}/api/hunt/${encodeURIComponent(huntId)}/results`);
  if (!response.ok) throw new Error(`Could not load matches (${response.status}).`);
  return (await response.json()) as Program[];
}

export async function fetchHuntMeta(huntId: string): Promise<HuntMeta> {
  const response = await fetch(`${API_BASE}/api/hunt/${encodeURIComponent(huntId)}/meta`);
  if (!response.ok) throw new Error(`Could not load hunt details (${response.status}).`);
  return (await response.json()) as HuntMeta;
}
