# Admissions Recommendation POC

Full POC implementation: student intake → merit/eligibility scoring →
top-3 ranking → LLM-generated (or template) explanation per pick →
automated email notification. No document/OCR intake, no approval gate
(deferred per current scope).

## What's new in v3

- **LLM-generated explanations**: each recommended university now comes
  with a personalized explanation of *why* it was picked, written by
  Claude (via the Anthropic API) if `ANTHROPIC_API_KEY` is set, or a
  deterministic template built from the score breakdown if not.
- **New student inputs**: `cgpa` (0–10 scale, as an alternative to
  `marks_percentage`), `budget_max_usd`, `field_of_study`,
  `english_test_score`. At least one of `marks_percentage`/`cgpa` is
  required; CGPA is converted to a percentage-equivalent for scoring
  (see caveat below).
- **New university inputs / eligibility criteria**: `seats_available` is
  now actually enforced (0 seats = excluded), plus
  `annual_tuition_fee_usd` (hard-filtered against student budget) and
  `min_english_test_score` (hard-filtered against student's score, if
  both are provided).

## Project layout

```
admissions-ai-poc/
├── backend/
│   ├── app/
│   │   ├── api/            # students, universities, recommendations endpoints
│   │   ├── models/          # SQLAlchemy models + Pydantic schemas
│   │   ├── scoring/         # eligibility + merit scoring engine (isolated, unit-tested)
│   │   ├── llm/              # explanation generation (Anthropic API, with template fallback)
│   │   ├── notifications/   # email service (console fallback if no SendGrid key)
│   │   ├── config/          # settings (DB URL, scoring weights, LLM + email config)
│   │   ├── database.py
│   │   ├── seed.py          # loads data/seed_universities.csv into the DB
│   │   └── main.py          # FastAPI app entrypoint
│   ├── tests/                # unit tests (scoring, explanations) + integration tests (full API flow)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── student-form/
│       └── index.html        # plain HTML/JS intake form, no build step needed
├── data/
│   └── seed_universities.csv # 15 sample university/program records
└── docker-compose.yml
```

## Running locally (no Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

python -m app.seed                 # seeds universities from data/seed_universities.csv
uvicorn app.main:app --reload      # starts API on http://127.0.0.1:8000
```

Then open `frontend/student-form/index.html` directly in a browser (it
points at `http://127.0.0.1:8000` by default — change `API_BASE_URL` in
the script tag if your backend runs elsewhere).

**No external accounts needed to try this.** With no `SENDGRID_API_KEY`,
email is logged to the server console instead of sent. With no
`ANTHROPIC_API_KEY`, explanations are built from a deterministic
template instead of an LLM call. Both flip on automatically, with no
code changes, once you set the corresponding key.

## Turning on LLM-generated explanations

```bash
export ANTHROPIC_API_KEY=your-key-here
export ANTHROPIC_MODEL=claude-haiku-4-5-20251001   # default; swap to claude-sonnet-5 for richer writing
```
The explanation service (`app/llm/explanation_service.py`) sends the
student profile and each university's score breakdown to the model and
asks for a short JSON-structured explanation per university, grounded
only in the data provided (no invented facts). If the call fails or the
response can't be parsed for a given entry, that entry falls back to the
template — the recommendation flow never breaks because of the LLM step.

**Cost/latency note**: this adds one LLM call per `/recommendations`
request (covering all 3 universities in one call, not 3 separate calls).
For a POC-scale trial this is negligible; for production volume, consider
caching explanations for identical score-breakdown patterns or batching.

## Turning on real email

You have three options. **Resend is recommended for the deployed
(Render) environment** — it sends over HTTPS, so it isn't affected by
Render's free-tier SMTP port block (see the deployment caveat below).
All three plug in via environment variables only, no code changes.

### Option A — Resend (recommended for Render deployment)

1. Sign up at resend.com (free tier: 3,000 emails/month, no credit card)
2. Get an API key from the dashboard
3. Set:
```bash
export RESEND_API_KEY=re_your_key_here
export NOTIFICATION_FROM_EMAIL=admissions@yourdomain.com
```
For testing without your own domain verified, Resend provides a
shared `onboarding@resend.dev` sender — check their docs for current
restrictions on that address.

### Option B — Gmail (or any SMTP provider) — local development only

**Does not work on Render's free tier** — Render blocks outbound SMTP
ports (25, 465, 587) for free web services as of September 2025,
regardless of credentials. Fine for local development; use Resend or
SendGrid for the deployed version.

1. Turn on 2-Step Verification on your Google account: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords — choose "Mail," copy the 16-character password
3. Set these before starting the server:
```bash
export SMTP_USERNAME=youraccount@gmail.com
export SMTP_PASSWORD=the16charapppassword     # not your normal Gmail password
export NOTIFICATION_FROM_EMAIL=youraccount@gmail.com
```
(PowerShell: `$env:SMTP_USERNAME="..."` etc. Command Prompt: `set SMTP_USERNAME=...`)

