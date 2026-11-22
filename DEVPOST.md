# Devpost submission — Unclaimed

Hack Western 13 · Theme: *Discover the unknown* · November 20–22, 2026

---

## Elevator pitch

**There's money out there with your name on it. Unclaimed sends AI agents to read the real web and find it.**

Unclaimed is an AI employee for Canadian students: it plans its own scholarship searches, opens real university and foundation pages, verifies the eligibility rules, and returns ranked matches with the exact source quote that proves each one.

---

## Inspiration

Every Canadian student has heard "there are thousands of unclaimed scholarships." Almost nobody finds them, because the money is not in one place. It is in a faculty page that has not been redesigned since 2011, a community foundation's PDF, a professional association's member-only award, and a company scholarship that never bought an ad.

Search engines return expired aggregator lists and government aid pages. Students give up, or they apply to the same three big awards as everyone else.

Hack Western 13's theme, **Discover the unknown**, felt like a direct instruction. The unknown is not a new planet — it is the $2,000 bursary sitting three clicks deep on your own university's website.

We also built for the **Canada Life Future Me** challenge. Canada Life's research says young Canadians disengage from long-term planning because the future feels uncertain. A list of deadlines is not motivating. A number that says "you could put $14,000 behind next year if you send four applications" is.

---

## What it does

1. **Eight quick questions, no account.** Province, school, field, year, household income, status in Canada, and an optional PDF resume. The resume is optional because requiring it loses users.
2. **Gemini writes the search plan.** It reads the resume and profile and produces 16 diverse queries, with at least six naming the student's own university or faculty and at least five targeting awards open to any Canadian university.
3. **TinyFish does the legwork.** Search finds candidate pages. Fetch opens them. A browser agent can open an awards index, follow pagination, and return the individual award links. Government, social, aggregator, PDF, and login URLs are filtered out before fetching.
4. **Gemini reads each page into a strict schema.** Award name, provider, amount, deadline, eligibility criteria, verbatim quotes, strong/good/weak fit, gaps, and the next step.
5. **A deterministic verifier decides what survives.** Quotes must appear in the full page text. Deadlines must be real, within 420 days, and stated near a deadline keyword. Contradicted eligibility, entrance awards, government programmes, stale pages, and duplicates are dropped. Anything left without a confirmable date goes into a visible "check before applying" section rather than getting an invented one.
6. **Results stream in live.** The hunt page shows each stage, the agent's progress, and the agent's live browser view when TinyFish provides one. Verified awards appear one by one.
7. **Future Me makes it a plan.** Confirmed awards become a funding total, a next deadline, and an application calendar.

Nothing is applied for automatically. Every match links back to the official page.

---

## How we built it

**Stack:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Zustand and Server-Sent Events on the frontend. FastAPI, Python 3.12, async worker pools, priority queues, and SSE on the backend. **Google Gemini** for resume reading, query planning, and structured page extraction. **TinyFish** for search, page fetch, and the browser agent.

The backend is a streaming pipeline, not a batch job. A hunt starts with one Gemini planning call, runs TinyFish searches concurrently, ranks every candidate, and feeds a score-ordered queue. Fetch workers pull batches of URLs and stream each readable page straight into extraction. Extraction workers send up to three pages per Gemini call with a strict JSON schema; any page the model omits is retried alone on another model. Verified results are emitted immediately.

The most important architectural choice was separating **extraction** from **verification**. Gemini reports facts and quotes. Python proves them: normalized substring matching for quotes, date parsing and programme-section rescuing for deadlines, and explicit rules for school, province, level of study, year of study, citizenship, identity restrictions, and duplicates. If we cannot prove it, it does not ship.

We also built a CLI runner that prints funnel counts, first-fetch/first-extract/first-verified timings, drop reasons, and the final table. That is how we debugged real hunts without clicking through the UI.

---

## Challenges we ran into

