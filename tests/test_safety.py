"""Tests for the safety classifier."""

from ai_health_coach.core.safety.classifier import (
    CLINICAL_REDIRECT,
    CRISIS_MESSAGE,
    FALLBACK_MESSAGE,
    check_and_filter_message,
    classify_message,
)


# ─── classify_message tests ─────────────────────────────────


def test_safe_message():
    assert classify_message("Great job on your exercises today!") == "safe"


def test_safe_greeting():
    assert classify_message("Hi, how are you?") == "safe"


def test_safe_goal_setting():
    assert classify_message("I want to do my exercises every morning") == "safe"


def test_clinical_pain():
    assert classify_message("I've been having pain in my knee") == "clinical"


def test_clinical_medication():
    assert classify_message("Should I change my medication?") == "clinical"


def test_clinical_swelling():
    assert classify_message("The swelling is getting worse") == "clinical"


def test_clinical_diagnosis():
    assert classify_message("What is my diagnosis?") == "clinical"


def test_clinical_treatment():
    assert classify_message("Is this the right treatment for me?") == "clinical"


def test_crisis_direct():
    assert classify_message("I want to kill myself") == "mental_health_crisis"


def test_crisis_hopelessness():
    assert classify_message("I feel hopeless and nothing matters") == "mental_health_crisis"


def test_crisis_cant_take_it():
    assert classify_message("I can't take it anymore") == "mental_health_crisis"


def test_crisis_self_harm():
    assert classify_message("I want to hurt myself") == "mental_health_crisis"


def test_crisis_done_with_everything():
    assert classify_message("I'm done with everything") == "mental_health_crisis"


def test_crisis_overrides_clinical():
    """Message with both clinical and crisis keywords → crisis wins."""
    assert classify_message("The pain makes me want to end it all") == "mental_health_crisis"


def test_crisis_case_insensitive():
    assert classify_message("I Want To KILL MYSELF") == "mental_health_crisis"


# ─── check_and_filter_message tests ─────────────────────────


def test_check_safe_passes_through():
    result = check_and_filter_message("Keep up the great work!")
    assert result["flagged"] is False
    assert result["final_message"] == "Keep up the great work!"
    assert result["retry_count"] == 0


def test_check_clinical_retry_success():
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
    assert result["retry_count"] == 1
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
    """Crisis messages are never retried — always return CRISIS_MESSAGE."""
    result = check_and_filter_message("I want to kill myself")
    assert result["flagged"] is True
    assert result["flag_reason"] == "mental_health_crisis"
    assert result["final_message"] == CRISIS_MESSAGE
    assert result["retry_count"] == 0


def test_check_clinical_no_regenerate_fn():
    """Without a regenerate function, falls back immediately."""
    result = check_and_filter_message("You need a new prescription")
    assert result["flagged"] is True
    assert result["final_message"] == FALLBACK_MESSAGE


def test_check_preserves_original_message():
    result = check_and_filter_message("Take this medication for the pain")
    assert result["original_message"] == "Take this medication for the pain"