Using a different SMTP provider? Also set `SMTP_HOST` and `SMTP_PORT`
(defaults are Gmail's: `smtp.gmail.com:587`).

### Option C — SendGrid

```bash
export SENDGRID_API_KEY=your-key-here
export NOTIFICATION_FROM_EMAIL=admissions@yourdomain.com
```
**Note:** SendGrid retired its free plan in 2025 — it's now a 60-day
trial (100 emails/day), then a paid plan. If email was previously
working and has since stopped, an expired trial is a likely cause.

### Priority order

If multiple are configured, the app checks in this order: **Resend →
SendGrid → SMTP → console fallback**. Unset whichever you don't want
used, or just set only the one you want.

## Running with Docker

```bash
docker compose up --build
```

## Running the tests

```bash
cd backend
export PYTHONPATH=.
pytest tests/ -v
```

26 tests: scoring unit tests (eligibility gating incl. seats/budget/English
score, CGPA normalization, weighting, capping, ranking), explanation
service tests (template fallback path — deterministic, no API key
needed), email service tests (console/SMTP/SendGrid priority, SMTP
mechanics verified via mocking), and API integration tests (intake
validation, full generate-and-notify flow, budget/seat filtering, 404/422
handling).

## API quick reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/students` | Submit a student profile (Stage A) |
| GET | `/students/{id}` | Fetch a student |
| POST | `/universities` | Add a university/program record (Stage B) |
| GET | `/universities` | List seeded universities |
| POST | `/students/{id}/recommendations` | Score, rank, explain, persist, and send notification (Stages C+D+E) |
| GET | `/students/{id}/recommendations` | Fetch past recommendations for a student |

## Known caveats worth reviewing before this touches real students

- **CGPA→percentage conversion** (`CGPA_TO_PERCENTAGE_MULTIPLIER = 9.5` in
  `app/config/settings.py`) is a common approximation, not your
  institution's actual grading conversion — replace it with the real
  table if you have one, or keep marks_percentage as the primary input.
- **Seats are checked but not decremented** — there's no reservation
  system yet, so `seats_available` reflects whatever was seeded/updated
  manually, not live consumption from recommendations sent.
- **Budget/English-score filters are hard cutoffs**, not scored factors —
  a student $1 over budget is excluded entirely rather than ranked lower.
  Worth revisiting if you'd rather show "reach" options with a caveat
  than exclude them outright.
- **LLM explanations are grounded in the score breakdown only** — they
  don't (and shouldn't) claim knowledge about the university beyond
  what's in your data. If your seed data is thin, explanations will be too.

## Re-adding the approval step later

The plan currently skips manager/counselor approval. To bring it back:
1. Add a `pending_approval` status to the `Recommendation` model (already has a `status` field).
2. Split `generate_and_send_recommendations` in `app/api/recommendations.py` into two steps:
   generate+explain+persist (stops at `pending_approval`), and a new
   `POST /recommendations/{id}/approve` endpoint that triggers the notification.
3. Add a counselor-facing list/approve UI (not built in this POC).

## Deploying to Render (free, public URL)

[Render](https://render.com) currently offers a genuinely free tier — web
service, static site hosting, and PostgreSQL, no credit card required —
which is why this project includes a `render.yaml` Blueprint that deploys
all three pieces (API, frontend, database) in one step.

**Why Postgres instead of SQLite for the deployed version:** free-tier web
services have an ephemeral filesystem — any SQLite file gets wiped on every
restart or redeploy. The blueprint provisions a free Postgres database and
wires `DATABASE_URL` to it automatically, so your data actually persists.
Locally, SQLite is still the default and still fine to use.

### Steps

1. **Push this project to a GitHub repo** (Render deploys from Git, not by
   file upload):
   ```bash
   cd admissions-ai-poc
   git init
   git add .
   git commit -m "Initial commit"
   # create a new repo on github.com, then:
   git remote add origin https://github.com/yourusername/admissions-ai-poc.git
   git push -u origin main
   ```

2. **Edit one line before deploying**: in
   `frontend/student-form/index.html`, you won't know your backend's real
   URL until after step 3 — so deploy once, copy the backend URL Render
   gives you (something like `https://admissions-api-xxxx.onrender.com`),
   update `const API_BASE_URL = "..."` in that file to point at it, commit,
   and push again. Render auto-redeploys the frontend on every push.

3. **In the Render dashboard**: click **New +** → **Blueprint** → connect
   your GitHub repo → Render reads `render.yaml` and shows you all three
   resources (API, frontend, database) → click **Apply**.

4. **Set secrets manually** (the blueprint deliberately leaves these
   blank — they shouldn't live in a committed file): on the
   `admissions-api` service → **Environment** tab, add whichever of these
   you want:
   - `ANTHROPIC_API_KEY` — for LLM-written explanations
   - `SMTP_USERNAME`, `SMTP_PASSWORD`, `NOTIFICATION_FROM_EMAIL` — for real Gmail-based email
   Leave any of these unset and that feature keeps using its fallback
   (template explanations / console-logged email) exactly like it does locally.

5. **Tighten CORS** once you have your frontend's real URL: change the
   `ALLOWED_ORIGINS` env var on `admissions-api` from `*` to your actual
   frontend URL (e.g. `https://admissions-frontend.onrender.com`) — `*` is
   fine to get things working but shouldn't stay that way once real
   student data is involved.

6. **Visit your frontend's URL** — that's your public link. Share it with
   anyone; they don't need Render, GitHub, or anything installed locally.

### What to expect on the free tier

- **Cold starts**: free web services spin down after 15 minutes of no
  traffic, and the first request after that takes ~30-60 seconds to wake
  back up. Fine for a POC demo, not something to build real-time
  expectations around.
- **SMTP is blocked**: Render's free tier blocks outbound SMTP ports
  (25, 465, 587) as of September 2025 — Gmail/SMTP email will silently
  time out there even with correct credentials. Use `RESEND_API_KEY` or
  `SENDGRID_API_KEY` for the deployed environment (see "Turning on real
  email" above); SMTP is still fine for local development.
- **No manual seeding needed**: the app seeds the university data
  automatically on first startup (`seed_universities()` runs in the
  startup lifecycle and is idempotent, so it's a no-op on every restart
  after the first).
- **Database limits**: Render's free Postgres has a storage cap and a
  time-limited free period per their current terms — check the Render
  dashboard for specifics on your instance, since these terms can change.
