'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ArrowRight, Check, Coins, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useStore } from '@/lib/store';
import { useHydrated } from '@/lib/useHydrated';
import { previewResume, startHunt } from '@/lib/huntClient';
import { Input } from '@/components/shared/Input';
import { Select } from '@/components/shared/Select';
import { Combobox } from '@/components/wizard/Combobox';
import { ResumeUpload } from '@/components/wizard/ResumeUpload';
import type { Profile, ResumeMeta, ResumePreview } from '@/lib/types';

const provinces = ['Alberta','British Columbia','Manitoba','New Brunswick','Newfoundland and Labrador','Northwest Territories','Nova Scotia','Nunavut','Ontario','Prince Edward Island','Quebec','Saskatchewan','Yukon'];
const schools = ['Western University','University of Toronto','McMaster University',"Queen's University",'University of Waterloo','University of Ottawa','York University','Toronto Metropolitan University','Carleton University','University of Guelph','Wilfrid Laurier University','Brock University','Trent University','Ontario Tech University','University of Windsor','Lakehead University','Laurentian University','McGill University','Concordia University','Université de Montréal','University of British Columbia','Simon Fraser University','University of Victoria','University of Alberta','University of Calgary','University of Saskatchewan','University of Manitoba','Dalhousie University','University of New Brunswick','Memorial University of Newfoundland','Fanshawe College','Humber College','Seneca Polytechnic','George Brown College','Conestoga College'];
const fields = ['Engineering','Computer Science','Health Sciences','Business','Arts and Humanities','Science','Education','Social Sciences','Other'];
const years = ['1st','2nd','3rd','4th','5th+','Graduate'];
const incomes = ['Under $30k','$30k–$60k','$60k–$100k','Over $100k','Prefer not to say'];
const statuses = ['Citizen','Permanent resident','Study permit','Other'];
const chipKeys = ['field','year','incomeRange','status'] as const;
const chipOptions: readonly string[][] = [fields, years, incomes, statuses];
const totalSteps = 8;
const demo: Profile = { fullName: 'Alex Chen', province: 'Ontario', school: 'Western University', field: 'Engineering', year: '2nd', incomeRange: '$30k–$60k', status: 'Citizen', resume: null };
const labels = ["What's your full name?", 'Where do you live?', 'Where do you study?', 'What do you study?', 'What year are you in?', "What's your household income?", "What's your status in Canada?", 'Upload your resume'];

const emptyProfile: Profile = { ...demo, fullName: '', school: '', field: '', year: '', incomeRange: '', status: '', resume: null };

type PreviewState = 'idle' | 'reading' | 'ready' | 'failed';

