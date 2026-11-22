'use client';

import { useEffect, useState } from 'react';
import { useStore } from './store';

/**
 * True once the persisted store has rehydrated in the browser.
 *
 * Pages that render persisted values wait for this flag so the server HTML and
 * the first client render agree. localStorage is never read during render; the
 * store rehydrates in an effect and reports completion through zustand.
 */
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let active = true;
    const finish = () => {
      if (active) setHydrated(true);
    };
    if (useStore.persist.hasHydrated()) {
      finish();
    }
    const unsubscribe = useStore.persist.onFinishHydration(finish);
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  return hydrated;
}
