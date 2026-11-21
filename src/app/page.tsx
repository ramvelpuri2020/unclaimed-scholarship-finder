'use client';

import Link from 'next/link';
import { ArrowRight, BriefcaseBusiness, Coins, GraduationCap, Landmark, Receipt, Sparkles, Users, WalletCards } from 'lucide-react';
import { HeroPreview } from '@/components/landing/HeroPreview';

const topics = [['Federal grants', Coins], ['Provincial student aid', Landmark], ['Tuition tax credits', Receipt], ['University bursaries', GraduationCap], ['Community foundations', Users], ['Industry awards', BriefcaseBusiness], ['Municipal youth programs', Landmark], ['Education savings grants', WalletCards]] as const;

export default function Landing() {
  return (
    <main className="min-h-screen overflow-hidden bg-bg text-ink">
      <header className="mx-auto flex h-16 w-full max-w-[1100px] items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-3 text-lg font-extrabold">
          <span className="grid size-9 place-items-center rounded-xl bg-brand text-white">
            <Coins size={20} />
          </span>
          Unclaimed
        </Link>
        <Link href="/start" className="btn-primary h-12 rounded-xl px-6">
          Find my money <ArrowRight size={17} />
        </Link>
      </header>

      <section className="mx-auto max-w-[1100px] px-6 pb-16 pt-12 md:pt-20">
        <div className="grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div className="max-w-[640px]">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-brand-tint px-4 py-2 text-sm font-semibold text-brand">
              <Sparkles size={16} /> AI agents that read the real web
            </div>
            <h1 className="max-w-[640px] text-[40px] font-extrabold leading-[1.05] tracking-[-0.02em] [word-spacing:normal] sm:text-[52px] lg:text-[64px]">
              There's money out there with your name on it.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-muted md:text-xl">
              Canadian students leave thousands unclaimed because finding it means digging through dozens of websites. Our AI employee does the digging for you.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-5">
              <Link href="/start" className="btn-primary h-12 rounded-xl px-6 text-base">
                Find my money <ArrowRight size={18} />
              </Link>
              <span className="max-w-xs text-sm leading-6 text-muted">
                Takes about 2 minutes. Nothing is applied for without your approval.
              </span>
            </div>
          </div>
          <HeroPreview />
        </div>

        <div className="marquee-mask relative mt-16 border-y border-border py-4">
          <div className="marquee-track flex w-max animate-marquee gap-3">
            {[...topics, ...topics].map(([label, Icon], index) => (
              <span
                key={`${label}-${index}`}
                className="flex items-center gap-2 rounded-full border border-border bg-white px-4 py-2.5 text-sm font-semibold shadow-card"
              >
                <Icon size={16} className="text-brand" />
                {label}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {[
            ['1', 'Tell us about you', 'Eight quick questions. No logins needed.'],
            ['2', 'Agents check real sites', 'Watch our agents visit the actual websites and read the eligibility rules.'],
            ['3', 'Review and apply', 'See what you likely qualify for, ranked, with the exact next step.'],
          ].map(([number, title, body]) => (
            <article
              key={number}
              className="rounded-card border border-border bg-white p-6 shadow-card transition-transform hover:-translate-y-1"
            >
              <span className="grid size-9 place-items-center rounded-xl bg-brand-tint font-bold text-brand">{number}</span>
              <h2 className="mt-5 text-lg font-bold">{title}</h2>
              <p className="mt-2 leading-6 text-muted">{body}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="border-t border-border px-6 py-7 text-center text-sm text-muted">
        Unclaimed is a hackathon project. Eligibility results are estimates. Always confirm on the official page.
      </footer>
    </main>
  );
}
