"""Tests for tool definitions and execution."""

from ai_health_coach.core.tools.definitions import (
    SUBGRAPH_TOOLS,
    execute_tool,
    get_program_summary,
    set_goal,
)


def test_set_goal_returns_success():
    result = set_goal("P001", "exercise", "daily", "morning")
    assert result["success"] is True
    assert "goal_id" in result


def test_get_program_summary_returns_exercises():
    result = get_program_summary("P001")
    assert result["success"] is True
    assert len(result["program"]["exercises"]) > 0


def test_execute_tool_unknown():
    result = execute_tool("nonexistent_tool", {})
    assert result["success"] is False


def test_execute_tool_by_name():
    result = execute_tool("set_goal", {
        "patient_id": "P001",
        "goal_type": "exercise",
        "frequency": "daily",
        "time_of_day": "morning",
    })
    assert result["success"] is True


def test_least_privilege_mapping():
    # set_goal only available in ONBOARDING
    assert "set_goal" in SUBGRAPH_TOOLS["ONBOARDING"]
    assert "set_goal" not in SUBGRAPH_TOOLS["ACTIVE"]
    assert "set_goal" not in SUBGRAPH_TOOLS["RE_ENGAGING"]
    assert "set_goal" not in SUBGRAPH_TOOLS["DORMANT"]

    # DORMANT has no tools
    assert SUBGRAPH_TOOLS["DORMANT"] == []
