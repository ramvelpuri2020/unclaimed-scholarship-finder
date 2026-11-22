'use client';

import { useEffect } from 'react';
import { RotateCcw } from 'lucide-react';

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section role="alert" className="card-surface p-8 text-center">
      <h1 className="text-xl font-extrabold">This page hit an error</h1>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">
        {error.message || 'The page could not be loaded.'}
      </p>
      {error.digest ? <p className="mt-2 text-xs text-muted">Reference: {error.digest}</p> : null}
      <button
        type="button"
        onClick={() => {
          reset();
          window.location.reload();
        }}
        className="btn-primary mt-5"
      >
        <RotateCcw size={16} /> Reload
      </button>
    </section>
  );
}
