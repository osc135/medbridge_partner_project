"""Tests for the LangGraph state graph — conditional edges, compilation, and
end-to-end invocation of non-LLM paths."""

from ai_health_coach.core.graph.graph_builder import (
    build_graph,
    route_after_consent,
    route_after_phase,
    route_after_safety,
)
from ai_health_coach.core.graph.router import (
    NEVER_CONSENTED_MESSAGE,
    REVOKED_MESSAGE,
    route_message,
)
from ai_health_coach.core.safety.classifier import CRISIS_MESSAGE
from ai_health_coach.core.state.schemas import create_initial_state


def _make_state(**overrides):
    state = create_initial_state(
        patient_id="P_GRAPH",
        patient_name="Graph Test",
        assigned_exercises=[{"name": "Quad Sets", "sets": 3, "reps": 10}],
        program_start_date="2026-03-20",
    )
    state.update(overrides)
    return state


# ─── Graph compilation ─────────────────────────────────────────────


def test_graph_compiles():
    graph = build_graph()
    assert graph is not None
    assert "CompiledStateGraph" in type(graph).__name__


def test_graph_compiles_only_once():
    """build_graph returns a new graph each time, but the router caches it."""
    from ai_health_coach.core.graph.router import _get_graph
    g1 = _get_graph()
    g2 = _get_graph()
    assert g1 is g2


# ─── route_after_consent ───────────────────────────────────────────


def test_consent_edge_proceed():
    assert route_after_consent({"consent_result": "proceed"}) == "safety_check"


def test_consent_edge_never_consented():
    assert route_after_consent({"consent_result": "never_consented"}) == "consent_denied"


def test_consent_edge_revoked():
    assert route_after_consent({"consent_result": "revoked"}) == "consent_denied"


# ─── route_after_safety ────────────────────────────────────────────


def test_safety_edge_safe():
    assert route_after_safety({"safety_result": "safe"}) == "evaluate_transitions"


def test_safety_edge_clinical():
    assert route_after_safety({"safety_result": "clinical"}) == "evaluate_transitions"


def test_safety_edge_crisis():
    assert route_after_safety({"safety_result": "mental_health_crisis"}) == "crisis_response"


# ─── route_after_phase ─────────────────────────────────────────────


def test_phase_edge_pending():
    state = {"phase": "PENDING", "patient_message": None, "trigger_type": None}
    assert route_after_phase(state) == "pending_response"


def test_phase_edge_onboarding():
    state = {"phase": "ONBOARDING", "patient_message": "hello", "trigger_type": None}
    assert route_after_phase(state) == "onboarding_node"


def test_phase_edge_active_trigger():
    state = {"phase": "ACTIVE", "patient_message": None, "trigger_type": "day_2_checkin"}
    assert route_after_phase(state) == "active_checkin"


def test_phase_edge_active_message():
    state = {"phase": "ACTIVE", "patient_message": "did my exercises", "trigger_type": None}
    assert route_after_phase(state) == "active_response"


def test_phase_edge_re_engaging_message():
    state = {"phase": "RE_ENGAGING", "patient_message": "I'm back", "trigger_type": None}
    assert route_after_phase(state) == "warm_reengagement"


def test_phase_edge_re_engaging_trigger():
    state = {"phase": "RE_ENGAGING", "patient_message": None, "trigger_type": "backoff"}
    assert route_after_phase(state) == "nudge_node"


def test_phase_edge_dormant_message():
    state = {"phase": "DORMANT", "patient_message": "hey", "trigger_type": None}
    assert route_after_phase(state) == "dormant_reactivate"


def test_phase_edge_dormant_no_message():
    state = {"phase": "DORMANT", "patient_message": None, "trigger_type": "backoff"}
    assert route_after_phase(state) == "dormant_silent"


# ─── Full graph invocation (non-LLM paths) ─────────────────────────


def test_graph_consent_denied_never_consented():
    state = _make_state(has_logged_in=False, has_consented=False)
    result = route_message(state, patient_message="hello")
    assert result["response"] == NEVER_CONSENTED_MESSAGE
    assert result["state"]["phase"] == "PENDING"


def test_graph_consent_denied_revoked():
    state = _make_state(has_logged_in=True, has_consented=False)
    result = route_message(state, patient_message="hello")
    assert result["response"] == REVOKED_MESSAGE


def test_graph_crisis_path():
    state = _make_state(
        has_logged_in=True,
        has_consented=True,
        phase="ACTIVE",
        goal={"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"},
    )
    result = route_message(state, patient_message="I want to kill myself")
    assert result["response"] == CRISIS_MESSAGE
    assert any("kill" in m["content"] for m in result["state"]["messages"] if m["role"] == "user")
    assert result["state"]["last_contact_date"] is not None


def test_graph_dormant_silent():
    state = _make_state(
        has_logged_in=True,
        has_consented=True,
        phase="DORMANT",
        consecutive_unanswered_count=3,
    )
    result = route_message(state, trigger_type="backoff")
    assert result["response"] is None


def test_graph_dormant_records_trigger():
    state = _make_state(
        has_logged_in=True,
        has_consented=True,
        phase="DORMANT",
        consecutive_unanswered_count=3,
    )
    result = route_message(state, trigger_type="day_7_checkin")
    assert "day_7_checkin" in result["state"]["completed_checkins"]


def test_graph_pending_returns_consent_message():
    """Consented patient in PENDING transitions to ONBOARDING, but without
    LLM we test that evaluate_transitions fires correctly."""
    state = _make_state(has_logged_in=True, has_consented=True, phase="PENDING")
    # This will try to call LLM for onboarding welcome, so just test
    # the transition via evaluate_transitions directly
    from ai_health_coach.core.graph.router import evaluate_transitions
    result = evaluate_transitions(state)
    assert result["phase"] == "ONBOARDING"
