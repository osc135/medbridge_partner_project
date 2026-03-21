"""Tests for deterministic phase transitions."""

from ai_health_coach.core.graph.router import evaluate_transitions
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_DORMANT,
    PHASE_ONBOARDING,
    PHASE_PENDING,
    PHASE_RE_ENGAGING,
    create_initial_state,
)


def _make_state(**overrides):
    state = create_initial_state(
        patient_id="P001",
        patient_name="Test Patient",
        assigned_exercises=[{"name": "Quad Sets", "sets": 3, "reps": 10}],
        program_start_date="2026-03-20",
    )
    state.update(overrides)
    return state


def test_pending_to_onboarding():
    state = _make_state(phase=PHASE_PENDING, has_logged_in=True, has_consented=True)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_ONBOARDING


def test_pending_stays_without_consent():
    state = _make_state(phase=PHASE_PENDING, has_logged_in=True, has_consented=False)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_PENDING


def test_pending_stays_without_login():
    state = _make_state(phase=PHASE_PENDING, has_logged_in=False, has_consented=False)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_PENDING


def test_active_to_re_engaging():
    state = _make_state(phase=PHASE_ACTIVE, has_logged_in=True, has_consented=True, consecutive_unanswered_count=1)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_RE_ENGAGING


def test_active_stays_with_zero_unanswered():
    state = _make_state(phase=PHASE_ACTIVE, has_logged_in=True, has_consented=True, consecutive_unanswered_count=0)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_ACTIVE


def test_active_to_re_engaging_at_higher_count():
    state = _make_state(phase=PHASE_ACTIVE, has_logged_in=True, has_consented=True, consecutive_unanswered_count=2)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_RE_ENGAGING


def test_re_engaging_to_dormant():
    state = _make_state(phase=PHASE_RE_ENGAGING, has_logged_in=True, has_consented=True, consecutive_unanswered_count=3)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_DORMANT


def test_re_engaging_stays_under_threshold():
    state = _make_state(phase=PHASE_RE_ENGAGING, has_logged_in=True, has_consented=True, consecutive_unanswered_count=2)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_RE_ENGAGING


def test_re_engaging_to_dormant_at_higher_count():
    state = _make_state(phase=PHASE_RE_ENGAGING, has_logged_in=True, has_consented=True, consecutive_unanswered_count=5)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_DORMANT


def test_onboarding_does_not_auto_transition():
    """ONBOARDING → ACTIVE is handled by the onboarding subgraph, not evaluate_transitions."""
    state = _make_state(phase=PHASE_ONBOARDING, has_logged_in=True, has_consented=True)
    state["goal"] = {"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"}
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_ONBOARDING


def test_dormant_stays_dormant():
    """DORMANT doesn't transition via evaluate_transitions — needs patient message."""
    state = _make_state(phase=PHASE_DORMANT, has_logged_in=True, has_consented=True, consecutive_unanswered_count=3)
    result = evaluate_transitions(state)
    assert result["phase"] == PHASE_DORMANT
