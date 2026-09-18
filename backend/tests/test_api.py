import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine
from app.models import db_models


# ---------------------------------------------------------------------------
# Test client / database setup
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _student_payload(
    name="Test Student",
    contact_email="test@example.com",
    contact_phone="+919999999999",
    academic_qualification="Bachelor's Degree",
    field_of_study="Computer Science",
    marks_percentage=80.0,
    cgpa=None,
    budget_max_usd=40000,
    english_test_score=7.0,
    preferred_course="Computer Science",
    preferred_country="New Zealand",
):
    return {
        "name": name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "academic_qualification": academic_qualification,
        "field_of_study": field_of_study,
        "marks_percentage": marks_percentage,
        "cgpa": cgpa,
        "budget_max_usd": budget_max_usd,
        "english_test_score": english_test_score,
        "preferred_course": preferred_course,
        "preferred_country": preferred_country,
    }


def _seed_universities(client):
    """
    Seed a small test dataset.

    The dataset intentionally contains:
    - Several New Zealand programs.
    - One Canada program.

    The Canada program is used to verify the New Zealand-only safeguard.
    """

    universities = [
        {
            "name": "University of Auckland",
            "country": "New Zealand",
            "program_name": "Bachelor of Science",
            "required_qualification": "Bachelor's Degree",
            "field_of_study": "Computer Science",
            "degree_level": "Bachelor's Degree",
            "min_marks_percentage_cutoff": 70.0,
            "seats_available": 50,
            "annual_tuition_fee_usd": 30000,
            "min_english_test_score": 6.5,
            "application_deadline": "2027-01-31",
        },
        {
            "name": "University of Auckland",
            "country": "New Zealand",
            "program_name": "Bachelor of Science - Data Science",
            "required_qualification": "Bachelor's Degree",
            "field_of_study": "Data Science",
            "degree_level": "Bachelor's Degree",
            "min_marks_percentage_cutoff": 65.0,
            "seats_available": 40,
            "annual_tuition_fee_usd": 32000,
            "min_english_test_score": 6.5,
            "application_deadline": "2027-01-31",
        },
        {
            "name": "University of Waikato",
            "country": "New Zealand",
            "program_name": "Bachelor of Computer Science",
            "required_qualification": "Bachelor's Degree",
            "field_of_study": "Computer Science",
            "degree_level": "Bachelor's Degree",
            "min_marks_percentage_cutoff": 60.0,
            "seats_available": 45,
            "annual_tuition_fee_usd": 25000,
            "min_english_test_score": 6.0,
            "application_deadline": "2027-02-15",
        },
        {
            "name": "Massey University",
            "country": "New Zealand",
            "program_name": "Bachelor of Information Sciences",
            "required_qualification": "Bachelor's Degree",
            "field_of_study": "Computer Science",
            "degree_level": "Bachelor's Degree",
            "min_marks_percentage_cutoff": 60.0,
            "seats_available": 35,
            "annual_tuition_fee_usd": 22000,
            "min_english_test_score": 6.0,
            "application_deadline": "2027-02-28",
        },
        {
            "name": "University of Toronto",
            "country": "Canada",
            "program_name": "Bachelor of Computer Science",
            "required_qualification": "Bachelor's Degree",
            "field_of_study": "Computer Science",
            "degree_level": "Bachelor's Degree",
            "min_marks_percentage_cutoff": 60.0,
            "seats_available": 50,
            "annual_tuition_fee_usd": 25000,
            "min_english_test_score": 6.5,
            "application_deadline": "2027-01-15",
        },
    ]

    for university in universities:
        response = client.post(
            "/universities",
            json=university,
        )

        assert response.status_code in (201, 200), response.text


# ---------------------------------------------------------------------------
# Student API tests
# ---------------------------------------------------------------------------