- **The model confidently invented deadlines.** Our first hunts had beautiful, wrong answers. We fixed it by requiring verbatim quotes, checking them against the full page text (not the trimmed excerpt), rescuing dates only from the programme's own section, and dropping pages with unusable dates instead of guessing.
- **The open web is mostly noise.** Aggregators, government pages, social posts, PDFs, and login walls dominated search. We added hard URL filters and a ranking step before we spent a single fetch.
- **Latency under a wall clock.** We stopped treating the hunt as a sequence. Fetch and extract now run as continuous worker pools, later rounds start when the queues drain, and the hunt finishes as soon as it hits its result or time budget.
- **Gemini rate limits.** Free-tier limits are per model, not per key. We built a model pool that paces RPM/TPM/RPD, probes which models the key can use at startup, retries and fails over, and shares a hard per-hunt call budget.
- **TinyFish agent constraints.** Agent runs are limited and the SDK has no cancel method. We run at most one optional list agent, with a timeout and an orphan-run guard, so the live-browser moment can never block search and fetch.
- **Year-of-study wording.** "Entering third year" targets a current second-year student, and entrance awards are not for enrolled students. We encoded those semantics explicitly and tested them.
- **Scanned resumes.** Text extraction failed, so we send the PDF directly to Gemini instead of running our own OCR. If the resume fails, the hunt continues on profile facts and says so.

---

## Accomplishments that we're proud of

- A working end-to-end agent pipeline on live websites — no mock programme list, no seeded database, no padding.
- Evidence-first results. Every verified award carries source quotes and a next step.
- An honest "deadline not confirmed" section instead of fake precision.
- A verifier that is deliberately separate from the language model, with real eligibility rules rather than vibes.
- The live browser view during a hunt. Watching an agent open a university page is the demo.
- Future Me, which only counts money with a confirmed date and turns it into a calendar.
- Failure modes that tell the truth: missing keys stop the server with the variable name, bad keys stop the hunt with plain English, and partial results are kept when a quota runs out.

---

## What we learned

- An LLM's output is a claim, not a fact. The verifier is the product.
- Strict schemas and written rubrics beat clever prompting for consistency.
- Concurrency needs backpressure; fetching faster than extraction only fills memory.
- API budgets and rate limits are architecture, not cleanup.
- Treat uploaded resumes as untrusted input and strip contact details before showing evidence.
- Designing for the demo — visible agents, streaming results, real quotes — made the product better, not just the pitch.

---

## What's next for Unclaimed

- Accounts and saved profiles, so students do not re-enter the wizard every visit.
- Deadline reminders and a weekly "new money" digest.
- More sources: French-language pages, provincial foundations, Indigenous and equity-specific awards, graduate funding.
- Application tracking with human-in-the-loop prefill — review and submit, never auto-submit.
- Better amount normalization and a confidence score calibrated on verified hunts.
- A deployed demo with a job queue and a freshness-aware result cache.

---

## Did you implement a generative AI model or API?

**Yes.**

We integrated the **Google Gemini API** (`google-genai`) in three places:

1. **Resume understanding** — the uploaded PDF is sent directly to Gemini, which returns a compact factual profile. This also handles scanned resumes without a separate OCR pipeline.
2. **Search planning** — Gemini writes the hunt's queries from the resume and profile, with quotas for the student's own school and for national awards, and uses per-angle outcome tables in later rounds to replace search angles that produced nothing.
3. **Structured page extraction** — Gemini converts each fetched award page into a strict JSON schema containing amount, deadline, eligibility criteria, verbatim quotes, fit, gaps, and next step.

We also used **TinyFish's browser agents**, which are AI agents operating a real browser, to read award index pages and return structured lists of awards.

Why: the problem is unstructured natural-language research across hundreds of inconsistent pages. That is exactly what these models are good at. But we deliberately kept the final decision deterministic — Gemini proposes quotes and eligibility facts, and Python verifies them against the source page. That combination is what lets us show a result we can defend.

---

## Built with

`next.js` · `react` · `typescript` · `tailwind-css` · `zustand` · `framer-motion` · `fastapi` · `python` · `google-gemini` · `tinyfish` · `server-sent-events` · `pydantic`
