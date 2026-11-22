# Unclaimed

**There's money out there with your name on it. Unclaimed sends AI agents to read the real web and find it.**

Unclaimed is a full-stack hackathon project built at **Hack Western 13** (November 20–22, 2026) for the theme *Discover the unknown*. It finds scholarships, bursaries, and student awards that Canadian students are actually eligible for — from universities, faculties, foundations, companies, and community organizations — and shows the exact quote from the source page that proves each result.

It is not an aggregator. There is no scraped database, no mock list, and no padding. A live hunt plans its own searches, opens real websites, extracts the eligibility rules with Gemini, and then a deterministic verifier throws out anything it cannot prove.

> **Hackathon demo:** run it locally in about five minutes. See [Quick start](#quick-start).

---

## What it does

1. **Eight questions, no account.** Province, school, program, year, household income, status in Canada, and an optional PDF resume.
2. **Gemini plans the hunt.** It reads the resume and profile and writes 16 diverse scholarship queries, with hard quotas for the student's own school/faculty and for awards open to any Canadian university.
3. **TinyFish searches and reads the live web.** Search results are filtered (no government, social, aggregator, PDF, or login pages), ranked, and fetched concurrently. A browser agent can open a university awards index, follow pagination, and return the individual award links.
4. **Gemini extracts each page into a strict JSON schema.** Name, provider, amount, deadline, eligibility criteria, verbatim quotes, fit, gaps, and next step.
5. **Python verifies everything.** Quotes must appear verbatim in the full page text. Deadlines must be real and near a deadline keyword. Entrance/high-school awards, government programs, duplicates, and contradicted eligibility are dropped. Anything left without a confirmable deadline is moved to a clearly labelled "check before applying" section instead of being given a fake date.
6. **Results stream into the UI as they are verified.** The live hunt page shows each stage, the agent's activity, and — when TinyFish provides it — the agent's live browser view.
7. **Future Me turns matches into a plan.** It totals the listed funding, counts confirmed awards, finds the next deadline, and builds an application calendar.

Nothing is submitted on the student's behalf. Every match links back to the official page.

---

## Sponsors and APIs

Unclaimed was built around two sponsor APIs, and one sponsor challenge shaped a whole page of the product.

### TinyFish — *Hire Your First AI Employee*

TinyFish is the "employee" doing the browser work, not a search box bolted on at the end.

| TinyFish capability | How Unclaimed uses it |
| --- | --- |
| **Search** (`search.query`, `location="CA"`) | Runs the 16+ Gemini-written queries and returns candidate award pages. |
| **Fetch** | Reads live award pages as rendered pages, with an `httpx` + `trafilatura` fallback, robots.txt checks, and a circuit breaker when TinyFish reports a daily fetch limit. |
| **Browser agent** (`agent.stream`) | One read-only agent opens a university/foundation awards index, follows pagination, and returns up to 30 individual awards as structured JSON. Its progress events and live streaming URL are pushed to the hunt UI. |

Why this fits *Hire Your First AI Employee*: the job is completed end to end on the real web — plan searches, find pages, open them, read the rules, verify, and report. The agent never logs in, submits a form, or applies. We deliberately cap it at one list agent so an agent run cannot starve the search/fetch pipeline.

> Hackathon note: this project targets the TinyFish prize. To qualify, the demo needs to be posted on X or LinkedIn and tag TinyFish.

### Google Gemini — *Best Use of Gemini API*

Gemini is used for the parts that genuinely need language understanding:

- **Reading the resume PDF directly** (including scanned PDFs, no separate OCR step). The PDF is processed in memory and contact details are stripped before any evidence is shown.
- **Planning queries** grounded in resume facts, with per-angle outcome feedback on later rounds so dead search angles are replaced.
- **Extracting award pages** into a strict JSON schema: amount, deadline, eligibility, verbatim quotes, fit (`strong` / `good` / `weak`), gaps, and next step.
- **Falling back across a model pool**: models are paced per RPM/TPM/RPD limits, retried on rate limits, and failed over, with a hard per-hunt call budget.

We intentionally do **not** let Gemini be the final judge. It proposes facts and quotes; deterministic Python checks them against the source page. That split is what makes the results demo-able without hoping the model behaved.

### Canada Life — *The Future Me Challenge*

The **Future Me** page is our answer to "turn uncertainty into confidence". It takes only awards with a confirmed deadline (or a confirmed rolling/cycle status) and turns them into:

- a **funding-in-play** number, $\sum_i \text{amountMax}_i$ over verified awards,
- a count of confirmed awards,
- the next deadline,
- an application calendar sorted by date.

It is deliberately honest: awards with no confirmed date are excluded from the projection, and the page says so.

### Prize alignment at a glance

| Track | Status |
| --- | --- |
| TinyFish — Hire Your First AI Employee | Core integration (search + fetch + agent) |
| MLH — Best Use of Gemini API | Core integration (resume, planning, extraction, fit) |
| Canada Life — Future Me Challenge | Future Me funding plan + deadline calendar |
| Sun Life health, QNX, PCBWay hardware, Solana, Tiger Data, Vultr, Auth0, Entire, GoDaddy | Not targeted by this build |

---

## How it works

```text
 profile + optional resume PDF
              │
              ▼
   Gemini planner  ─────────────►  TinyFish Search (16 queries, CA)
              │                              │
              │                              ▼
              │                    hard URL filters + ranking
              │                              │
              │                              ▼
              │                 priority queue → fetch workers
              │                 (TinyFish Fetch / httpx fallback)
              │                              │
              │                              ▼
              │                 Gemini extractor, 3 pages/call
              │                 strict JSON schema + verbatim quotes
              │                              │
              ▼                              ▼
   one TinyFish list agent        deterministic verifier
   (index pages only,             • quote substring check
    live browser view)            • deadline parse + rescue (≤ 420 days)
              │                   • entrance / government / duplicate drop
              └──────────────►    • school, province, level, year,
                                  • citizenship, identity checks
                                             │
                                             ▼
                                  verified Program objects
                                             │
                                             ▼
                         Server-Sent Events → Next.js UI
                         (live stages, live browser, matches, Future Me)
```

### The verification rules (the part that makes it trustworthy)

- A quote is only kept if it appears in the **full** page text, not just the trimmed excerpt sent to Gemini.
- A deadline must be a real date within 420 days and must sit near a deadline keyword in that programme's own section of the page.
- If a page shows dates but none are usable, the programme is **dropped as stale**, not given a guessed date.
- If no deadline is stated, the programme appears under **"Deadline not confirmed on the page"**.
- Entrance, admission, and high-school awards are dropped for already-enrolled students.
- Government programmes (`canada.ca`, `gc.ca`, `ontario.ca`, `*.gov.*`, OSAP, Canada Student Grants, CESG/RESP, CRA tuition credits) are out of scope by design.
- Year-of-study wording is handled explicitly: "entering year N" means the student is currently in year N−1; "all undergraduate years" and "continuing students" always match.
- Resume evidence must appear verbatim in the resume text, and lines containing email/phone/address are removed.
- Duplicate awards are dropped by normalized name + provider.

There is **no result cache and no mock fallback**. If only nine programmes survive verification, the hunt returns nine and says so.

### Architecture

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Zustand (persisted), Framer Motion, `EventSource` for SSE |
| Backend | FastAPI, Python 3.12, async worker pools and priority queues, Server-Sent Events |
| AI | Google Gemini (`google-genai`) for resume reading, planning, extraction and fit |
| Web | TinyFish SDK for search, fetch and the browser agent |
| Verification | Pure Python: quote matching, date parsing/rescue, eligibility rules, dedupe |

---

## Project structure

```text
.
├─ src/                        Next.js frontend
│  ├─ app/                     landing, wizard, live hunt, matches, saved, activity, future-me
│  ├─ components/              hunt, match, wizard, landing, shared UI
│  └─ lib/                     API client, SSE store, types, formatting
├─ backend/
│  ├─ app/
│  │  ├─ main.py               FastAPI app, SSE endpoint, resume preview
│  │  ├─ hunt.py               orchestrator, queues, rounds, persistence
│  │  ├─ agents.py             TinyFish list/index browser agent
│  │  ├─ resume.py             Gemini PDF resume reading
│  │  └─ pipeline/
│  │     ├─ planner.py         Gemini query planning + quotas
│  │     ├─ discovery.py       TinyFish search + URL filtering
│  │     ├─ reader.py          concurrent page fetching + fallback
│  │     ├─ extractor.py       strict-schema page extraction
│  │     ├─ verify.py          deterministic verification
│  │     └─ matcher.py         verified extraction → public Program
│  ├─ tests/                   offline pipeline and model-pool tests
│  └─ .env.example             backend env template
├─ scripts/run_hunt.py         CLI demo + funnel/timing diagnostics
└─ .env.example                frontend env template
```

---

## Quick start

### What you need

- **Node.js 20.9+** and npm
- **Python 3.12+**
- Two free API keys:
  - **TinyFish** — https://tinyfish.ai/students (hackathon credits) or your TinyFish dashboard
  - **Gemini** — https://aistudio.google.com/apikey

You run **two servers**: the FastAPI backend on port `8000` and Next.js on port `3000`.

### 1. Clone and install

```bash
git clone https://github.com/ramvelpuri2020/unclaimed-scholarship-finder.git
cd unclaimed-scholarship-finder
```

### 2. Backend — keys first

```bash
cd backend
cp .env.example .env
```

Open `backend/.env` and paste your keys:

```dotenv
TINYFISH_API_KEY=your_tinyfish_key_here
GEMINI_API_KEY=your_gemini_key_here
```

Then install and run:

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# source .venv/Scripts/activate    # Windows Git Bash
# .venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend **refuses to start** if either key is missing and names the exact variable. That is intentional — no silent mock mode.

Check it:

```bash
curl http://localhost:8000/api/health
# {"ok":true}
```

### 3. Frontend — second terminal

```bash
cd unclaimed-scholarship-finder
cp .env.example .env.local
npm install
npm run dev
```

Open **http://localhost:3000**, click **Find my money**, or use **Use demo profile** to skip the wizard.

> Codespaces/remote VM? Set `CORS_ORIGINS` in `backend/.env` to your frontend origin, and set `NEXT_PUBLIC_API_BASE_URL` in `.env.local` to the backend's public URL.

### 4. Optional — run a hunt from the CLI

The CLI prints funnel counts, stage timings, drop reasons, and the verified table, which is useful for debugging without the UI:

```bash
# from the repo root, with backend deps installed and backend/.env filled in
python scripts/run_hunt.py --demo
python scripts/run_hunt.py --demo --resume path/to/resume.pdf
```

---

## Environment variables

### Frontend — `.env.local` (from `.env.example`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Where the FastAPI backend lives. Restart `npm run dev` after changing it. |

The frontend has **no secret keys**. Both API keys stay in the backend.

### Backend — `backend/.env` (from `backend/.env.example`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `TINYFISH_API_KEY` | **required** | Search, page fetch, and the list agent. |
| `GEMINI_API_KEY` | **required** | Resume reading, query planning, page extraction. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | First model to try. The pool probes what your key can use and fails over. |
| `GEMINI_POOL_JSON` | unset | Optional per-model RPM/TPM/RPD overrides (JSON array). |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed frontend origins. |
| `STOP_AT_RESULTS` | `40` | Stop once this many results are committed. |
| `SEARCH_CONCURRENCY` | `4` | Concurrent search queries. |
| `FETCH_CONCURRENCY` | `12` | Concurrent page fetch workers. |
| `FETCH_BATCH` | `3` | URLs per fetch worker call. |
| `EXTRACT_CONCURRENCY` | `12` | Concurrent Gemini extraction calls. |
| `EXTRACT_PAGES_PER_CALL` | `3` | Pages bundled into one extraction call. |
| `PER_URL_TIMEOUT_MS` | `8000` | Per-page fetch timeout. |
| `MAX_PAGE_CHARS` | `9000` | Maximum page text sent for extraction. |
| `MAX_PAGES_ROUND_1` | `120` | Page budget for the first round. |
| `MAX_PAGES_LATER` | `50` | Page budget for later rounds. |
| `MAX_ROUNDS` | `4` | Maximum search rounds per hunt. |
| `MAX_GEMINI_CALLS` | `600` | Hard Gemini request budget per hunt. |
| `PLAN_QUERIES` | `16` | Queries in the first planning round. |
| `RESUME_EXTRACT_CHARS` | `3500` | Resume context characters kept for matching. |
| `WALL_TIMEOUT_SECONDS` | `180` | Whole-hunt wall clock. |
| `LIST_AGENT_TIMEOUT_SECONDS` | `60` | Timeout for the single optional browser agent. |
| `SELECTOR_ENABLED` | `true` | Enable the model-based page selector. |

> Never commit `backend/.env` or `.env.local`. They are gitignored; the `*.example` files are not.

---

## Resume privacy

- The PDF is sent as an in-memory base64 data URL and processed in memory. It is **not written to disk** by the backend.
- The frontend stores only the resume's name and size in `localStorage`, never the PDF itself. Reloading the page asks for the file again.
- Gemini returns a short factual profile; contact details are stripped, and resume evidence is only shown if the line appears verbatim in the resume and contains no email, phone, address, or profile URL.
- The PDF is treated as untrusted input: both the resume-reading prompt and the extraction prompt explicitly tell the model to ignore instructions inside it.

---

## How we built it

- **Friday — scope.** We cut government aid entirely. It is the first thing people expect a "scholarship finder" to do, but every other tool already covers it, and the forgotten money is in faculty pages and small foundations. That single decision made the search problem tractable in 36 hours.
- **Saturday — the pipeline.** We built the backend as a streaming pipeline instead of a batch job: planner → search → priority queue → fetch workers → extractor workers → verifier → SSE. We added the verifier after watching the model invent a deadline and confidently attach it to the wrong award.
- **Saturday night — the employee.** We wired the TinyFish browser agent to university award indexes and streamed its live browser URL into the hunt page, so the demo shows a browser actually working rather than a spinner.
- **Sunday — trust and polish.** We added the "deadline not confirmed" bucket, the evidence quotes, the entrance-award filter, resume contact stripping, Future Me, and the diagnostics CLI. Then we ran hunts against real sites until the failure modes were boring.

### Challenges we ran into

- **Models invent deadlines and amounts.** Fixed by making Gemini cite, then checking every quote against the full page text and rescuing dates only from the programme's own section. Unverifiable results are removed instead of repaired.
- **Search results are mostly noise.** Government pages, aggregators, social posts, PDFs, and login walls. Fixed with hard URL filters and domain-aware ranking.
- **Latency.** A hunt has a wall clock. Fixed with a continuous pipeline: fetch workers, extract workers, a score-ordered queue, immediate streaming of verified results, and a hard stop at the result/time budget.
- **Rate limits.** Gemini free-tier limits are per model. Fixed with a model pool that paces RPM/TPM/RPD, probes availability at startup, retries and fails over, and shares a per-hunt call budget.
- **TinyFish concurrency and no cancel.** Agent runs are limited and the SDK has no cancel call. Fixed by running at most one optional list agent, with a timeout and an orphan-run guard, while search/fetch continue independently.
- **Year-of-study wording.** "Entering third year" does not mean a current third-year student. Fixed with explicit year semantics and tests, plus dropping entrance awards.
- **Resume parsing.** Scanned PDFs broke text extraction. Fixed by sending the PDF directly to Gemini and keeping the resume optional — a failed resume read never kills the hunt.

### Accomplishments we're proud of

- A real end-to-end agent pipeline on live websites, with no mock results.
- Evidence-first matches: every verified award has a source quote and a next step.
- An honest "unconfirmed" section instead of fabricated deadlines.
- A deterministic verifier that is separate from the language model.
- Live browser visibility during a hunt.
- A Future Me plan that only counts money with a confirmed date.

### What we learned

- An LLM's output is a **claim**, not a fact. The verifier is the product.
- Structured output schemas plus explicit rubrics beat prompt vibes for consistency.
- Concurrency needs backpressure: fetching faster than extraction just fills memory.
- Budgets and rate limits are architecture, not an afterthought.
- Designing for the demo — live browser, streaming results, visible stages — changes what you build for the better.
- Privacy details (contact stripping, not persisting the PDF) are cheap to add and easy to explain.

### What's next

- Accounts and saved profiles, so a student does not re-enter the wizard every visit.
- Application tracking and deadline reminders (email/push), plus a weekly "new money" digest.
- More sources: French-language pages, provincial foundations, Indigenous and equity-specific awards, and graduate funding.
- Better amount normalization and a confidence model trained on verified hunts.
- Human-in-the-loop application assistance — prefill, review, never auto-submit.
- A deployed demo with a queue and a shared result cache that respects freshness.

---

## Limitations

- Eligibility results are **estimates**, not advice. Always confirm on the official page.
- Government aid is intentionally out of scope.
- Sources are mostly English-language Canadian pages.
- A live hunt depends on third-party sites and API quotas; results vary by run.
- This is a hackathon project, not a financial or legal service.

## License

No license file is included — this is a hackathon submission. Ask before reusing it commercially.