export default function Start() {
  const router = useRouter();
  const hydrated = useHydrated();
  const save = useStore((s) => s.setProfile);
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ResumePreview | null>(null);
  const [previewState, setPreviewState] = useState<PreviewState>('idle');
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [continueWithout, setContinueWithout] = useState(false);
  const loaded = useRef(false);

  useEffect(() => {
    if (!hydrated || loaded.current) return;
    loaded.current = true;
    const stored = useStore.getState().profile;
    if (stored) setProfile(stored);
  }, [hydrated]);

  const resumeDataUrl = profile.resume?.dataUrl ?? null;
  const resumeName = profile.resume?.name ?? 'resume.pdf';

  useEffect(() => {
    if (!resumeDataUrl) {
      setPreview(null);
      setPreviewState('idle');
      setPreviewError(null);
      return;
    }
    let cancelled = false;
    setPreview(null);
    setPreviewState('reading');
    setPreviewError(null);
    previewResume(resumeDataUrl, resumeName)
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setPreviewState('ready');
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setPreview(null);
        setPreviewState('failed');
        setPreviewError(reason instanceof Error ? reason.message : "We couldn't read that resume.");
      });
    return () => {
      cancelled = true;
    };
  }, [resumeDataUrl, resumeName]);

  const values = [profile.fullName, profile.province, profile.school, profile.field, profile.year, profile.incomeRange, profile.status];
  const valid =
    step === 0
      ? profile.fullName.trim().length >= 2
      : step === 7
        ? Boolean(profile.resume?.dataUrl) || continueWithout
        : Boolean(values[step]);
  const startReady =
    !profile.resume || continueWithout || (Boolean(profile.resume.dataUrl) && previewState === 'ready');

  function patch<K extends keyof Profile>(key: K, value: Profile[K]) {
    const next = { ...profile, [key]: value };
    setProfile(next);
    save(next);
  }

  function setResume(resume: ResumeMeta | null) {
    if (resume) setContinueWithout(false);
    patch('resume', resume);
  }

  function advance() {
    if (step === 7 && !profile.resume && !continueWithout) {
      toast.error('Upload a resume or choose to continue without one.');
      return;
    }
    if (step < totalSteps - 1) {
      setStep(step + 1);
      return;
    }
    setStep(totalSteps);
  }

  async function begin() {
    if (!startReady) {
      toast.error('Re-upload your resume, wait for the preview, or continue without it.');
      setStep(7);
      return;
    }
    setBusy(true);
    save(profile);
    try {
      const id = await startHunt(profile);
      router.push(`/hunt/${id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'The hunt could not start.');
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg text-ink">
      <header className="mx-auto flex h-16 w-full max-w-[1100px] items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5 text-lg font-extrabold">
          <span className="grid size-9 place-items-center rounded-xl bg-brand text-white">
            <Coins size={18} />
          </span>
          Unclaimed
        </Link>
        <button
          type="button"
          onClick={() => {
            setProfile(demo);
            save(demo);
            setContinueWithout(false);
            setStep(totalSteps);
          }}
          className="text-sm font-semibold text-brand hover:underline"
        >
          Use demo profile
        </button>
      </header>

      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-10">
        <div className="min-h-[440px] w-full max-w-[560px] overflow-visible rounded-card border border-border bg-white p-6 shadow-card sm:p-8">
          <div className="mb-8">
            <div className="mb-2 flex justify-between text-xs font-semibold text-muted">
              <span>{step < totalSteps ? `Step ${step + 1} of ${totalSteps}` : 'Your profile'}</span>
              <span>{step < totalSteps ? `${Math.round(((step + 1) / totalSteps) * 100)}%` : '100%'}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-brand-tint">
              <div
                className="h-full rounded-full bg-brand transition-all duration-300"
                style={{ width: `${Math.min(((step + 1) / totalSteps) * 100, 100)}%` }}
              />
            </div>
          </div>

          {step < totalSteps ? (
            <>
              <p className="text-sm font-semibold text-brand">A little about you</p>
              <h1 className="mt-2 text-2xl font-extrabold">{labels[step]}</h1>

              {step === 0 && (
                <>
                  <p className="mt-2 text-sm text-muted">As it appears on official documents. We use it to prefill forms.</p>
                  <Input
                    autoFocus
                    className="mt-6"
                    placeholder="Your full name"
                    value={profile.fullName}
                    onChange={(event) => patch('fullName', event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && valid) advance();
                    }}
                  />
                </>
              )}

              {step === 1 && (
                <Select
                  autoFocus
                  className="mt-6"
                  value={profile.province}
                  onChange={(event) => patch('province', event.target.value)}
                >
                  {provinces.map((province) => (
                    <option key={province}>{province}</option>
                  ))}
                </Select>
              )}

              {step === 2 && (
                <div className="mt-6">
                  <Combobox
                    autoFocus
                    value={profile.school}
                    onChange={(school) => patch('school', school)}
                    options={schools}
                    onEnter={() => {
                      if (valid) advance();
                    }}
                  />
                </div>
              )}

              {step === 7 && (
                <>
                  <p className="mt-2 text-sm text-muted">
                    Attach a PDF so agents can use your experience as evidence for every award they check.
                  </p>
                  <div className="mt-6">
                    <ResumeUpload resume={profile.resume ?? null} onChange={setResume} />
                  </div>

                  {profile.resume && !profile.resume.dataUrl ? (
                    <p className="mt-3 text-[13px] font-semibold text-warn">
                      Re-upload your resume so we can read it.
                    </p>
                  ) : null}

                  {previewState === 'reading' ? (
                    <p className="mt-3 flex items-center gap-2 text-[13px] font-semibold text-muted">
                      <Loader2 size={14} className="animate-spin" /> Reading your resume…
                    </p>
                  ) : null}

                  {previewState === 'ready' && preview ? (
                    <p className="mt-3 text-[13px] font-semibold text-money">
                      Resume read: {preview.characters.toLocaleString()} characters · Top angles:{' '}
                      {preview.angles.slice(0, 5).join(' · ') || 'none found yet'}
                    </p>
                  ) : null}

                  {previewState === 'failed' ? (
                    <p className="mt-3 text-[13px] font-semibold text-danger">
                      {previewError || "We couldn't read your resume. Upload a PDF with selectable text."}
                    </p>
                  ) : null}

                  <label className="mt-4 flex items-start gap-2 text-sm text-ink">
                    <input
                      type="checkbox"
                      checked={continueWithout}
                      onChange={(event) => {
                        const checked = event.target.checked;
                        setContinueWithout(checked);
                        if (checked) {
                          setPreview(null);
                          setPreviewState('idle');
                          setPreviewError(null);
                          patch('resume', null);
                        }
                      }}
                      className="mt-0.5 size-4 accent-[var(--color-brand)]"
                    />
                    <span>Continue without my resume</span>
                  </label>

                  <button
                    type="button"
                    onClick={() => {
                      setContinueWithout(true);
                      patch('resume', null);
                      setStep(totalSteps);
                    }}
                    className="mt-3 text-sm font-semibold text-muted hover:text-ink"
                  >
                    Skip for now
                  </button>
                </>
              )}

              {step === 5 && (
                <p className="mt-2 text-sm text-muted">Used only to check which programs fit. You can skip this.</p>
              )}

              {step >= 3 && step <= 6 && (
                <div className="mt-6 flex flex-wrap gap-2">
                  {chipOptions[step - 3].map((option) => {
                    const key = chipKeys[step - 3];
                    const selected = profile[key] === option;
                    return (
                      <button
                        key={option}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => patch(key, option)}
                        className={`inline-flex h-11 items-center gap-1.5 rounded-xl border px-4 text-sm font-semibold transition-colors ${
                          selected
                            ? 'border-brand bg-brand text-white'
                            : 'border-border bg-white text-ink hover:border-brand'
                        }`}
                      >
                        {option}
                        {selected && <Check size={15} />}
                      </button>
                    );
                  })}
                </div>
              )}

              <div className="mt-9 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => (step === 0 ? router.push('/') : setStep(step - 1))}
                  className="inline-flex h-11 items-center gap-2 px-2 text-sm font-semibold text-muted transition-colors hover:text-ink"
                >
                  <ArrowLeft size={16} />
                  Back
                </button>
                <button
                  type="button"
                  onClick={advance}
                  disabled={!valid}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-brand px-6 font-semibold text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-brand"
                >
                  Continue <ArrowRight size={17} />
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold text-brand">Almost there</p>
              <h1 className="mt-2 text-2xl font-extrabold">Ready to hunt?</h1>
              <div className="mt-6 divide-y divide-border">
                {labels.map((label, index) => {
                  const keys: (keyof Profile)[] = ['fullName','province','school','field','year','incomeRange','status','resume'];
                  const key = keys[index];
                  const value = key === 'resume' ? profile.resume?.name : profile[key];
                  return (
                    <div key={label} className="flex items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="text-xs text-muted">{label}</p>
                        <p className="mt-1 truncate text-sm font-semibold">{value || '—'}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setStep(index)}
                        className="shrink-0 text-sm font-semibold text-brand"
                      >
                        Edit
                      </button>
                    </div>
                  );
                })}
              </div>

              {profile.resume && !profile.resume.dataUrl ? (
                <div className="mt-4 rounded-xl border border-warn/40 bg-warn-tint p-3">
                  <p className="text-[13px] font-semibold text-warn">Re-upload your resume</p>
                  <p className="mt-1 text-xs leading-5 text-ink">
                    The PDF itself is not kept between visits. Attach it again so this hunt can use it.
                  </p>
                  <button
                    type="button"
                    onClick={() => setStep(7)}
                    className="mt-2 text-xs font-bold text-brand hover:underline"
                  >
                    Upload resume
                  </button>
                </div>
              ) : null}

              {profile.resume && profile.resume.dataUrl && previewState === 'reading' ? (
                <p className="mt-4 flex items-center gap-2 text-[13px] font-semibold text-muted">
                  <Loader2 size={14} className="animate-spin" /> Reading your resume…
                </p>
              ) : null}

              {profile.resume && profile.resume.dataUrl && previewState === 'failed' ? (
                <p className="mt-4 text-[13px] font-semibold text-danger">
                  {previewError || 'We could not read your resume yet.'}
                </p>
              ) : null}

              <button
                type="button"
                onClick={begin}
                disabled={busy || !startReady}
                className="btn-primary mt-6 h-14 w-full text-base disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? 'Getting your hunt ready…' : 'Start the hunt'} <ArrowRight size={18} />
              </button>
              <p className="mt-3 text-center text-xs text-muted">
                {startReady
                  ? 'Your answers help us find relevant programs. Nothing is applied for without you.'
                  : 'Start unlocks as soon as the resume preview finishes.'}
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
