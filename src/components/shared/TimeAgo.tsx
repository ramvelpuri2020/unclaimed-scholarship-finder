'use client';

import { useEffect, useState } from 'react';
import { relativeTime } from '@/lib/format';

/** Render a relative timestamp without touching Date.now() during render. */
export function TimeAgo({ value }: { value: string }) {
  const [label, setLabel] = useState('');

  useEffect(() => {
    const update = () => setLabel(relativeTime(value));
    update();
    const timer = window.setInterval(update, 60_000);
    return () => window.clearInterval(timer);
  }, [value]);

  return <time dateTime={value}>{label || 'just now'}</time>;
}
