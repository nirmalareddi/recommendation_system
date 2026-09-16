"""
Integration tests for the full API flow: intake -> seed universities ->
generate recommendations (with explanations) -> notification logged.

Uses an isolated in-memory SQLite DB per test run (overrides the app's
DB dependency) so tests don't touch the real admissions_poc.db file.

No ANTHROPIC_API_KEY is set in the test environment, so explanation
generation exercises the deterministic template fallback path — tests
assert an explanation is present and non-empty, not exact wording.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import db_models  # noqa: F401 — registers models on Base


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_universities(client):
    client.post("/universities", json={
        "name": "University of Toronto",
        "country": "Canada",
        "program_name": "Computer Science",
        "required_qualification": "Bachelor's Degree",
        "min_marks_percentage_cutoff": 70,
        "seats_available": 10,
        "annual_tuition_fee_usd": 45000,
        "min_english_test_score": 6.5,
    })
    client.post("/universities", json={
        "name": "Technical University of Munich",
        "country": "Germany",
        "program_name": "Computer Science",
        "required_qualification": "Bachelor's Degree",
        "min_marks_percentage_cutoff": 72,
        "seats_available": 5,
        "annual_tuition_fee_usd": 3000,
        "min_english_test_score": 6.5,
    })
    client.post("/universities", json={
        "name": "Some PhD-only School",
        "country": "Canada",
        "program_name": "Computer Science",
        "required_qualification": "PhD",
        "min_marks_percentage_cutoff": 70,
    })
    client.post("/universities", json={
        "name": "Full Program",
        "country": "Canada",
        "program_name": "Computer Science",
        "required_qualification": "Bachelor's Degree",
        "min_marks_percentage_cutoff": 60,
        "seats_available": 0,  # should be excluded — no seats
    })


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_student_with_marks_percentage(client):
    resp = client.post("/students", json={
        "name": "Asha Rao",
        "contact_email": "asha@example.com",
        "academic_qualification": "Bachelor's Degree",
        "marks_percentage": 82.0,
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Asha Rao"


def test_create_student_with_cgpa_only(client):
    resp = client.post("/students", json={
        "name": "Ravi Kumar",
        "contact_email": "ravi@example.com",
        "academic_qualification": "Bachelor's Degree",
        "cgpa": 8.5,
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    assert resp.status_code == 201
    assert resp.json()["cgpa"] == 8.5


def test_create_student_requires_marks_or_cgpa(client):
    resp = client.post("/students", json={
        "name": "No Score",
        "contact_email": "noscore@example.com",
        "academic_qualification": "Bachelor's Degree",
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    assert resp.status_code == 422


def test_recommendations_require_seeded_universities(client):
    student_resp = client.post("/students", json={
        "name": "No Universities Yet",
        "contact_email": "nouni@example.com",
        "academic_qualification": "Bachelor's Degree",
        "marks_percentage": 75,
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    student_id = student_resp.json()["id"]

    resp = client.post(f"/students/{student_id}/recommendations")
    assert resp.status_code == 400


def test_full_flow_with_explanations_and_new_eligibility_filters(client):
    _seed_universities(client)

    student_resp = client.post("/students", json={
        "name": "Priya Sharma",
        "contact_email": "priya@example.com",
        "academic_qualification": "Bachelor's Degree",
        "field_of_study": "Computer Engineering",
        "marks_percentage": 80.0,
        "budget_max_usd": 40000,  # excludes University of Toronto (45k tuition)
        "english_test_score": 7.0,
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    student_id = student_resp.json()["id"]

    rec_resp = client.post(f"/students/{student_id}/recommendations")
    assert rec_resp.status_code == 201
    body = rec_resp.json()

    assert body["status"] == "sent"
    assert body["sent_at"] is not None

    # University of Toronto excluded due to budget; PhD-only and zero-seat
    # programs excluded on their own filters. Only Munich remains eligible.
    names = [r["university_name"] for r in body["recommendations"]]
    assert "University of Toronto" not in names
    assert "Technical University of Munich" in names

    # Every recommendation should carry a non-empty explanation (template
    # fallback, since no ANTHROPIC_API_KEY is set in tests).
    for item in body["recommendations"]:
        assert item["explanation"]
        assert isinstance(item["explanation"], str)

    get_resp = client.get(f"/students/{student_id}/recommendations")
    assert get_resp.status_code == 200
    assert get_resp.json()[0]["recommendations"][0]["explanation"]


def test_budget_filter_excludes_expensive_program(client):
    _seed_universities(client)
    student_resp = client.post("/students", json={
        "name": "Tight Budget",
        "contact_email": "tight@example.com",
        "academic_qualification": "Bachelor's Degree",
        "marks_percentage": 90.0,
        "budget_max_usd": 5000,  # only Munich (3000) fits
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    student_id = student_resp.json()["id"]
    rec_resp = client.post(f"/students/{student_id}/recommendations")
    body = rec_resp.json()
    names = [r["university_name"] for r in body["recommendations"]]
    assert names == ["Technical University of Munich"]


def test_no_eligible_universities_returns_422(client):
    _seed_universities(client)
    student_resp = client.post("/students", json={
        "name": "Impossible Budget",
        "contact_email": "impossible@example.com",
        "academic_qualification": "Bachelor's Degree",
        "marks_percentage": 90.0,
        "budget_max_usd": 100,  # nothing fits
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    student_id = student_resp.json()["id"]
    resp = client.post(f"/students/{student_id}/recommendations")
    assert resp.status_code == 422


def test_recommendations_404_for_unknown_student(client):
    resp = client.post("/students/nonexistent-id/recommendations")
    assert resp.status_code == 404


def test_invalid_marks_percentage_rejected(client):
    resp = client.post("/students", json={
        "name": "Bad Input",
        "contact_email": "bad@example.com",
        "academic_qualification": "Bachelor's Degree",
        "marks_percentage": 150,  # out of range
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    assert resp.status_code == 422


def test_invalid_cgpa_rejected(client):
    resp = client.post("/students", json={
        "name": "Bad CGPA",
        "contact_email": "badcgpa@example.com",
        "academic_qualification": "Bachelor's Degree",
        "cgpa": 15,  # out of range (0-10)
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
    })
    assert resp.status_code == 422
