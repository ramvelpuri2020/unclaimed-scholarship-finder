import { cn } from '@/lib/utils';

export function MatchBadge({ confidence }: { confidence: number }) {
  const label = confidence >= 0.85 ? 'Strong match' : confidence >= 0.65 ? 'Likely' : 'Maybe';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold',
        confidence >= 0.85
          ? 'bg-money-tint text-money'
          : confidence >= 0.65
            ? 'bg-brand-tint text-brand'
            : 'bg-warn-tint text-warn',
      )}
    >
      {label} · {Math.round(confidence * 100)}%
    </span>
  );
}
