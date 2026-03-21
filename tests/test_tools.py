"""Tests for tool definitions and execution."""

import os

from ai_health_coach.core.tools.definitions import (
    SUBGRAPH_TOOLS,
    execute_tool,
    get_program_summary,
    set_goal,
    set_reminder,
    get_adherence_summary,
    alert_clinician,
)


def test_set_goal_returns_success():
    result = set_goal("P001", "exercise", "daily", "morning")
    assert result["success"] is True
    assert "goal_id" in result


def test_set_goal_includes_patient_id():
    result = set_goal("P999", "stretching", "3x per week", "evening")
    assert "P999" in result["goal_id"]


def test_set_reminder_returns_scheduled_date():
    result = set_reminder("P001", "2026-03-22", "day_2_checkin")
    assert result["success"] is True
    assert result["scheduled_for"] == "2026-03-22"
    assert "reminder_id" in result


def test_get_program_summary_reads_from_state(tmp_path):
    """get_program_summary should read from persisted state, not hardcoded data."""
    import ai_health_coach.core.persistence as persistence

    db_path = str(tmp_path / "test.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        from ai_health_coach.core.state.schemas import create_initial_state

        exercises = [{"name": "Lunges", "sets": 2, "reps": 15}]
        state = create_initial_state(
            patient_id="P_TEST",
            patient_name="Test",
            assigned_exercises=exercises,
            program_start_date="2026-03-20",
        )
        persistence.save_state(state)

        result = get_program_summary("P_TEST")
        assert result["success"] is True
        assert result["program"]["exercises"] == exercises
        assert result["program"]["exercises"][0]["name"] == "Lunges"
        assert result["program"]["exercises"][0]["sets"] == 2
        assert result["program"]["exercises"][0]["reps"] == 15
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_get_program_summary_missing_patient():
    """Should return failure for nonexistent patient."""
    import ai_health_coach.core.persistence as persistence

    result = get_program_summary("NONEXISTENT_PATIENT_XYZ")
    assert result["success"] is False


def test_get_adherence_summary_empty_log(tmp_path):
    """No exercise log → 0% completion, stable trend."""
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state

    db_path = str(tmp_path / "adh_empty.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_ADH_EMPTY",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        persistence.save_state(state)

        result = get_adherence_summary("P_ADH_EMPTY")
        assert result["success"] is True
        assert result["adherence"]["total_days"] == 0
        assert result["adherence"]["completion_rate"] == 0.0
        assert result["adherence"]["trend"] == "stable"
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_get_adherence_summary_with_log(tmp_path):
    """Exercise log with mixed results → correct rate and trend."""
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state

    db_path = str(tmp_path / "adh_log.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_ADH_LOG",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        state["exercise_log"] = [
            {"date": "2026-03-20", "completed": True, "source": "patient_response"},
            {"date": "2026-03-21", "completed": True, "source": "patient_response"},
            {"date": "2026-03-22", "completed": False, "source": "unanswered_day_2"},
            {"date": "2026-03-23", "completed": True, "source": "patient_response"},
        ]
        persistence.save_state(state)

        result = get_adherence_summary("P_ADH_LOG")
        assert result["success"] is True
        assert result["adherence"]["total_days"] == 4
        assert result["adherence"]["completed_days"] == 3
        assert result["adherence"]["completion_rate"] == 0.75
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_get_adherence_summary_trend_improving(tmp_path):
    """Trend should be improving when recent entries are better than earlier ones."""
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state

    db_path = str(tmp_path / "adh_trend.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_ADH_TREND",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        state["exercise_log"] = [
            {"date": "2026-03-20", "completed": False, "source": "unanswered"},
            {"date": "2026-03-21", "completed": False, "source": "unanswered"},
            {"date": "2026-03-22", "completed": False, "source": "unanswered"},
            {"date": "2026-03-23", "completed": True, "source": "patient_response"},
            {"date": "2026-03-24", "completed": True, "source": "patient_response"},
            {"date": "2026-03-25", "completed": True, "source": "patient_response"},
        ]
        persistence.save_state(state)

        result = get_adherence_summary("P_ADH_TREND")
        assert result["adherence"]["trend"] == "improving"
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_get_adherence_summary_trend_declining(tmp_path):
    """Trend should be declining when recent entries are worse."""
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state

    db_path = str(tmp_path / "adh_decline.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_ADH_DEC",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        state["exercise_log"] = [
            {"date": "2026-03-20", "completed": True, "source": "patient_response"},
            {"date": "2026-03-21", "completed": True, "source": "patient_response"},
            {"date": "2026-03-22", "completed": True, "source": "patient_response"},
            {"date": "2026-03-23", "completed": False, "source": "unanswered"},
            {"date": "2026-03-24", "completed": False, "source": "unanswered"},
            {"date": "2026-03-25", "completed": False, "source": "unanswered"},
        ]
        persistence.save_state(state)

        result = get_adherence_summary("P_ADH_DEC")
        assert result["adherence"]["trend"] == "declining"
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_get_adherence_summary_missing_patient():
    result = get_adherence_summary("NONEXISTENT_XYZ")
    assert result["success"] is False


def test_alert_clinician_returns_success():
    result = alert_clinician("P001", "disengagement", "routine", "Patient unresponsive")
    assert result["success"] is True
    assert "alert_id" in result


def test_alert_clinician_crisis():
    result = alert_clinician("P001", "mental_health_crisis", "urgent", "Crisis detected")
    assert result["success"] is True
    assert "mental_health_crisis" in result["alert_id"]


def test_execute_tool_unknown():
    result = execute_tool("nonexistent_tool", {})
    assert result["success"] is False
    assert "Unknown tool" in result["error"]


def test_execute_tool_by_name():
    result = execute_tool("set_goal", {
        "patient_id": "P001",
        "goal_type": "exercise",
        "frequency": "daily",
        "time_of_day": "morning",
    })
    assert result["success"] is True


def test_execute_tool_bad_args():
    """Should handle missing required args gracefully."""
    result = execute_tool("set_goal", {"patient_id": "P001"})
    assert result["success"] is False
    assert "error" in result


def test_least_privilege_mapping():
    # set_goal only available in ONBOARDING
    assert "set_goal" in SUBGRAPH_TOOLS["ONBOARDING"]
    assert "set_goal" not in SUBGRAPH_TOOLS["ACTIVE"]
    assert "set_goal" not in SUBGRAPH_TOOLS["RE_ENGAGING"]
    assert "set_goal" not in SUBGRAPH_TOOLS["DORMANT"]

    # get_adherence_summary not in ONBOARDING
    assert "get_adherence_summary" not in SUBGRAPH_TOOLS["ONBOARDING"]
    assert "get_adherence_summary" in SUBGRAPH_TOOLS["ACTIVE"]
    assert "get_adherence_summary" in SUBGRAPH_TOOLS["RE_ENGAGING"]

    # alert_clinician available everywhere except DORMANT
    assert "alert_clinician" in SUBGRAPH_TOOLS["ONBOARDING"]
    assert "alert_clinician" in SUBGRAPH_TOOLS["ACTIVE"]
    assert "alert_clinician" in SUBGRAPH_TOOLS["RE_ENGAGING"]
    assert "alert_clinician" not in SUBGRAPH_TOOLS["DORMANT"]

    # DORMANT has no tools
    assert SUBGRAPH_TOOLS["DORMANT"] == []