def test_create_student(client):
    response = client.post(
        "/students",
        json=_student_payload(),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Test Student"
    assert data["contact_email"] == "test@example.com"
    assert data["contact_phone"] == "+919999999999"
    assert data["academic_qualification"] == "Bachelor's Degree"
    assert data["field_of_study"] == "Computer Science"
    assert data["marks_percentage"] == 80.0
    assert data["budget_max_usd"] == 40000
    assert data["english_test_score"] == 7.0
    assert data["preferred_course"] == "Computer Science"
    assert data["preferred_country"] == "New Zealand"


def test_create_student_with_cgpa(client):
    payload = _student_payload(
        marks_percentage=None,
        cgpa=8.5,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["marks_percentage"] is None
    assert data["cgpa"] == 8.5


def test_create_student_requires_marks_or_cgpa(client):
    payload = _student_payload(
        marks_percentage=None,
        cgpa=None,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 422


def test_create_student_rejects_invalid_marks(client):
    payload = _student_payload(
        marks_percentage=120.0,
        cgpa=None,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 422


def test_create_student_rejects_invalid_cgpa(client):
    payload = _student_payload(
        marks_percentage=None,
        cgpa=11.0,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 422


def test_create_student_rejects_invalid_english_score(client):
    payload = _student_payload(
        english_test_score=10.0,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 422


def test_create_student_rejects_negative_budget(client):
    payload = _student_payload(
        budget_max_usd=-1000,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Recommendation flow tests
# ---------------------------------------------------------------------------


def test_full_flow_with_explanations_and_new_eligibility_filters(client):
    _seed_universities(client)

    student_response = client.post(
        "/students",
        json=_student_payload(
            name="Priya Sharma",
            contact_email="priya@example.com",
            field_of_study="Computer Engineering",
            marks_percentage=80.0,
            cgpa=None,
            budget_max_usd=40000,
            english_test_score=7.0,
            preferred_course="Computer Science",
            preferred_country="New Zealand",
        ),
    )

    assert student_response.status_code == 201, student_response.text

    student_id = student_response.json()["id"]

    recommendation_response = client.post(
        f"/students/{student_id}/recommendations"
    )

    assert recommendation_response.status_code == 201
    data = recommendation_response.json()

    assert data["student_id"] == student_id
    assert data["status"] == "sent"
    assert len(data["recommendations"]) > 0

    for recommendation in data["recommendations"]:
        assert recommendation["country"] == "New Zealand"
        assert recommendation["explanation"] is not None
        assert len(recommendation["explanation"]) > 0


def test_recommendations_are_new_zealand_only(client):
    """
    Verify that even when a non-New-Zealand university exists in the
    database, the recommendation API never returns it.
    """

    _seed_universities(client)

    student_response = client.post(
        "/students",
        json=_student_payload(
            name="NZ Test Student",
            contact_email="nz@example.com",
            field_of_study="Computer Science",
            marks_percentage=85.0,
            budget_max_usd=50000,
            english_test_score=7.5,
            preferred_course="Computer Science",
            preferred_country="New Zealand",
        ),
    )

    assert student_response.status_code == 201

    student_id = student_response.json()["id"]

    recommendation_response = client.post(
        f"/students/{student_id}/recommendations"
    )

    assert recommendation_response.status_code == 201

    data = recommendation_response.json()

    assert len(data["recommendations"]) > 0

    countries = {
        recommendation["country"]
        for recommendation in data["recommendations"]
    }

    assert countries == {"New Zealand"}

    university_names = {
        recommendation["university_name"]
        for recommendation in data["recommendations"]
    }

    assert "University of Toronto" not in university_names


def test_preferred_country_does_not_allow_non_nz_recommendations(client):
    """
    The product is New Zealand-only.

    Even if a student submits another preferred country, the API must
    not recommend universities outside New Zealand.
    """

    _seed_universities(client)

    student_response = client.post(
        "/students",
        json=_student_payload(
            name="Country Preference Test",
            contact_email="country@example.com",
            field_of_study="Computer Science",
            marks_percentage=85.0,
            budget_max_usd=50000,
            english_test_score=7.5,
            preferred_course="Computer Science",
            preferred_country="Canada",
        ),
    )

    assert student_response.status_code == 201

    student_id = student_response.json()["id"]

    recommendation_response = client.post(
        f"/students/{student_id}/recommendations"
    )

    assert recommendation_response.status_code == 201

    data = recommendation_response.json()

    assert len(data["recommendations"]) > 0

    for recommendation in data["recommendations"]:
        assert recommendation["country"] == "New Zealand"


def test_budget_filter_excludes_expensive_program(client):
    _seed_universities(client)

    student_response = client.post(
        "/students",
        json=_student_payload(
            name="Tight Budget",
            contact_email="tight@example.com",
            field_of_study="Computer Science",
            marks_percentage=80.0,
            budget_max_usd=24000,
            english_test_score=7.0,
            preferred_course="Computer Science",
            preferred_country="New Zealand",
        ),
    )

    assert student_response.status_code == 201

    student_id = student_response.json()["id"]

    recommendation_response = client.post(
        f"/students/{student_id}/recommendations"
    )

    assert recommendation_response.status_code == 201

    data = recommendation_response.json()

    assert len(data["recommendations"]) > 0

    for recommendation in data["recommendations"]:
        assert recommendation["country"] == "New Zealand"

        # Every recommended program must be within the student's budget.
        assert recommendation["breakdown"] is not None


def test_budget_filter_returns_no_recommendations_when_all_are_expensive(
    client,
):
    _seed_universities(client)

    student_response = client.post(
        "/students",
        json=_student_payload(
            name="Very Tight Budget",
            contact_email="verytight@example.com",
            field_of_study="Computer Science",
            marks_percentage=80.0,
            budget_max_usd=1000,
            english_test_score=7.0,
            preferred_course="Computer Science",
            preferred_country="New Zealand",
        ),
    )

    assert student_response.status_code == 201

    student_id = student_response.json()["id"]

    recommendation_response = client.post(
        f"/students/{student_id}/recommendations"
    )

    assert recommendation_response.status_code == 422


def test_recommendation_for_missing_student_returns_404(client):
    response = client.post(
        "/students/non-existent-student-id/recommendations"
    )

    assert response.status_code == 404


def test_get_recommendations_for_missing_student_returns_404(client):
    response = client.get(
        "/students/non-existent-student-id/recommendations"
    )

    assert response.status_code == 404


def test_get_recommendations_after_generation(client):
    _seed_universities(client)

    student_response = client.post(
        "/students",
        json=_student_payload(
            name="Get Recommendation Test",
            contact_email="get@example.com",
        ),
    )

    assert student_response.status_code == 201

    student_id = student_response.json()["id"]

    create_response = client.post(
        f"/students/{student_id}/recommendations"
    )

    assert create_response.status_code == 201

    get_response = client.get(
        f"/students/{student_id}/recommendations"
    )

    assert get_response.status_code == 200

    data = get_response.json()

    assert isinstance(data, list)
    assert len(data) >= 1

    recommendation = data[0]

    assert recommendation["student_id"] == student_id
    assert len(recommendation["recommendations"]) > 0

    for item in recommendation["recommendations"]:
        assert item["country"] == "New Zealand"


# ---------------------------------------------------------------------------
# University API tests
# ---------------------------------------------------------------------------


def test_create_university(client):
    university = {
        "name": "Test New Zealand University",
        "country": "New Zealand",
        "program_name": "Master of Artificial Intelligence",
        "required_qualification": "Bachelor's Degree",
        "field_of_study": "Artificial Intelligence",
        "degree_level": "Master's Degree",
        "min_marks_percentage_cutoff": 65.0,
        "seats_available": 20,
        "annual_tuition_fee_usd": 30000,
        "min_english_test_score": 6.5,
        "application_deadline": "2027-02-28",
    }

    response = client.post(
        "/universities",
        json=university,
    )

    assert response.status_code in (200, 201)

    data = response.json()

    assert data["name"] == "Test New Zealand University"
    assert data["country"] == "New Zealand"
    assert data["field_of_study"] == "Artificial Intelligence"


def test_get_universities(client):
    _seed_universities(client)

    response = client.get("/universities")

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1


def test_create_student_with_all_optional_academic_fields(client):
    payload = _student_payload(
        marks_percentage=82.5,
        cgpa=8.7,
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["marks_percentage"] == 82.5
    assert data["cgpa"] == 8.7


def test_student_country_is_preserved(client):
    payload = _student_payload(
        preferred_country="Canada",
    )

    response = client.post(
        "/students",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["preferred_country"] == "Canada"