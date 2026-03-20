"""Tool definitions — real interfaces, stubbed implementations.

The LLM sees these as proper tool definitions and autonomously decides
when to call them based on the description field.
"""

from datetime import datetime


def set_goal(patient_id: str, goal_type: str, frequency: str, time_of_day: str) -> dict:
    """Store a confirmed exercise goal for the patient.

    Called at the end of onboarding when the patient has confirmed their goal.
    """
    return {
        "success": True,
        "goal_id": f"goal_{patient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "message": f"Goal set for patient {patient_id}",
    }


def set_reminder(patient_id: str, scheduled_for: str, interaction_type: str) -> dict:
    """Schedule a follow-up reminder for the patient.

    interaction_type: 'day_2_checkin' | 'day_5_checkin' | 'day_7_checkin'
    """
    return {
        "success": True,
        "reminder_id": f"reminder_{patient_id}_{interaction_type}",
        "scheduled_for": scheduled_for,
    }


def get_program_summary(patient_id: str) -> dict:
    """Fetch the patient's assigned home exercise program from MedBridge Go.

    Returns exercises, frequency, and prescribing clinician.
    """
    return {
        "success": True,
        "program": {
            "exercises": [
                {"name": "Quad Sets", "sets": 3, "reps": 10},
                {"name": "Heel Slides", "sets": 3, "reps": 15},
                {"name": "Straight Leg Raises", "sets": 2, "reps": 10},
            ],
            "frequency": "daily",
            "assigned_by": "Dr. Smith",
        },
    }


def get_adherence_summary(patient_id: str) -> dict:
    """Fetch the patient's exercise adherence data.

    Returns completion rate and trend for tone determination.
    """
    return {
        "success": True,
        "adherence": {
            "total_days": 7,
            "completed_days": 5,
            "completion_rate": 0.71,
            "trend": "improving",
        },
    }


def alert_clinician(
    patient_id: str, alert_type: str, urgency: str, context: str
) -> dict:
    """Send an alert to the patient's clinician.

    alert_type: 'disengagement' | 'mental_health_crisis'
    urgency: 'routine' | 'urgent'
    """
    return {
        "success": True,
        "alert_id": f"alert_{patient_id}_{alert_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
    }


# Tool registry for easy lookup by name
TOOL_REGISTRY = {
    "set_goal": set_goal,
    "set_reminder": set_reminder,
    "get_program_summary": get_program_summary,
    "get_adherence_summary": get_adherence_summary,
    "alert_clinician": alert_clinician,
}

# Least-privilege mapping: which tools each subgraph can access
SUBGRAPH_TOOLS = {
    "ONBOARDING": ["set_goal", "set_reminder", "get_program_summary", "alert_clinician"],
    "ACTIVE": ["set_reminder", "get_program_summary", "get_adherence_summary", "alert_clinician"],
    "RE_ENGAGING": ["set_reminder", "get_program_summary", "get_adherence_summary", "alert_clinician"],
    "DORMANT": [],
}


def get_tools_for_phase(phase: str) -> list[dict]:
    """Return LangChain-compatible tool definitions for the given phase."""
    from langchain_core.tools import tool as lc_tool

    tool_names = SUBGRAPH_TOOLS.get(phase, [])
    tools = []
    for name in tool_names:
        fn = TOOL_REGISTRY[name]
        tools.append(lc_tool(fn))
    return tools


def execute_tool(tool_name: str, tool_args: dict) -> dict:
    """Execute a tool by name with the given arguments.

    Handles failures by returning error dicts rather than raising.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        result = fn(**tool_args)
        if not result.get("success"):
            return {"success": False, "error": f"Tool {tool_name} returned failure", "result": result}
        return result
    except Exception as e:
        return {"success": False, "error": f"Tool {tool_name} raised: {e}"}
