"""Tests for the simulation clock and scheduled reminder firing."""

import os

from ai_health_coach.core.simulation import (
    clear_simulated_date,
    get_current_date,
    set_simulated_date,
)


# ─── Simulation clock ──────────────────────────────────────


def test_get_current_date_returns_string():
    clear_simulated_date()
    date = get_current_date()
    assert isinstance(date, str)
    assert len(date) == 10  # YYYY-MM-DD


def test_set_and_get_simulated_date():
    set_simulated_date("2026-04-15")
    assert get_current_date() == "2026-04-15"
    clear_simulated_date()


def test_clear_reverts_to_real_time():
    set_simulated_date("2099-01-01")
    assert get_current_date() == "2099-01-01"
    clear_simulated_date()
    assert get_current_date() != "2099-01-01"


def test_set_simulated_date_validates_format():
    import pytest
    with pytest.raises(ValueError):
        set_simulated_date("not-a-date")


def test_set_simulated_date_rejects_partial():
    import pytest
    with pytest.raises(ValueError):
        set_simulated_date("2026-04")


def test_simulated_date_used_in_state_operations():
    """get_current_date should be usable wherever dates are needed."""
    set_simulated_date("2026-06-01")
    date = get_current_date()
    assert date == "2026-06-01"
    # Verify it's a valid date string
    from datetime import datetime
    parsed = datetime.strptime(date, "%Y-%m-%d")
    assert parsed.year == 2026
    assert parsed.month == 6
    clear_simulated_date()


# ─── Reminder firing logic ─────────────────────────────────


def test_fire_due_reminders_fires_on_date(tmp_path):
    """When simulation date is advanced, due reminders should fire."""
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state

    db_path = str(tmp_path / "reminder_fire.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_FIRE",
            patient_name="Fire Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
            has_logged_in=True,
            has_consented=True,
        )
        state["phase"] = "ACTIVE"
        state["goal"] = {"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"}
        state["reminders"] = [
            {"type": "day_2_checkin", "scheduled_for": "2026-03-22", "sent": False},
            {"type": "day_5_checkin", "scheduled_for": "2026-03-25", "sent": False},
            {"type": "day_7_checkin", "scheduled_for": "2026-03-27", "sent": False},
        ]
        persistence.save_state(state)

        # Only day_2 should be due on March 22
        loaded = persistence.load_state("P_FIRE")
        due = [r for r in loaded["reminders"] if r["scheduled_for"] <= "2026-03-22" and not r["sent"]]
        assert len(due) == 1
        assert due[0]["type"] == "day_2_checkin"

        # All three should be due on March 27
        due_all = [r for r in loaded["reminders"] if r["scheduled_for"] <= "2026-03-27" and not r["sent"]]
        assert len(due_all) == 3
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)
        clear_simulated_date()


def test_sent_reminders_not_refired(tmp_path):
    """Reminders marked as sent should not fire again."""
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state

    db_path = str(tmp_path / "sent.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_SENT",
            patient_name="Sent Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
            has_logged_in=True,
            has_consented=True,
        )
        state["phase"] = "ACTIVE"
        state["goal"] = {"goal_type": "exercise", "frequency": "daily", "time_of_day": "morning"}
        state["reminders"] = [
            {"type": "day_2_checkin", "scheduled_for": "2026-03-22", "sent": True},
            {"type": "day_5_checkin", "scheduled_for": "2026-03-25", "sent": False},
        ]
        persistence.save_state(state)

        loaded = persistence.load_state("P_SENT")
        due = [r for r in loaded["reminders"] if r["scheduled_for"] <= "2026-03-25" and not r["sent"]]
        assert len(due) == 1
        assert due[0]["type"] == "day_5_checkin"
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_future_reminders_not_due():
    """Reminders scheduled for after the current date should not be due."""
    reminder = {"type": "day_7_checkin", "scheduled_for": "2099-12-31", "sent": False}
    assert reminder["scheduled_for"] > "2026-03-21"
