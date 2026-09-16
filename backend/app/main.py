"""
FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload

This wires together:
- Stage A: student intake  (app/api/students.py)
- Stage B: university reference data (app/api/universities.py)
- Stages C+D+E: scoring, ranking, persistence, notification (app/api/recommendations.py)

No approval-gate endpoints — recommendations are generated and sent in one call.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api import students, universities, recommendations
from app.config.settings import ALLOWED_ORIGINS
from app.seed import seed_universities

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Idempotent — seed_universities() checks for existing rows and skips
    # if already seeded, so this is safe to run on every startup/restart.
    # This means the deployed app self-seeds on first boot with no manual
    # shell step required (useful since free-tier hosting doesn't always
    # include shell/SSH access).
    seed_universities()
    yield


app = FastAPI(
    title="Admissions Recommendation POC",
    description="POC API for student intake, merit scoring, and automated recommendation delivery.",
    version="0.1.0",
    lifespan=lifespan,
)

# Needed once the frontend is hosted on a different domain than the API
# (e.g. Render static site calling a Render web service) — browsers block
# cross-origin requests by default without this. ALLOWED_ORIGINS defaults
# to "*" for POC convenience; tighten it to your actual frontend URL(s)
# before this handles real student data.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router)
app.include_router(universities.router)
app.include_router(recommendations.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
