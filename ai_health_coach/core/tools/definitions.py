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
    Writes the reminder to state so it's trackable.
    """
    from ai_health_coach.core.persistence import load_state, save_state

    state = load_state(patient_id)
    if state is not None:
        reminder = {
            "type": interaction_type,
            "scheduled_for": scheduled_for,
            "sent": False,
        }
        state = {**state, "reminders": state["reminders"] + [reminder]}
        save_state(state)

    return {
        "success": True,
        "reminder_id": f"reminder_{patient_id}_{interaction_type}",
        "scheduled_for": scheduled_for,
    }


def get_program_summary(patient_id: str) -> dict:
    """Fetch the patient's assigned home exercise program.

    Reads from patient state rather than an external service.
    """
    from ai_health_coach.core.persistence import load_state

    state = load_state(patient_id)
    if state is None:
        return {"success": False, "error": "Patient not found"}

    return {
        "success": True,
        "program": {
            "exercises": state["assigned_exercises"],
            "frequency": "as prescribed by clinician",
        },
    }


def get_adherence_summary(patient_id: str) -> dict:
    """Fetch the patient's exercise adherence data.

    Reads from the exercise_log in state. Returns completion rate and trend.
    """
    from ai_health_coach.core.persistence import load_state

    state = load_state(patient_id)
    if state is None:
        return {"success": False, "error": "Patient not found"}

    log = state.get("exercise_log", [])

    if not log:
        # No data yet — return neutral defaults
        return {
            "success": True,
            "adherence": {
                "total_days": 0,
                "completed_days": 0,
                "completion_rate": 0.0,
                "trend": "stable",
            },
        }

    total = len(log)
    completed = sum(1 for entry in log if entry.get("completed"))
    rate = completed / total if total > 0 else 0.0

    # Trend: compare last 3 entries vs previous 3
    if total >= 6:
        recent = sum(1 for e in log[-3:] if e.get("completed"))
        earlier = sum(1 for e in log[-6:-3] if e.get("completed"))
        if recent > earlier:
            trend = "improving"
        elif recent < earlier:
            trend = "declining"
        else:
            trend = "stable"
    elif total >= 3:
        recent = sum(1 for e in log[-3:] if e.get("completed"))
        if recent >= 2:
            trend = "improving"
        elif recent == 0:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {
        "success": True,
        "adherence": {
            "total_days": total,
            "completed_days": completed,
            "completion_rate": round(rate, 2),
            "trend": trend,
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
    import json as _json

    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        print(f"  \033[91m✗ TOOL CALL: {tool_name}({tool_args}) → UNKNOWN TOOL\033[0m")
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    print(f"  \033[94m→ TOOL CALL: {tool_name}({_json.dumps(tool_args, indent=None)})\033[0m")

    try:
        result = fn(**tool_args)
        if not result.get("success"):
            print(f"  \033[91m  ✗ FAILED: {result}\033[0m")
            return {"success": False, "error": f"Tool {tool_name} returned failure", "result": result}
        print(f"  \033[92m  ✓ RESULT: {_json.dumps(result, indent=None)}\033[0m")
        return result
    except Exception as e:
        print(f"  \033[91m  ✗ ERROR: {e}\033[0m")
        return {"success": False, "error": f"Tool {tool_name} raised: {e}"}
