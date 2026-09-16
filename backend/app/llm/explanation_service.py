"""
Generates a personalized, natural-language explanation of why each
recommended university was chosen, for use in the recommendation email.

POC design choice — same pattern as the email/SendGrid fallback: if
ANTHROPIC_API_KEY is not configured, this falls back to a deterministic,
template-built explanation from the score breakdown. That means the POC
is fully runnable end-to-end with zero LLM cost or setup; set the key to
upgrade to natural, personalized writing with no other code changes.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.config.settings import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

logger = logging.getLogger("llm_explanations")


@dataclass
class ExplanationResult:
    university_id: str
    explanation: str
    source: str  # "llm" | "template_fallback"


def _template_fallback_explanation(student_name: str, item: dict) -> str:
    """
    Deterministic, no-LLM explanation built directly from the score
    breakdown. Not as natural as the LLM version, but fully explainable
    and requires no external dependency.
    """
    b = item["breakdown"]
    parts = [f"{item['university_name']} was recommended for {student_name} because"]
    reasons = []

    if b.get("course_match"):
        reasons.append("the program matches your preferred course")
    if b.get("country_match"):
        reasons.append("it's in your preferred country")
    academic_pct = b.get("academic_percentage_equivalent")
    if academic_pct is not None:
        reasons.append(f"your academic score ({academic_pct}%) meets the program's eligibility criteria")
    if b.get("budget_headroom_usd") is not None:
        if b["budget_headroom_usd"] >= 0:
            reasons.append(f"the tuition fits within your budget (${b['tuition_fee_usd']:,.0f}/year)")
    if b.get("seats_available") is not None:
        reasons.append(f"seats are currently available ({int(b['seats_available'])} open)")

    if not reasons:
        reasons.append("it met the program's eligibility requirements")

    parts.append(", ".join(reasons) + f". Overall match score: {item['score']}.")
    return " ".join(parts)


def _build_llm_prompt(student: dict, items: list[dict]) -> str:
    student_summary = (
        f"Name: {student['name']}\n"
        f"Qualification: {student['academic_qualification']}"
        + (f" in {student['field_of_study']}" if student.get("field_of_study") else "")
        + "\n"
        + (f"Marks: {student['marks_percentage']}%\n" if student.get("marks_percentage") is not None else "")
        + (f"CGPA: {student['cgpa']}\n" if student.get("cgpa") is not None else "")
        + f"Preferred course: {student['preferred_course']}\n"
        f"Preferred country: {student['preferred_country']}\n"
        + (f"Budget: up to ${student['budget_max_usd']:,.0f}/year\n" if student.get("budget_max_usd") is not None else "")
    )

    universities_summary = ""
    for item in items:
        b = item["breakdown"]
        universities_summary += (
            f"\n- university_id: {item['university_id']}\n"
            f"  name: {item['university_name']}\n"
            f"  match_score: {item['score']}\n"
            f"  score_breakdown: {json.dumps(b)}\n"
        )

    return f"""You are writing brief, warm, factual explanations for a student about to
receive their top {len(items)} university recommendations by email.

Student profile:
{student_summary}

Recommended universities with their score breakdowns:
{universities_summary}

For each university, write a 1-2 sentence explanation of why it was
recommended, grounded ONLY in the score breakdown data provided (don't
invent facts about the university not present in the data). Be specific
about what matched (course, country, academic fit, budget fit, seat
availability) using the actual numbers where relevant. Keep a warm,
encouraging, professional tone appropriate for a student email.

Respond ONLY with a JSON array, no preamble, no markdown code fences, in
this exact shape:
[{{"university_id": "...", "explanation": "..."}}, ...]
"""


def generate_explanations(student: dict, items: list[dict]) -> list[ExplanationResult]:
    """
    student: dict with keys matching StudentOut fields (name, academic_qualification,
             field_of_study, marks_percentage, cgpa, preferred_course,
             preferred_country, budget_max_usd)
    items: list of dicts with keys: university_id, university_name, score, breakdown
    """
    if not ANTHROPIC_API_KEY:
        logger.info("ANTHROPIC_API_KEY not set — using template fallback explanations.")
        return [
            ExplanationResult(
                university_id=item["university_id"],
                explanation=_template_fallback_explanation(student["name"], item),
                source="template_fallback",
            )
            for item in items
        ]

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = _build_llm_prompt(student, items)

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        raw_text = "".join(text_blocks).strip()
        # Defensive cleanup in case the model wraps the JSON in code fences anyway.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:].strip()

        parsed = json.loads(raw_text)
        explanations_by_id = {p["university_id"]: p["explanation"] for p in parsed}

        results = []
        for item in items:
            explanation = explanations_by_id.get(item["university_id"])
            if explanation:
                results.append(ExplanationResult(item["university_id"], explanation, "llm"))
            else:
                # LLM didn't return this one for some reason — fall back for just this item.
                results.append(
                    ExplanationResult(
                        item["university_id"],
                        _template_fallback_explanation(student["name"], item),
                        "template_fallback",
                    )
                )
        return results

    except Exception:  # noqa: BLE001 — POC-level: never let explanation generation break the recommendation flow
        logger.exception("LLM explanation generation failed — falling back to templates for all items.")
        return [
            ExplanationResult(
                university_id=item["university_id"],
                explanation=_template_fallback_explanation(student["name"], item),
                source="template_fallback",
            )
            for item in items
        ]
