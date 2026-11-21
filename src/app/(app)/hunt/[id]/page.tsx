import HuntView from './HuntView';

// `output: 'export'` requires every dynamic segment to be known at build time.
// The mock hunt always runs as "demo" (see lib/huntClient.ts), so that's the
// only id that needs its own static page.
export function generateStaticParams() {
  return [{ id: 'demo' }];
}

export default function HuntPage() {
  return <HuntView />;
}
