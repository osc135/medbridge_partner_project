"""Tests for tool calling infrastructure — registry, phase access, and execute_tool."""

from ai_health_coach.core.tools.definitions import (
    SUBGRAPH_TOOLS,
    TOOL_REGISTRY,
    execute_tool,
    get_tools_for_phase,
)


# ─── Tool registry completeness ────────────────────────────


def test_registry_has_all_five_tools():
    expected = {"set_goal", "set_reminder", "get_program_summary", "get_adherence_summary", "alert_clinician"}
    assert set(TOOL_REGISTRY.keys()) == expected


def test_all_registry_entries_are_callable():
    for name, fn in TOOL_REGISTRY.items():
        assert callable(fn), f"{name} is not callable"


# ─── Phase tool access (least privilege) ───────────────────


def test_onboarding_has_set_goal():
    assert "set_goal" in SUBGRAPH_TOOLS["ONBOARDING"]


def test_active_cannot_set_goal():
    assert "set_goal" not in SUBGRAPH_TOOLS["ACTIVE"]


def test_active_has_adherence():
    assert "get_adherence_summary" in SUBGRAPH_TOOLS["ACTIVE"]


def test_onboarding_no_adherence():
    assert "get_adherence_summary" not in SUBGRAPH_TOOLS["ONBOARDING"]


def test_dormant_has_no_tools():
    assert SUBGRAPH_TOOLS["DORMANT"] == []


def test_alert_clinician_everywhere_except_dormant():
    for phase in ["ONBOARDING", "ACTIVE", "RE_ENGAGING"]:
        assert "alert_clinician" in SUBGRAPH_TOOLS[phase]
    assert "alert_clinician" not in SUBGRAPH_TOOLS["DORMANT"]


# ─── get_tools_for_phase returns LangChain tools ───────────


def test_get_tools_for_phase_returns_list():
    tools = get_tools_for_phase("ACTIVE")
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_get_tools_for_phase_dormant_empty():
    tools = get_tools_for_phase("DORMANT")
    assert tools == []


def test_get_tools_for_phase_unknown_empty():
    tools = get_tools_for_phase("NONEXISTENT")
    assert tools == []


def test_get_tools_for_phase_tools_are_callable():
    tools = get_tools_for_phase("ONBOARDING")
    for t in tools:
        # LangChain tools should have a name attribute
        assert hasattr(t, "name")


# ─── execute_tool error handling ───────────────────────────


def test_execute_unknown_tool():
    result = execute_tool("nonexistent_tool", {})
    assert result["success"] is False
    assert "Unknown tool" in result["error"]


def test_execute_tool_with_missing_args():
    result = execute_tool("set_goal", {"patient_id": "P001"})
    assert result["success"] is False
    assert "error" in result


def test_execute_tool_success():
    result = execute_tool("set_goal", {
        "patient_id": "P001",
        "goal_type": "exercise",
        "frequency": "daily",
        "time_of_day": "morning",
    })
    assert result["success"] is True


def test_execute_alert_clinician():
    result = execute_tool("alert_clinician", {
        "patient_id": "P001",
        "alert_type": "disengagement",
        "urgency": "routine",
        "context": "Test alert",
    })
    assert result["success"] is True
    assert "alert_id" in result
