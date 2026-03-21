"""Tests for state schemas and persistence."""

import os
from ai_health_coach.core.state.schemas import (
    PHASE_PENDING,
    create_initial_state,
)


def test_create_initial_state_defaults():
    state = create_initial_state(
        patient_id="P001",
        patient_name="Jane Doe",
        assigned_exercises=[{"name": "Quad Sets", "sets": 3, "reps": 10}],
        program_start_date="2026-03-20",
    )
    assert state["patient_id"] == "P001"
    assert state["patient_name"] == "Jane Doe"
    assert state["phase"] == PHASE_PENDING
    assert state["goal"] is None
    assert state["has_logged_in"] is False
    assert state["has_consented"] is False
    assert state["consecutive_unanswered_count"] == 0
    assert state["current_backoff_step"] == 0
    assert state["clinician_alerted"] is False
    assert state["completed_checkins"] == []
    assert state["messages"] == []
    assert state["failed_alerts"] == []
    assert state["reminders"] == []


def test_create_initial_state_with_consent():
    state = create_initial_state(
        patient_id="P002",
        patient_name="Bob",
        assigned_exercises=[{"name": "Lunges", "sets": 2, "reps": 15}],
        program_start_date="2026-03-20",
        has_logged_in=True,
        has_consented=True,
    )
    assert state["has_logged_in"] is True
    assert state["has_consented"] is True


def test_exercises_are_structured():
    exercises = [
        {"name": "Quad Sets", "sets": 3, "reps": 10},
        {"name": "Heel Slides", "sets": 2, "reps": 15},
    ]
    state = create_initial_state(
        patient_id="P003",
        patient_name="Test",
        assigned_exercises=exercises,
        program_start_date="2026-03-20",
    )
    assert len(state["assigned_exercises"]) == 2
    assert state["assigned_exercises"][0]["name"] == "Quad Sets"
    assert state["assigned_exercises"][0]["sets"] == 3
    assert state["assigned_exercises"][0]["reps"] == 10
    assert state["assigned_exercises"][1]["name"] == "Heel Slides"


def test_persistence_roundtrip(tmp_path):
    """State should survive save/load cycle."""
    import ai_health_coach.core.persistence as persistence

    db_path = str(tmp_path / "test.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_ROUNDTRIP",
            patient_name="Roundtrip Test",
            assigned_exercises=[{"name": "Squats", "sets": 4, "reps": 12}],
            program_start_date="2026-03-20",
            has_logged_in=True,
            has_consented=True,
        )
        state["messages"] = [{"role": "assistant", "content": "Hello!"}]
        state["phase"] = "ACTIVE"
        state["goal"] = {"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"}

        persistence.save_state(state)
        loaded = persistence.load_state("P_ROUNDTRIP")

        assert loaded is not None
        assert loaded["patient_id"] == "P_ROUNDTRIP"
        assert loaded["phase"] == "ACTIVE"
        assert loaded["goal"]["frequency"] == "daily"
        assert loaded["assigned_exercises"][0]["name"] == "Squats"
        assert loaded["assigned_exercises"][0]["sets"] == 4
        assert len(loaded["messages"]) == 1
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_persistence_load_nonexistent(tmp_path):
    import ai_health_coach.core.persistence as persistence

    db_path = str(tmp_path / "empty.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        assert persistence.load_state("DOES_NOT_EXIST") is None
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_persistence_delete(tmp_path):
    import ai_health_coach.core.persistence as persistence

    db_path = str(tmp_path / "del.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_DEL",
            patient_name="Delete Me",
            assigned_exercises=[{"name": "Test", "sets": 1, "reps": 1}],
            program_start_date="2026-03-20",
        )
        persistence.save_state(state)
        assert persistence.load_state("P_DEL") is not None

        assert persistence.delete_patient("P_DEL") is True
        assert persistence.load_state("P_DEL") is None
        assert persistence.delete_patient("P_DEL") is False
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_persistence_list_patients(tmp_path):
    import ai_health_coach.core.persistence as persistence

    db_path = str(tmp_path / "list.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        for i in range(3):
            state = create_initial_state(
                patient_id=f"P{i}",
                patient_name=f"Patient {i}",
                assigned_exercises=[{"name": "Test", "sets": 1, "reps": 1}],
                program_start_date="2026-03-20",
            )
            persistence.save_state(state)

        patients = persistence.list_patients()
        assert len(patients) == 3
        ids = {p["patient_id"] for p in patients}
        assert ids == {"P0", "P1", "P2"}
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)
