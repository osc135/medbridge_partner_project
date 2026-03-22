"""Active subgraph — scheduled check-ins and patient interactions.

Handles Day 2, 5, 7 check-ins with tone adjusted by check-in type.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_health_coach.core.llm import safe_generate, tool_calling_generate
from ai_health_coach.core.state.schemas import ActiveState, PatientState
from ai_health_coach.core.tools.definitions import get_tools_for_phase


CHECKIN_DESCRIPTIONS = {
    "day_2_checkin": "This is Day 2 — the patient's first check-in. They just started. Ask how their first couple days have gone. Are they settling into the routine?",
    "day_5_checkin": "This is Day 5 — midpoint check-in. The patient has been at it for almost a week. Ask about progress, acknowledge the effort of sticking with it this far.",
    "day_7_checkin": "This is Day 7 — one week milestone! Celebrate that they've completed a full week. Reflect on how far they've come since setting their goal.",
}

# Tone is driven by check-in type, not adherence data
CHECKIN_TONES = {
    "day_2_checkin": "checkin",
    "day_5_checkin": "encouragement",
    "day_7_checkin": "celebration",
}

CHECKIN_PROMPT = """You are a supportive health coach sending a scheduled check-in to a patient.

Patient name: {patient_name}
Patient goal: {goal_type} {frequency} in the {time_of_day}
Assigned exercises: {exercises}
Tone: {tone}

{checkin_context}

IMPORTANT:
- This is a NEW check-in message. Do NOT repeat or rephrase anything you've already said.
- Reference their specific goal naturally
- Match the tone specified above
- Ask them a specific question about how it's going
- Do not give clinical advice
- Keep it to 2-3 sentences
"""

RESPONSE_PROMPT = """You are an accountability-focused health coach. You are warm but firm — your job \
is to help the patient follow through on the commitment they made.

Patient name: {patient_name}
Patient goal: {goal_type} {frequency} in the {time_of_day}

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
    tone = CHECKIN_TONES.get(checkin_type, "checkin")

    prompt = CHECKIN_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
        exercises=exercises,
        checkin_context=checkin_context,
        tone=tone,
    )

    messages = [SystemMessage(content=prompt)]
    response = safe_generate(messages)

    active_state = ActiveState(
        current_checkin=checkin_type,
        interaction_tone=tone,
    )

    # Outbound check-in with no patient reply — count as unanswered
    unanswered = parent_state["consecutive_unanswered_count"] + 1

    parent_updates = {
        "completed_checkins": parent_state["completed_checkins"] + [checkin_type],
        "consecutive_unanswered_count": unanswered,
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
    goal = parent_state.get("goal") or {}

    prompt = RESPONSE_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
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
        interaction_tone="checkin",
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
