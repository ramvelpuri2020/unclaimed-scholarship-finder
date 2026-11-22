'use client';

import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Award,
  Building2,
  Check,
  Coins,
  GraduationCap,
  Landmark,
  MapPin,
  PiggyBank,
  Receipt,
  Users,
} from 'lucide-react';

const STAGES = [
  'Reading your answers',
  'Choosing where to look',
  'Sending your agents',
  'Opening real websites',
] as const;

const CHIPS = [
  { label: 'Federal grants', Icon: Landmark },
  { label: 'Provincial aid', Icon: MapPin },
  { label: 'Tax credits', Icon: Receipt },
  { label: 'Your school', Icon: GraduationCap },
  { label: 'Faculty awards', Icon: Award },
  { label: 'Community funds', Icon: Users },
  { label: 'Industry awards', Icon: Building2 },
  { label: 'Savings grants', Icon: PiggyBank },
] as const;

const PROGRESS = [18, 40, 65, 90] as const;

function TypingDots() {
  return (
    <span className="ml-2 inline-flex items-center gap-1" aria-hidden="true">
      {[0, 1, 2].map((dot) => (
        <motion.span
          key={dot}
          className="size-1.5 rounded-full bg-brand"
          animate={{ opacity: [0.25, 1, 0.25], y: [0, -2, 0] }}
          transition={{ duration: 0.9, repeat: Infinity, delay: dot * 0.15, ease: 'easeInOut' }}
        />
      ))}
    </span>
  );
}

export function HuntLaunch({ firstName }: { firstName: string }) {
  const reduceMotion = useReducedMotion() ?? false;
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (stage >= STAGES.length - 1) return;
    const timer = window.setTimeout(() => setStage((current) => current + 1), 1200);
    return () => window.clearTimeout(timer);
  }, [stage]);

  const litCount = Math.min(CHIPS.length, (stage + 1) * 2);

  return (
    <motion.div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <section className="relative w-full overflow-hidden rounded-[24px] border border-border bg-white px-5 py-8 shadow-card sm:px-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(circle at 50% 38%, rgba(15,118,110,0.14) 0%, rgba(15,118,110,0.035) 40%, transparent 68%)',
          }}
        />

        <div className="relative mx-auto max-w-4xl">
          <div className="relative mx-auto h-[420px] w-full max-w-[560px] scale-[0.78] sm:h-[520px] sm:scale-100">
            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
              {!reduceMotion
                ? [0, 1, 2].map((ring) => (
                    <motion.span
                      key={ring}
                      aria-hidden="true"
                      className="absolute inset-0 rounded-full border border-brand/40"
                      initial={{ scale: 1, opacity: 0.35 }}
                      animate={{ scale: 2.2, opacity: 0 }}
                      transition={{
                        duration: 2.4,
                        repeat: Infinity,
                        delay: ring * 0.8,
                        ease: 'easeOut',
                      }}
                    />
                  ))
                : null}
              <div className="relative grid size-[120px] place-items-center rounded-full bg-brand shadow-[0_18px_50px_rgba(15,118,110,0.28)]">
                <Coins aria-hidden="true" className="text-white" size={52} strokeWidth={1.7} />
              </div>
            </div>

            <motion.div
              className="absolute inset-0"
              animate={reduceMotion ? undefined : { rotate: 360 }}
              transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}
            >
              {CHIPS.map(({ label, Icon }, index) => {
                const angle = (index / CHIPS.length) * Math.PI * 2;
                const x = Math.cos(angle) * 220;
                const y = Math.sin(angle) * 220;
                const lit = index < litCount;
                return (
                  <div
                    key={label}
                    className="absolute left-1/2 top-1/2"
                    style={{ transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))` }}
                  >
                    <motion.div
                      animate={reduceMotion ? undefined : { rotate: -360 }}
                      transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}
                    >
                      <span
                        className={`flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-2 text-[11px] font-semibold shadow-card transition-colors duration-500 ${
                          lit
                            ? 'border-brand bg-brand-tint text-brand'
                            : 'border-border bg-white text-muted'
                        }`}
                      >
                        <Icon aria-hidden="true" size={13} />
                        {label}
                      </span>
                    </motion.div>
                  </div>
                );
              })}
            </motion.div>
          </div>

          <div className="mx-auto -mt-2 max-w-md text-center">
            <h1 className="text-[28px] font-bold leading-tight text-ink">
              Getting your hunt ready, {firstName}
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted">
              We pick the best places to look, then send agents to read them for you.
            </p>
          </div>

          <ol className="mx-auto mt-7 max-w-md space-y-3" aria-label="Hunt preparation stages">
            {STAGES.map((label, index) => {
              const done = index < stage;
              const active = index === stage;
              return (
                <li key={label} className="flex items-center gap-3 text-sm">
                  <span
                    className={`grid size-6 shrink-0 place-items-center rounded-full border transition-colors ${
                      done
                        ? 'border-brand bg-brand text-white'
                        : active
                          ? 'border-brand bg-white text-brand'
                          : 'border-border bg-white text-transparent'
                    }`}
                  >
                    {done ? (
                      <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true">
                        <motion.path
                          d="M5 12.5l4.5 4.5L19 7.5"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={3}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          initial={reduceMotion ? false : { pathLength: 0 }}
                          animate={{ pathLength: 1 }}
                          transition={{ duration: 0.35, ease: 'easeOut' }}
                        />
                      </svg>
                    ) : active && index === STAGES.length - 1 ? (
                      <motion.span
                        aria-hidden="true"
                        className="size-3 rounded-full border-2 border-brand border-t-transparent"
                        animate={reduceMotion ? undefined : { rotate: 360 }}
                        transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                      />
                    ) : active ? (
                      <span className="size-1.5 rounded-full bg-brand" aria-hidden="true" />
                    ) : (
                      <Check aria-hidden="true" size={12} className="opacity-0" />
                    )}
                  </span>
                  <span
                    className={`flex items-center transition-colors ${
                      active ? 'font-semibold text-brand' : done ? 'text-ink' : 'text-muted'
                    }`}
                  >
                    {label}
                    {active && !reduceMotion ? <TypingDots /> : null}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="relative mx-auto mt-7 h-1.5 max-w-4xl overflow-hidden rounded-full bg-brand-tint">
          <motion.div
            className="h-full rounded-full bg-brand"
            initial={false}
            animate={{ width: `${PROGRESS[stage]}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />
        </div>
      </section>

      <p className="mt-3 text-center text-[13px] text-muted">
        Agents only read public pages. Nothing is submitted for you.
      </p>

      <p className="sr-only">Stage {stage + 1} of {STAGES.length}: {STAGES[stage]}</p>
    </motion.div>
  );
}
