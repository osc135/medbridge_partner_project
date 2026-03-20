"""Tests for the safety classifier."""

from ai_health_coach.core.safety.classifier import (
    CLINICAL_REDIRECT,
    CRISIS_MESSAGE,
    FALLBACK_MESSAGE,
    check_and_filter_message,
    classify_message,
)


def test_safe_message():
    assert classify_message("Great job on your exercises today!") == "safe"


def test_clinical_keyword_detection():
    assert classify_message("I've been having pain in my knee") == "clinical"
    assert classify_message("Should I change my medication?") == "clinical"
    assert classify_message("The swelling is getting worse") == "clinical"


def test_crisis_keyword_detection():
    # Crisis takes priority over clinical
    assert classify_message("I want to kill myself") == "mental_health_crisis"
    assert classify_message("I feel hopeless and nothing matters") == "mental_health_crisis"
    assert classify_message("I can't take it anymore") == "mental_health_crisis"


def test_crisis_overrides_clinical():
    # Message with both clinical and crisis keywords → crisis wins
    assert classify_message("The pain makes me want to end it all") == "mental_health_crisis"


def test_check_safe_message_passes_through():
    result = check_and_filter_message("Keep up the great work!")
    assert result["flagged"] is False
    assert result["final_message"] == "Keep up the great work!"


def test_check_clinical_with_retry_success():
    call_count = 0

    def regenerate():
        nonlocal call_count
        call_count += 1
        return "Keep focusing on your exercises!"

    result = check_and_filter_message(
        "You should take ibuprofen for the pain",
        regenerate_fn=regenerate,
    )
    assert result["flagged"] is True
    assert result["flag_reason"] == "clinical"
    assert result["final_message"] == "Keep focusing on your exercises!"
    assert call_count == 1


def test_check_clinical_retry_also_fails():
    def regenerate():
        return "Try this treatment for your symptoms"

    result = check_and_filter_message(
        "Take this medication",
        regenerate_fn=regenerate,
    )
    assert result["flagged"] is True
    assert result["final_message"] == FALLBACK_MESSAGE


def test_check_crisis_no_retry():
    result = check_and_filter_message("I want to kill myself")
    assert result["flagged"] is True
    assert result["flag_reason"] == "mental_health_crisis"
    assert result["final_message"] == CRISIS_MESSAGE


def test_check_clinical_no_regenerate_fn():
    result = check_and_filter_message("You need a new prescription")
    assert result["flagged"] is True
    assert result["final_message"] == FALLBACK_MESSAGE
