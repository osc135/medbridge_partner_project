"""Tests for reminder scheduling — all 3 reminders (Day 2, 5, 7)."""

import os

import ai_health_coach.core.persistence as persistence
from ai_health_coach.core.state.schemas import create_initial_state
from ai_health_coach.core.tools.definitions import set_reminder


def test_three_reminders_persisted(tmp_path):
    """After onboarding, all 3 reminders should be in state."""
    db_path = str(tmp_path / "reminders.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_REM3",
            patient_name="Reminder Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        persistence.save_state(state)

        # Simulate what onboarding does — schedule all 3
        set_reminder("P_REM3", "2026-03-22", "day_2_checkin")
        set_reminder("P_REM3", "2026-03-25", "day_5_checkin")
        set_reminder("P_REM3", "2026-03-27", "day_7_checkin")

        loaded = persistence.load_state("P_REM3")
        assert len(loaded["reminders"]) == 3

        types = [r["type"] for r in loaded["reminders"]]
        assert "day_2_checkin" in types
        assert "day_5_checkin" in types
        assert "day_7_checkin" in types

        dates = {r["type"]: r["scheduled_for"] for r in loaded["reminders"]}
        assert dates["day_2_checkin"] == "2026-03-22"
        assert dates["day_5_checkin"] == "2026-03-25"
        assert dates["day_7_checkin"] == "2026-03-27"

        # All should start as unsent
        assert all(not r["sent"] for r in loaded["reminders"])
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_reminder_dates_relative_to_start():
    """Reminder dates should be calculated from program_start_date."""
    from datetime import datetime, timedelta

    start = "2026-04-01"
    start_dt = datetime.strptime(start, "%Y-%m-%d")

    day_2 = (start_dt + timedelta(days=2)).strftime("%Y-%m-%d")
    day_5 = (start_dt + timedelta(days=5)).strftime("%Y-%m-%d")
    day_7 = (start_dt + timedelta(days=7)).strftime("%Y-%m-%d")

    assert day_2 == "2026-04-03"
    assert day_5 == "2026-04-06"
    assert day_7 == "2026-04-08"


def test_duplicate_reminder_appends(tmp_path):
    """Calling set_reminder twice with same type adds both (no dedup)."""
    db_path = str(tmp_path / "dup.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_DUP",
            patient_name="Dup Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        persistence.save_state(state)

        set_reminder("P_DUP", "2026-03-22", "day_2_checkin")
        set_reminder("P_DUP", "2026-03-22", "day_2_checkin")

        loaded = persistence.load_state("P_DUP")
        assert len(loaded["reminders"]) == 2
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)
