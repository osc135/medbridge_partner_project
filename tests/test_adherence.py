"""Tests for adherence detection and exercise logging."""

from ai_health_coach.core.graph.active import _detect_adherence, CHECKIN_DESCRIPTIONS


# ─── Adherence detection from patient messages ──────────────


def test_detect_positive_did():
    assert _detect_adherence("I did my exercises today") is True


def test_detect_positive_done():
    assert _detect_adherence("All done with my squats!") is True


def test_detect_positive_finished():
    assert _detect_adherence("Finished them this morning") is True


def test_detect_positive_completed():
    assert _detect_adherence("Completed my routine") is True


def test_detect_positive_yeah():
    assert _detect_adherence("Yeah I worked out") is True


def test_detect_negative_skipped():
    assert _detect_adherence("I skipped today") is False


def test_detect_negative_didnt():
    assert _detect_adherence("I didn't do them") is False


def test_detect_negative_too_tired():
    assert _detect_adherence("Too tired today") is False


def test_detect_negative_forgot():
    assert _detect_adherence("I forgot to do my exercises") is False


def test_detect_negative_cant():
    assert _detect_adherence("I can't do them today") is False


def test_detect_negative_not_today():
    assert _detect_adherence("Not today") is False


def test_detect_ambiguous_question():
    """Questions about exercises should return None, not a false positive."""
    assert _detect_adherence("How many should I do?") is None


def test_detect_ambiguous_greeting():
    assert _detect_adherence("Hi, how are you?") is None


def test_detect_ambiguous_unrelated():
    assert _detect_adherence("The weather is nice today") is None


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


# ─── Exercise log integration ────────────────────────────────


def test_exercise_log_starts_empty():
    from ai_health_coach.core.state.schemas import create_initial_state

    state = create_initial_state(
        patient_id="P_LOG",
        patient_name="Test",
        assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
        program_start_date="2026-03-20",
    )
    assert state["exercise_log"] == []


def test_adherence_summary_reflects_log(tmp_path):
    """Adherence summary should calculate from real exercise log data."""
    import os
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state
    from ai_health_coach.core.tools.definitions import get_adherence_summary

    db_path = str(tmp_path / "adh_reflect.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_REFLECT",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        # 2 completed, 1 missed
        state["exercise_log"] = [
            {"date": "2026-03-20", "completed": True, "source": "patient_response"},
            {"date": "2026-03-21", "completed": True, "source": "patient_response"},
            {"date": "2026-03-22", "completed": False, "source": "unanswered_day_2"},
        ]
        persistence.save_state(state)

        result = get_adherence_summary("P_REFLECT")
        assert result["success"] is True
        assert result["adherence"]["total_days"] == 3
        assert result["adherence"]["completed_days"] == 2
        assert round(result["adherence"]["completion_rate"], 2) == 0.67
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_adherence_summary_all_completed(tmp_path):
    """100% completion should yield celebration tone."""
    import os
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state
    from ai_health_coach.core.tools.definitions import get_adherence_summary
    from ai_health_coach.core.graph.active import determine_tone

    db_path = str(tmp_path / "adh_all.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_ALL",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        state["exercise_log"] = [
            {"date": f"2026-03-{20+i}", "completed": True, "source": "patient_response"}
            for i in range(5)
        ]
        persistence.save_state(state)

        result = get_adherence_summary("P_ALL")
        assert result["adherence"]["completion_rate"] == 1.0

        tone = determine_tone("P_ALL")
        assert tone == "celebration"
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


def test_adherence_summary_none_completed(tmp_path):
    """0% completion should yield nudge tone."""
    import os
    import ai_health_coach.core.persistence as persistence
    from ai_health_coach.core.state.schemas import create_initial_state
    from ai_health_coach.core.graph.active import determine_tone

    db_path = str(tmp_path / "adh_none.db")
    original = os.environ.get("HEALTH_COACH_DB")
    os.environ["HEALTH_COACH_DB"] = db_path

    try:
        state = create_initial_state(
            patient_id="P_NONE",
            patient_name="Test",
            assigned_exercises=[{"name": "Squats", "sets": 2, "reps": 10}],
            program_start_date="2026-03-20",
        )
        state["exercise_log"] = [
            {"date": f"2026-03-{20+i}", "completed": False, "source": "unanswered"}
            for i in range(3)
        ]
        persistence.save_state(state)

        tone = determine_tone("P_NONE")
        assert tone == "nudge"
    finally:
        if original:
            os.environ["HEALTH_COACH_DB"] = original
        else:
            os.environ.pop("HEALTH_COACH_DB", None)


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
