"""Tests for the full safety pipeline — classify, retry, fallback."""

from ai_health_coach.core.safety.classifier import (
    CLINICAL_REDIRECT,
    CRISIS_MESSAGE,
    FALLBACK_MESSAGE,
    check_and_filter_message,
    classify_message,
)


# ─── Classification ───────────────────────────────────────


def test_classify_safe_message():
    assert classify_message("Great job on your exercises!") == "safe"


def test_classify_clinical_pain():
    assert classify_message("You should take medication for the pain") == "clinical"


def test_classify_clinical_symptom():
    assert classify_message("Your symptoms suggest inflammation") == "clinical"


def test_classify_crisis_suicide():
    assert classify_message("I want to kill myself") == "mental_health_crisis"


def test_classify_crisis_hurt():
    assert classify_message("I want to hurt myself") == "mental_health_crisis"


def test_classify_crisis_hopeless():
    assert classify_message("Nothing matters anymore, what's the point") == "mental_health_crisis"


def test_crisis_takes_priority_over_clinical():
    """Crisis keywords should win even if clinical keywords are also present."""
    assert classify_message("The pain makes me want to end it all") == "mental_health_crisis"


# ─── check_and_filter_message pipeline ─────────────────────


def test_safe_message_passes_through():
    result = check_and_filter_message("Keep up the great work!")
    assert result["flagged"] is False
    assert result["final_message"] == "Keep up the great work!"
    assert result["retry_count"] == 0


def test_crisis_returns_crisis_message():
    result = check_and_filter_message("I want to end my life")
    assert result["flagged"] is True
    assert result["flag_reason"] == "mental_health_crisis"
    assert result["final_message"] == CRISIS_MESSAGE
    assert result["retry_count"] == 0


def test_clinical_with_no_regenerate_returns_fallback():
    """Clinical content with no regenerate function → fallback."""
    result = check_and_filter_message("Take your medication twice daily")
    assert result["flagged"] is True
    assert result["flag_reason"] == "clinical"
    assert result["final_message"] == FALLBACK_MESSAGE


def test_clinical_with_safe_retry_passes():
    """Clinical content → retry with safe prompt → if retry is safe, use it."""
    def regenerate():
        return "Keep focusing on your exercises!"

    result = check_and_filter_message(
        "You should increase your medication dosage",
        regenerate_fn=regenerate,
    )
    assert result["flagged"] is True
    assert result["retry_count"] == 1
    assert result["final_message"] == "Keep focusing on your exercises!"


def test_clinical_with_still_clinical_retry_returns_fallback():
    """Clinical content → retry also clinical → fallback."""
    def regenerate():
        return "Your pain symptoms need treatment"

    result = check_and_filter_message(
        "Adjust your medication",
        regenerate_fn=regenerate,
    )
    assert result["flagged"] is True
    assert result["retry_count"] == 1
    assert result["final_message"] == FALLBACK_MESSAGE
