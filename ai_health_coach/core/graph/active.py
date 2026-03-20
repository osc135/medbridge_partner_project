"""Active subgraph — scheduled check-ins and patient interactions.

Handles Day 2, 5, 7 check-ins with tone adjusted by adherence data.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_health_coach.core.llm import get_llm
from ai_health_coach.core.safety.classifier import (
    SAFE_PROMPT_ADDITION,
    check_and_filter_message,
)
from ai_health_coach.core.state.schemas import ActiveState, PatientState
from ai_health_coach.core.tools.definitions import execute_tool

CHECKIN_PROMPT = """You are a supportive health coach checking in with a patient.

Patient name: {patient_name}
Patient goal: {goal_type} {frequency} in the {time_of_day}
Assigned exercises: {exercises}
Check-in type: {checkin_type}
Tone: {tone}

Generate a personalized check-in message that:
- References their specific goal naturally (the one THEY committed to)
- Matches the tone specified
- Does not give clinical advice
- Is concise (2-3 sentences)
- If tone is "nudge", be direct — remind them what they committed to and ask what they can do today
- Never suggest that skipping is okay
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


def determine_tone(patient_id: str) -> str:
    """Determine the check-in tone from adherence data."""
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
    tone = determine_tone(parent_state["patient_id"])
    goal = parent_state.get("goal") or {}

    exercises = ", ".join(parent_state["assigned_exercises"]) or "your exercises"

    prompt = CHECKIN_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
        exercises=exercises,
        checkin_type=checkin_type,
        tone=tone,
    )

    messages = [SystemMessage(content=prompt)]

    # Include conversation history for context
    for msg in parent_state["messages"][-6:]:  # Last few messages for context
        if msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))

    response = _safe_generate(messages)

    active_state = ActiveState(
        current_checkin=checkin_type,
        interaction_tone=tone,
    )

    parent_updates = {
        "completed_checkins": parent_state["completed_checkins"] + [checkin_type],
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

    response = _safe_generate(messages)

    active_state = ActiveState(
        current_checkin=parent_state["completed_checkins"][-1] if parent_state["completed_checkins"] else "day_2",
        interaction_tone=tone,
    )

    # Patient responded — reset unanswered count
    parent_updates = {
        "consecutive_unanswered_count": 0,
        "current_backoff_step": 0,
    }

    return {
        "response": response,
        "active_state": active_state,
        "parent_updates": parent_updates,
    }


def _safe_generate(prompt_messages: list) -> str:
    """Generate with safety check."""
    llm = get_llm()
    response = llm.invoke(prompt_messages)
    message_text = response.content

    def regenerate():
        augmented = prompt_messages.copy()
        augmented.append(SystemMessage(content=SAFE_PROMPT_ADDITION))
        return llm.invoke(augmented).content

    result = check_and_filter_message(message_text, regenerate_fn=regenerate)
    return result["final_message"]
