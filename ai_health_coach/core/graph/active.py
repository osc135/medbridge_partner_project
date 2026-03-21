"""Active subgraph — scheduled check-ins and patient interactions.

Handles Day 2, 5, 7 check-ins with tone adjusted by adherence data.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_health_coach.core.llm import safe_generate, tool_calling_generate
from ai_health_coach.core.simulation import get_current_date
from ai_health_coach.core.state.schemas import ActiveState, PatientState
from ai_health_coach.core.tools.definitions import execute_tool, get_tools_for_phase


POSITIVE_INDICATORS = [
    "did", "done", "finished", "completed", "yes", "yeah", "yep",
    "crushed it", "nailed it", "got it done", "all done", "did them",
    "did my", "worked out", "exercised", "kept up",
]

NEGATIVE_INDICATORS = [
    "didn't", "did not", "skipped", "missed", "no", "nope", "not today",
    "couldn't", "could not", "forgot", "don't want", "too tired",
    "not feeling", "can't", "haven't",
]


def _detect_adherence(message: str) -> bool | None:
    """Detect if patient did their exercises from their message.

    Returns True (did them), False (didn't), or None (unclear).
    """
    msg_lower = message.lower()

    # Check negatives first — they take priority since "didn't" contains "did"
    has_negative = any(ind in msg_lower for ind in NEGATIVE_INDICATORS)
    if has_negative:
        return False

    has_positive = any(ind in msg_lower for ind in POSITIVE_INDICATORS)
    if has_positive:
        return True

    return None

CHECKIN_DESCRIPTIONS = {
    "day_2_checkin": "This is Day 2 — the patient's first check-in. They just started. Ask how their first couple days have gone. Are they settling into the routine?",
    "day_5_checkin": "This is Day 5 — midpoint check-in. The patient has been at it for almost a week. Ask about progress, acknowledge the effort of sticking with it this far.",
    "day_7_checkin": "This is Day 7 — one week milestone! Celebrate that they've completed a full week. Reflect on how far they've come since setting their goal.",
}

CHECKIN_PROMPT = """You are a supportive health coach sending a scheduled check-in to a patient.

Patient name: {patient_name}
Patient ID: {patient_id}
Patient goal: {goal_type} {frequency} in the {time_of_day}
Assigned exercises: {exercises}

{checkin_context}

IMPORTANT:
- First, call get_adherence_summary with patient_id='{patient_id}' to check how the patient is doing.
- Use the adherence data to pick the right tone:
  - 80%+ completion → celebration
  - 50%+ and improving → encouragement
  - 50%+ and stable → regular check-in
  - Below 50% → nudge (be direct, remind them of their commitment)
- This is a NEW check-in message. Do NOT repeat or rephrase anything you've already said.
- Reference their specific goal naturally
- Ask them a specific question about how it's going
- Do not give clinical advice
- Keep it to 2-3 sentences
"""

RESPONSE_PROMPT = """You are an accountability-focused health coach. You are warm but firm — your job \
is to help the patient follow through on the commitment they made.

Patient name: {patient_name}
Patient goal: {goal_type} {frequency} in the {time_of_day}
Tone: {tone}

Rules:
- If the patient says they don't want to exercise or are skipping, DO NOT validate skipping. \
Instead, acknowledge their feeling briefly, then redirect toward action. Suggest a smaller \
version of their workout (e.g. "What about just one set of quad sets?"). Remind them of the \
goal THEY chose.
- Never say "it's okay to take a break" or "rest is just as important." That is not your role.
- If they completed their exercises, celebrate genuinely.
- If they're struggling, be empathetic but always steer back toward doing something, even if small.
- Do not give clinical advice.
- Keep responses concise (2-3 sentences).
"""


def determine_tone(patient_id: str, adherence_result: dict | None = None) -> str:
    """Determine the check-in tone from adherence data.

    Pass adherence_result to avoid a redundant tool call when the caller
    already has the data.
    """
    if adherence_result is None:
        adherence_result = execute_tool("get_adherence_summary", {"patient_id": patient_id})

    if not adherence_result.get("success"):
        return "checkin"  # Default tone on failure

    adherence = adherence_result["adherence"]
    rate = adherence["completion_rate"]
    trend = adherence["trend"]

    if rate >= 0.8:
        return "celebration"
    elif rate >= 0.5 and trend == "improving":
        return "encouragement"
    elif rate >= 0.5:
        return "checkin"
    else:
        return "nudge"


def run_checkin(
    parent_state: PatientState,
    checkin_type: str,
) -> dict[str, Any]:
    """Generate a proactive check-in message.

    Returns:
        - response: str (message to send)
        - active_state: ActiveState
        - parent_updates: dict
    """
    goal = parent_state.get("goal") or {}

    exercises = ", ".join(
        f"{ex['name']} ({ex['sets']}x{ex['reps']})" for ex in parent_state["assigned_exercises"]
    ) or "your exercises"

    checkin_context = CHECKIN_DESCRIPTIONS.get(
        checkin_type,
        f"This is a {checkin_type} check-in. Ask how things are going."
    )

    prompt = CHECKIN_PROMPT.format(
        patient_name=parent_state["patient_name"],
        patient_id=parent_state["patient_id"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
        exercises=exercises,
        checkin_context=checkin_context,
    )

    messages = [SystemMessage(content=prompt)]

    tools = get_tools_for_phase("ACTIVE")
    result = tool_calling_generate(messages, tools)
    response = result["message"]

    # Extract adherence data from tool calls if the LLM fetched it
    adherence_result = None
    for tc in result["tool_calls_made"]:
        if tc["name"] == "get_adherence_summary" and tc["result"].get("success"):
            adherence_result = tc["result"]
    tone = determine_tone(parent_state["patient_id"], adherence_result=adherence_result)

    active_state = ActiveState(
        current_checkin=checkin_type,
        interaction_tone=tone,
    )

    # Outbound check-in with no patient reply — count as unanswered
    unanswered = parent_state["consecutive_unanswered_count"] + 1

    # Log as missed since this is an outbound check-in (patient hasn't responded yet)
    log_entry = {
        "date": get_current_date(),
        "completed": False,
        "source": f"unanswered_{checkin_type}",
    }

    parent_updates = {
        "completed_checkins": parent_state["completed_checkins"] + [checkin_type],
        "consecutive_unanswered_count": unanswered,
        "exercise_log": parent_state.get("exercise_log", []) + [log_entry],
    }

    return {
        "response": response,
        "active_state": active_state,
        "parent_updates": parent_updates,
    }


def run_active_response(
    parent_state: PatientState,
    patient_message: str,
) -> dict[str, Any]:
    """Handle a patient message during the active phase.

    Returns:
        - response: str
        - active_state: ActiveState
        - parent_updates: dict
    """
    tone = determine_tone(parent_state["patient_id"])
    goal = parent_state.get("goal") or {}

    prompt = RESPONSE_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
        tone=tone,
    )

    messages = [SystemMessage(content=prompt)]
    for msg in parent_state["messages"][-6:]:
        if msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
    messages.append(HumanMessage(content=patient_message))

    response = safe_generate(messages)

    active_state = ActiveState(
        current_checkin=parent_state["completed_checkins"][-1] if parent_state["completed_checkins"] else "day_2",
        interaction_tone=tone,
    )

    # Patient responded — reset unanswered count
    parent_updates = {
        "consecutive_unanswered_count": 0,
        "current_backoff_step": 0,
    }

    # Log adherence based on what the patient said
    adherence = _detect_adherence(patient_message)
    if adherence is not None:
        log_entry = {
            "date": get_current_date(),
            "completed": adherence,
            "source": "patient_response",
        }
        parent_updates["exercise_log"] = parent_state.get("exercise_log", []) + [log_entry]
        print(f"  \033[{'92' if adherence else '93'}m  📋 ADHERENCE: {'completed' if adherence else 'skipped'}\033[0m")

    return {
        "response": response,
        "active_state": active_state,
        "parent_updates": parent_updates,
    }
