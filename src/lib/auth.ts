'use client';
import { useStore } from './store';
export function useSession() { const profile = useStore(s=>s.profile); const name=profile?.fullName||''; return { user: profile ? { name, firstName:name.split(' ')[0]||name, initials:name.split(' ').map(x=>x[0]).join('').slice(0,2).toUpperCase() } : null }; }
export function startOver() { useStore.getState().reset(); window.location.href='/'; }
