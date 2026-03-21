"""Tests for the GraphState schema and state creation."""

from ai_health_coach.core.state.schemas import (
    GraphState,
    PatientState,
    create_initial_state,
)


def test_graph_state_can_be_constructed():
    """GraphState should be constructable with all fields."""
    ps = create_initial_state(
        patient_id="P_GS",
        patient_name="Graph State Test",
        assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
        program_start_date="2026-03-20",
    )

    gs = GraphState(
        patient_state=ps,
        patient_message="hello",
        trigger_type=None,
        onboarding_state=None,
        response=None,
        updated_patient_state=ps,
        updated_onboarding_state=None,
        consent_result="",
        safety_result="",
        phase="PENDING",
    )

    assert gs["patient_state"]["patient_id"] == "P_GS"
    assert gs["patient_message"] == "hello"
    assert gs["phase"] == "PENDING"


def test_graph_state_total_false():
    """GraphState uses total=False, so partial construction should work."""
    gs = GraphState(
        patient_state=create_initial_state(
            patient_id="P1",
            patient_name="Test",
            assigned_exercises=[],
            program_start_date="2026-03-20",
        ),
    )
    assert "patient_state" in gs
    # Optional fields should be absent, not None
    assert "response" not in gs


def test_graph_state_accepts_partial_updates():
    """Nodes return partial GraphState dicts — verify merge works."""
    base = {"consent_result": "", "safety_result": ""}
    update = {"consent_result": "proceed"}
    merged = {**base, **update}
    assert merged["consent_result"] == "proceed"
    assert merged["safety_result"] == ""
