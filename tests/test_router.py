"""Tests for the router — consent gate blocking and phase dispatch."""

from ai_health_coach.core.graph.router import (
    NEVER_CONSENTED_MESSAGE,
    REVOKED_MESSAGE,
    route_message,
)
from ai_health_coach.core.safety.classifier import CRISIS_MESSAGE
from ai_health_coach.core.state.schemas import create_initial_state


def _make_state(**overrides):
    state = create_initial_state(
        patient_id="P_ROUTER",
        patient_name="Router Test",
        assigned_exercises=[{"name": "Quad Sets", "sets": 3, "reps": 10}],
        program_start_date="2026-03-20",
    )
    state.update(overrides)
    return state


def test_route_blocks_without_consent():
    state = _make_state(has_logged_in=False, has_consented=False)
    result = route_message(state, patient_message="hello")
    assert result["response"] == NEVER_CONSENTED_MESSAGE


def test_route_blocks_revoked_consent():
    state = _make_state(has_logged_in=True, has_consented=False)
    result = route_message(state, patient_message="hello")
    assert result["response"] == REVOKED_MESSAGE


def test_route_crisis_triggers_alert():
    """Crisis messages should return CRISIS_MESSAGE regardless of phase."""
    state = _make_state(
        has_logged_in=True,
        has_consented=True,
        phase="ACTIVE",
        goal={"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"},
    )
    result = route_message(state, patient_message="I want to kill myself")
    assert result["response"] == CRISIS_MESSAGE
    # Message should be recorded in history
    assert any("kill" in m["content"] for m in result["state"]["messages"] if m["role"] == "user")


def test_route_pending_with_consent_transitions():
    """PENDING → ONBOARDING is tested via evaluate_transitions (no LLM needed).
    route_message would call the LLM for the welcome, so we test the transition
    logic directly instead.
    """
    from ai_health_coach.core.graph.router import evaluate_transitions
    state = _make_state(has_logged_in=True, has_consented=True, phase="PENDING")
    result = evaluate_transitions(state)
    assert result["phase"] == "ONBOARDING"


def test_route_dormant_no_outbound():
    state = _make_state(
        has_logged_in=True,
        has_consented=True,
        phase="DORMANT",
        consecutive_unanswered_count=3,
    )
    result = route_message(state, trigger_type="backoff")
    assert result["response"] is None


def test_route_records_messages():
    """User and assistant messages should be added to state history."""
    state = _make_state(
        has_logged_in=True,
        has_consented=True,
        phase="ACTIVE",
        goal={"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"},
    )
    # Crisis is the only path that doesn't need LLM
    result = route_message(state, patient_message="I want to end it all")
    messages = result["state"]["messages"]
    assert len(messages) >= 2
    assert messages[-2]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
