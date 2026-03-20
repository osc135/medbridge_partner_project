"""Tests for the consent gate."""

from ai_health_coach.core.graph.router import check_consent
from ai_health_coach.core.state.schemas import create_initial_state


def _make_state(**overrides):
    state = create_initial_state(
        patient_id="P001",
        patient_name="Test Patient",
        assigned_exercises=["Quad Sets"],
        program_start_date="2026-03-20",
    )
    state.update(overrides)
    return state


def test_consent_proceed():
    state = _make_state(has_logged_in=True, has_consented=True)
    assert check_consent(state) == "proceed"


def test_consent_never_consented():
    state = _make_state(has_logged_in=False, has_consented=False)
    assert check_consent(state) == "never_consented"


def test_consent_revoked():
    state = _make_state(has_logged_in=True, has_consented=False)
    assert check_consent(state) == "revoked"
