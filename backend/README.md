# Unclaimed backend

FastAPI service that searches for Canadian scholarships, bursaries and awards from
external organizations and the student's own university, fetches source pages,
extracts facts with Gemini, verifies deadlines/eligibility deterministically, and
streams verified matches to the frontend.

Government programs are out of scope. The pipeline drops `canada.ca`, `gc.ca`,
`ontario.ca`, `gov.on.ca`, any `*.gov.*` host, OSAP, Canada Student Grants,
CESG/RESP and CRA tuition tax credits. There is no result cache, no mock program
list and no padding: if fewer than 15 programs survive verification, the hunt
returns fewer and says so.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in both API keys
uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` returns `{"ok": true}`. The service refuses
to start if `TINYFISH_API_KEY` or `GEMINI_API_KEY` is missing and names the missing
variable.

## Streaming pipeline

1. `app/pipeline/planner.py` makes one Gemini call for 16 diverse queries. It
   mixes school/faculty awards, field-of-study external scholarships, year of
   study, province/city foundations, and at least six resume-fact queries. A
   single optional second pass asks for eight more queries at 45 seconds only
   when fewer than eight verified results exist and at least 40 seconds remain.
2. `app/pipeline/discovery.py` runs searches concurrently, applies the hard URL
   filters, deduplicates, and ranks every candidate from title, snippet and
   domain. There is no candidate cap; the pipeline consumes the ranking until it
   stops.
3. `app/pipeline/reader.py` has no sequential fetch stage. Fetch workers take
   `FETCH_BATCH` URLs at a time, stream each successful page immediately, keep
   the complete text plus links, and emit a `Reading host/path` progress row.
   Fetched pages wait in a score-ordered queue; fetching pauses above 24 pending
   extraction pages and resumes as the queue drains.
4. `app/pipeline/extractor.py` makes one Gemini call per page. The input is the
   first 5,000 characters plus merged ±600-character windows around deadline,
   due date, apply-by, applications-open and eligibility matches, capped at
   `MAX_PAGE_CHARS`. The response contains programs, verbatim evidence, the
   strong/good/weak fit judgement, matched facts, gaps and the next step.
5. `app/pipeline/verify.py` checks quotes against the **full** page text, applies
   freshness and hard eligibility drops, drops weak fit under the enforced rubric,
   and falls back to deterministic date/rolling rescue before giving up. It then
   deduplicates incrementally against results already committed.
6. `app/pipeline/matcher.py` only builds the public `Program` from a verified
   extraction. There is no separate batched matching call and no batch-of-four
   extraction.
7. `app/hunt.py` runs fetch and extract worker pools over async queues. A result
   is appended to `state.results` and emitted as `program_found` immediately.
   At `STOP_AT_RESULTS` (40 by default), or at the wall-clock limit, only
   unfinished workers are cancelled; committed results are kept.

A list/index page can queue up to eight same-domain keyword-filtered detail links
at the front of the fetch queue, depth one only. At most one read-only TinyFish
list agent starts around ten seconds in, concurrently with the rest of the
pipeline. Its streaming URL is published as a site row; its detail URLs are used
only if they arrive before 75 seconds.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `TINYFISH_API_KEY` | required | Search, fetch and the one list agent |
| `GEMINI_API_KEY` | required | Planning, resume summary, extraction and fit |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model name |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `STOP_AT_RESULTS` | `40` | Stop as soon as this many results are committed |
| `SEARCH_CONCURRENCY` | `4` | Concurrent search queries |
| `FETCH_CONCURRENCY` | `8` | Concurrent fetch workers |
| `FETCH_BATCH` | `3` | URLs per fetch worker call |
| `EXTRACT_CONCURRENCY` | `8` | Concurrent one-page Gemini extractions |
| `PER_URL_TIMEOUT_MS` | `8000` | TinyFish per-URL fetch timeout |
| `MAX_PAGE_CHARS` | `9000` | Maximum extraction input characters |
| `MAX_GEMINI_CALLS` | `600` | Gemini request budget per hunt |
| `PLAN_QUERIES` | `16` | First-pass query count |
| `WALL_TIMEOUT_SECONDS` | `115` | Hunt-wide wall clock |
| `LIST_AGENT_TIMEOUT_SECONDS` | `60` | Timeout for the one list agent |

TinyFish currently allows two concurrent runs. The hunt starts at most one list
agent so that the live-browser moment cannot block the pipeline. The SDK has no
run-cancel method; the agent wrapper keeps the existing orphan-run protection and
the hunt has a wall-clock limit.

## Resume

A PDF resume is sent as `resume: { name, dataUrl }` in `POST /api/hunt`. Gemini
reads it once, with a 10-second wait inside the hunt. If it cannot be read, the
hunt streams a visible `site_progress` message: `Resume could not be read;
matching without it`. The pipeline then continues on profile facts only.

## API

- `POST /api/hunt` with a `Profile` body returns `{"huntId": "..."}`.
- `GET /api/hunt/{huntId}/events` is the SSE stream.
- `GET /api/hunt/{huntId}/results` returns `Program[]`, or `[]` while running.
- `GET /api/health` returns `{"ok": true}`.

Events: `site_started`, `site_progress`, `program_found`, `site_done`,
`site_failed`, `hunt_error`, `hunt_complete`. A `site_progress` event can carry a
live `count` for the stage row.

Finished hunts are written to `data/hunts/{huntId}.json` so results survive a
restart. No extraction cache is written.

## Demo

```bash
python scripts/run_hunt.py --demo
python scripts/run_hunt.py --demo --resume path/to/resume.pdf
```

The runner prints first-fetch, first-extract, first-verified and 5th/10th/15th
result timing markers, per-stage counts, drop reasons, Gemini calls used, and a
final table with name, provider, amount, deadline or verification type, deadline
quote, URL and matched facts. If either API key is missing it reports exactly
which live stages could not run and does not invent results.

## Notes

- A TinyFish authentication or payment error stops the whole hunt with a
  plain-English `hunt_error`.
- Gemini model errors abort the hunt. Individual page extraction errors are
  logged and skipped.
- Results with stale or unverifiable freshness are dropped rather than padded.
