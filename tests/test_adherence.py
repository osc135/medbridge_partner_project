"""Tests for check-in descriptions and reminder persistence."""

from ai_health_coach.core.graph.active import CHECKIN_DESCRIPTIONS, CHECKIN_TONES


# ─── Check-in descriptions exist for all types ──────────────


def test_checkin_descriptions_day_2():
    assert "day_2_checkin" in CHECKIN_DESCRIPTIONS
    assert "Day 2" in CHECKIN_DESCRIPTIONS["day_2_checkin"]


def test_checkin_descriptions_day_5():
    assert "day_5_checkin" in CHECKIN_DESCRIPTIONS
    assert "Day 5" in CHECKIN_DESCRIPTIONS["day_5_checkin"]


def test_checkin_descriptions_day_7():
    assert "day_7_checkin" in CHECKIN_DESCRIPTIONS
    assert "Day 7" in CHECKIN_DESCRIPTIONS["day_7_checkin"]
    assert "week" in CHECKIN_DESCRIPTIONS["day_7_checkin"].lower()


# ─── Check-in tones by type ─────────────────────────────────


def test_tone_day_2_is_checkin():
    assert CHECKIN_TONES["day_2_checkin"] == "checkin"


def test_tone_day_5_is_encouragement():
    assert CHECKIN_TONES["day_5_checkin"] == "encouragement"


def test_tone_day_7_is_celebration():
    assert CHECKIN_TONES["day_7_checkin"] == "celebration"


# ─── set_reminder persistence ────────────────────────────────


def test_set_reminder_persists(tmp_path):
    """set_reminder should write to state reminders list."""
    import os
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state
    from ai_health_coach.core.tools.definitions import set_reminder

    db_path = str(tmp_path / "reminder.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_REM",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        persistence.save_state(state)

        result = set_reminder("P_REM", "2026-03-22", "day_2_checkin")
        assert result["success"] is True

        loaded = persistence.load_state("P_REM")
        assert len(loaded["reminders"]) == 1
        assert loaded["reminders"][0]["type"] == "day_2_checkin"
        assert loaded["reminders"][0]["scheduled_for"] == "2026-03-22"
        assert loaded["reminders"][0]["sent"] is False
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)
