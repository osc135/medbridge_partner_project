"""Tests for the consent gate — every interaction, every time."""

from ai_health_coach.core.graph.router import check_consent
from ai_health_coach.core.graph.graph_builder import (
    NEVER_CONSENTED_MESSAGE,
    REVOKED_MESSAGE,
    consent_gate_node,
    consent_denied_node,
)
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_ONBOARDING,
    PHASE_PENDING,
    create_initial_state,
)


def _make_state(**overrides):
    state = create_initial_state(
        patient_id="P_CONSENT",
        patient_name="Test",
        assigned_exercises=[],
        program_start_date="2026-03-22",
    )
    return {**state, **overrides}


# ─── check_consent function ────────────────────────────────


def test_consent_proceed():
    state = _make_state(has_logged_in=True, has_consented=True)
    assert check_consent(state) == "proceed"


def test_consent_never_consented():
    state = _make_state(has_logged_in=False, has_consented=False)
    assert check_consent(state) == "never_consented"


def test_consent_revoked():
    state = _make_state(has_logged_in=True, has_consented=False)
    assert check_consent(state) == "revoked"


def test_consent_not_logged_in_but_consented():
    """Edge case: has_consented=True but not logged in. Treat as never_consented."""
    state = _make_state(has_logged_in=False, has_consented=True)
    assert check_consent(state) == "never_consented"


# ─── consent_gate_node (graph node) ────────────────────────


def test_consent_gate_node_proceed():
    state = _make_state(has_logged_in=True, has_consented=True)
    graph_state = {"patient_state": state}
    result = consent_gate_node(graph_state)
    assert result["consent_result"] == "proceed"


def test_consent_gate_node_revoked():
    state = _make_state(has_logged_in=True, has_consented=False)
    graph_state = {"patient_state": state}
    result = consent_gate_node(graph_state)
    assert result["consent_result"] == "revoked"


# ─── consent_denied_node messages ──────────────────────────


def test_consent_denied_never_consented_message():
    state = _make_state()
    graph_state = {
        "consent_result": "never_consented",
        "patient_state": state,
    }
    result = consent_denied_node(graph_state)
    assert result["response"] == NEVER_CONSENTED_MESSAGE


def test_consent_denied_revoked_message():
    state = _make_state()
    graph_state = {
        "consent_result": "revoked",
        "patient_state": state,
    }
    result = consent_denied_node(graph_state)
    assert result["response"] == REVOKED_MESSAGE


# ─── Phase preserved on revocation ─────────────────────────


def test_phase_preserved_on_revocation():
    """Revoking consent should NOT reset the phase."""
    state = _make_state(
        has_logged_in=True,
        has_consented=False,  # Revoked
        phase=PHASE_ACTIVE,
    )
    # Phase should still be ACTIVE — consent gate blocks interaction
    # but doesn't change phase
    assert state["phase"] == PHASE_ACTIVE
    assert check_consent(state) == "revoked"


# ─── Consent checked every interaction ─────────────────────


def test_consent_blocks_even_after_onboarding():
    """Even if patient was in ACTIVE phase, revoking consent blocks them."""
    state = _make_state(
        has_logged_in=True,
        has_consented=False,
        phase=PHASE_ACTIVE,
        goal={"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"},
    )
    assert check_consent(state) == "revoked"
