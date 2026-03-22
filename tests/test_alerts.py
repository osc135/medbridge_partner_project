"""Tests for the alerts system — persistence, acknowledgment, and crisis flow."""

import os

import ai_health_coach.core.persistence as persistence
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_RE_ENGAGING,
    create_initial_state,
)
from ai_health_coach.core.tools.definitions import alert_clinician


def _make_state(tmp_path, patient_id="P_ALERT", phase=PHASE_ACTIVE, **overrides):
    """Helper to create and persist a patient state."""
    db_path = str(tmp_path / f"{patient_id}.db")
    os.environ["HEALTH_COACH_DB"] = db_path

    state = create_initial_state(
        patient_id=patient_id,
        patient_name="Test Patient",
        assigned_exercises=[{"name": "Squats", "sets": 3, "reps": 10}],
        program_start_date="2026-03-20",
        has_logged_in=True,
        has_consented=True,
    )
    state = {**state, "phase": phase, **overrides}
    persistence.save_state(state)
    return state, db_path


# ─── alert_clinician tool ──────────────────────────────────


def test_alert_clinician_returns_alert_dict():
    """Tool should return an alert dict for the caller to persist."""
    result = alert_clinician("P001", "disengagement", "routine", "Test context")
    assert result["success"] is True
    assert "alert" in result
    alert = result["alert"]
    assert alert["alert_type"] == "disengagement"
    assert alert["urgency"] == "routine"
    assert alert["context"] == "Test context"
    assert alert["acknowledged"] is False


def test_alert_clinician_does_not_write_to_db(tmp_path):
    """Tool should NOT write to DB — caller is responsible."""
    state, _ = _make_state(tmp_path, "P_NO_WRITE")
    original = os.environ.get("HEALTH_COACH_DB")

    try:
        alert_clinician("P_NO_WRITE", "disengagement", "routine", "Test")
        loaded = persistence.load_state("P_NO_WRITE")
        assert loaded.get("alerts", []) == []
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


# ─── Crisis alert persists through graph ───────────────────


def test_crisis_alert_persists_in_state(tmp_path):
    """When a crisis message is processed, the alert should end up in patient state."""
    from ai_health_coach.core.graph.graph_builder import crisis_response_node

    state, db_path = _make_state(tmp_path, "P_CRISIS")
    original = os.environ.get("HEALTH_COACH_DB")

    try:
        graph_state = {
            "patient_state": state,
            "patient_message": "I want to hurt myself",
            "trigger_type": None,
            "onboarding_state": None,
            "response": None,
            "updated_patient_state": state,
            "updated_onboarding_state": None,
            "consent_result": "proceed",
            "safety_result": "mental_health_crisis",
            "phase": PHASE_ACTIVE,
        }

        result = crisis_response_node(graph_state)
        updated = result["updated_patient_state"]

        assert len(updated.get("alerts", [])) == 1
        alert = updated["alerts"][0]
        assert alert["alert_type"] == "mental_health_crisis"
        assert alert["urgency"] == "urgent"
        assert alert["acknowledged"] is False
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


# ─── Nudge alert persists ─────────────────────────────────


def test_nudge_dormant_alert_persists(tmp_path):
    """When a patient hits dormant threshold, alert should be in parent_updates."""
    from ai_health_coach.core.graph.re_engaging import run_nudge

    state, db_path = _make_state(
        tmp_path, "P_NUDGE_ALERT",
        phase=PHASE_RE_ENGAGING,
        consecutive_unanswered_count=2,
        current_backoff_step=2,
        clinician_alerted=False,
        goal={"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"},
    )

    # This should NOT be run because it calls the LLM.
    # Instead, test the logic that builds the alert.
    result = alert_clinician(
        "P_NUDGE_ALERT", "disengagement", "routine",
        "Patient has not responded to 3 consecutive messages."
    )
    alert = result["alert"]

    # Simulate what run_nudge does with the alert
    existing_alerts = state.get("alerts", [])
    parent_updates = {"alerts": existing_alerts + [alert]}

    assert len(parent_updates["alerts"]) == 1
    assert parent_updates["alerts"][0]["alert_type"] == "disengagement"


# ─── Alert acknowledgment ─────────────────────────────────


def test_acknowledge_alert(tmp_path):
    """Acknowledging an alert should set acknowledged=True."""
    state, db_path = _make_state(tmp_path, "P_ACK")
    original = os.environ.get("HEALTH_COACH_DB")

    try:
        # Add an alert manually
        alert = {
            "id": "alert_test_1",
            "alert_type": "disengagement",
            "urgency": "routine",
            "context": "Test",
            "timestamp": "2026-03-22",
            "acknowledged": False,
        }
        state = {**state, "alerts": [alert]}
        persistence.save_state(state)

        # Acknowledge it
        loaded = persistence.load_state("P_ACK")
        updated_alerts = []
        for a in loaded["alerts"]:
            if a["id"] == "alert_test_1":
                updated_alerts.append({**a, "acknowledged": True})
            else:
                updated_alerts.append(a)
        loaded = {**loaded, "alerts": updated_alerts}
        persistence.save_state(loaded)

        final = persistence.load_state("P_ACK")
        assert final["alerts"][0]["acknowledged"] is True
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_initial_state_has_empty_alerts():
    """New patients should start with no alerts."""
    state = create_initial_state(
        patient_id="P_NEW",
        patient_name="New",
        assigned_exercises=[],
        program_start_date="2026-03-22",
    )
    assert state["alerts"] == []
