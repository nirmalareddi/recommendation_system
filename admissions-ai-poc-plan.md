# Student Admissions Recommendation System — POC Implementation Plan
*(v2 — manager/counselor approval step removed)*

## 1. POC Objective

Prove the core value proposition end-to-end with a small, controlled dataset:

> A student's profile can be automatically scored against university/college eligibility criteria, the top 3 matches can be ranked, and the student receives the recommendation automatically — with no document upload/OCR step and no manual approval gate at this stage.

**POC success criteria:**
- End-to-end flow runs on ≥30–50 sample student profiles against ≥15–20 seeded university/program records
- Recommendation engine returns explainable top-3 (score breakdown stored, even without a human reviewing it)
- Notification fires automatically the moment recommendations are generated
- Each stage is independently testable before wiring to the next (per your preference for stage-by-stage validation)

---

## 2. Architecture (POC-level)

```
[Web Form / Portal]
        │  (student submits profile)
        ▼
[Intake API] ── validate & normalize ──► [Students DB]
        │
        ▼
[Eligibility & Merit Scoring Engine]
        │  reads
        ▼
[University/College Criteria DB]
        │
        ▼
[Ranking Engine] ──► Top 3 Recommendations ──► [Recommendations DB]
        │
        ▼
[Notification Service] ──► Email (POC) / SMS-WhatsApp (post-POC) / Portal update
```

No approval stage in this version — recommendations go straight from generation to notification. Everything above can live in a single monolith for the POC.

---

## 3. Recommended Tech Stack (POC-appropriate, low setup overhead)

| Layer | Recommendation | Why |
|---|---|---|
| Backend | Python (FastAPI) | Fast to prototype, easy scoring/ranking logic in plain Python |
| Database | PostgreSQL (or SQLite for pure POC) | Relational fit for structured student/college criteria data |
| Frontend (student form) | Simple React form or even a Google Form → webhook for v0 | Don't over-invest in UI polish at POC stage |
| Notifications | SendGrid/Amazon SES for email | Free tier / low setup cost, reliable for POC |
| Orchestration | Simple synchronous pipeline | No async/queue needed until scale demands it |
| Hosting | Single VM / Docker Compose stack | No need for Kubernetes at POC scale |

*(No counselor dashboard needed — this removes the biggest UI build item from the original plan.)*

---

## 4. Data Model (minimum viable schema)

**students**
- id, name, contact_email, contact_phone
- academic_qualification (e.g., 12th/UG degree)
- marks_percentage / cgpa
- preferred_course
- preferred_country
- submitted_at

**universities**
- id, name, country
- program_name
- min_eligibility (qualification required)
- min_marks_cgpa_cutoff
- seats_available (optional, for POC can be static)
- admission_probability_weight (tunable factor)

**recommendations**
- id, student_id
- ranked_university_ids (top 3, ordered)
- score_breakdown (JSON — per-university score components, kept for explainability/audit even without a human reviewer)
- status (generated / sent)
- generated_at, sent_at

**notifications_log**
- id, student_id, channel, status, sent_at

---

## 5. Step-by-Step Build Sequence (validate each stage before moving on)

### Stage A — Data Capture
1. Build the intake form (fields: personal details, academic qualification, marks/CGPA, preferred course, preferred country).
2. Build a simple validation layer (required fields, marks in valid range, known qualification types).
3. **Validate:** submit 5–10 dummy profiles, confirm they land correctly in the `students` table.

### Stage B — Seed Reference Data
1. Manually seed 15–20 sample university/program records with eligibility and cutoff criteria.
2. **Validate:** spot-check the seeded data is queryable and matches expected format.

### Stage C — Merit/Eligibility Scoring Engine
1. Define scoring logic in plain, explainable terms:
   - Eligibility gate: qualification must match required qualification (hard filter, pass/fail)
   - Merit score = weighted function of (marks/cgpa vs cutoff), (course preference match), (country preference match)
   - Example: `score = 0.5*(student_marks/cutoff_marks) + 0.3*(course_match ? 1 : 0) + 0.2*(country_match ? 1 : 0)`
2. Store weights as config, not hardcoded — you'll want to tune this after seeing real POC results.
3. **Validate:** run scoring on your 5–10 dummy profiles against the 15–20 seeded universities; manually sanity-check a few results against what you'd expect.

### Stage D — Ranking & Top-3 Generation
1. Sort eligible universities by score, take top 3, store with score breakdown for explainability.
2. **Validate:** confirm top-3 output changes sensibly when you tweak a student's marks or preferences.

### Stage E — Student Notification (fires immediately after ranking)
1. As soon as recommendations are generated, trigger an email (POC scope) with the finalized top-3.
2. **Validate:** confirm email is sent and content is accurate for 5 test runs; log delivery status.

### Stage F — End-to-End Dry Run
1. Run 20–30 profiles through the full pipeline with zero manual intervention.
2. Track: time per stage, error rate, and — since there's no human checkpoint — spot-check a sample of the auto-generated recommendations yourself against what you'd expect a counselor to pick. This is your substitute quality signal until/unless approval comes back.

---

## 6. Suggested Folder Structure

```
admissions-ai-poc/
├── backend/
│   ├── app/
│   │   ├── api/            # intake, recommendations endpoints
│   │   ├── models/          # DB models (students, universities, recommendations)
│   │   ├── scoring/         # eligibility + merit scoring logic (isolated, unit-testable)
│   │   ├── notifications/   # email integration
│   │   └── config/          # tunable weights, cutoffs
│   ├── tests/
│   │   ├── test_scoring.py
│   │   ├── test_intake.py
│   │   └── test_notifications.py
│   └── requirements.txt
├── frontend/
│   └── student-form/
├── data/
│   └── seed_universities.csv
├── docs/
│   ├── scoring_logic.md
│   └── poc_validation_log.md
└── docker-compose.yml
```

`scoring/` remains the most important isolated, unit-tested module — even more so now that there's no human in the loop to catch a bad recommendation before it reaches a student.

---

## 7. Effort Estimation (POC only, single developer, focused scope)

| Stage | Effort |
|---|---|
| A — Intake form + validation | 2–3 days |
| B — Seed reference data + schema | 1 day |
| C — Scoring engine | 3–4 days (includes tuning) |
| D — Ranking logic | 1 day |
| E — Notification integration | 1–2 days |
| F — End-to-end testing & fixes | 2–3 days |
| **Total** | **~1.5–2.5 weeks** |

Removing the counselor dashboard cuts roughly a week off the original estimate.

---

## 8. What to Explicitly Defer Past POC

- Document upload/OCR
- Manager/counselor approval workflow (deferred, not discarded — can be reintroduced as a `pending_approval` status + review UI later)
- SMS/WhatsApp notifications (email-only proves the workflow)
- Real-time university seat availability / live API integrations
- Automated re-evaluation/feedback loop
- Multi-tenant/role-based access control
- Scaling infrastructure (queueing, load balancing)

---

## 9. Validation Checklist Before Calling the POC "Done"

- [ ] 30–50 student profiles processed end-to-end, fully automated
- [ ] Scoring logic manually spot-checked against expected outcomes (your substitute for counselor review)
- [ ] Top-3 explainability confirmed (score breakdown stored and readable, even if unreviewed)
- [ ] Email notification delivery confirmed and content verified
- [ ] Scoring weights documented and stored as config, not hardcoded
- [ ] Known limitations documented (no OCR, static university data, no approval gate, single notification channel)
