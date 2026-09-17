"""
Tunable scoring configuration.

Keep weights here (not hardcoded in scoring.py) so they can be adjusted
during POC calibration without touching logic code.
"""

SCORING_WEIGHTS = {
    "marks_ratio": 0.40,          # academic performance
    "course_match": 0.25,         # preferred course vs program
    "field_of_study_match": 0.20, # academic background vs program field
    "country_match": 0.15,        # preferred country vs university country
}

# Marks/CGPA ratio is capped at this value so a student far above cutoff
# doesn't blow out the score (e.g., cap at 1.2 = 120% of cutoff counts as max credit)
MARKS_RATIO_CAP = 1.2