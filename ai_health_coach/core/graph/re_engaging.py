"""Re-engaging subgraph — handles missed check-ins and backoff responses.

Entered when consecutive_unanswered_count >= 1. Manages exponential backoff
and warm re-engagement when dormant patients return.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_health_coach.core.llm import safe_generate, tool_calling_generate
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_DORMANT,
    ReEngagingState,
    PatientState,
)
from ai_health_coach.core.tools.definitions import execute_tool, get_tools_for_phase

NUDGE_PROMPT = """You are a supportive health coach. The patient hasn't responded to your last message(s).

Patient name: {patient_name}
Patient goal: {goal_type} {frequency} in the {time_of_day}
Unanswered messages: {unanswered_count}
Trigger: {trigger}

Write a gentle, non-pressuring nudge. Don't guilt them. Remind them of their goal
in a positive way. Keep it short. Do not give clinical advice."""

WARM_REENGAGEMENT_PROMPT = """You are a supportive health coach. A patient who had gone quiet is reaching out again!

Patient name: {patient_name}
Patient goal: {goal_type} {frequency} in the {time_of_day}

Welcome them back warmly. Don't make them feel bad for being away. Express genuine
happiness that they're back. Ask how they're doing. Keep it brief. No clinical advice."""


def run_nudge(
    parent_state: PatientState,
) -> dict[str, Any]:
    """Generate a re-engagement nudge message (outbound, no patient message).

    Returns:
        - response: str | None
        - re_engaging_state: ReEngagingState
        - parent_updates: dict
    """
    unanswered = parent_state["consecutive_unanswered_count"] + 1  # Post-increment value
    backoff_step = parent_state["current_backoff_step"] + 1
    goal = parent_state.get("goal") or {}

    # Build nudge prompt — if hitting dormant threshold, instruct LLM to alert clinician
    hitting_dormant = unanswered >= 3 and not parent_state["clinician_alerted"]

    nudge_instructions = NUDGE_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
        unanswered_count=unanswered,
        trigger="missed_checkin",
    )

    if hitting_dormant:
        nudge_instructions += (
            f"\n\nIMPORTANT: This patient has not responded to {unanswered} consecutive messages. "
            f"You MUST call alert_clinician with patient_id='{parent_state['patient_id']}', "
            f"alert_type='disengagement', urgency='routine', "
            f"context='Patient has not responded to {unanswered} consecutive messages.' "
            f"Then write your final nudge message to the patient."
        )

    messages = [SystemMessage(content=nudge_instructions)]

    alert_to_store = None

    if hitting_dormant:
        tools = get_tools_for_phase("RE_ENGAGING")
        result = tool_calling_generate(messages, tools)
        response = result["message"]

        # Collect alert from LLM tool calls
        for tc in result["tool_calls_made"]:
            if tc["name"] == "alert_clinician" and tc["result"].get("success"):
                alert_to_store = tc["result"].get("alert")

        # Verify alert was sent — fall back if LLM didn't call it
        if alert_to_store is None:
            fallback = execute_tool("alert_clinician", {
                "patient_id": parent_state["patient_id"],
                "alert_type": "disengagement",
                "urgency": "routine",
                "context": f"Patient has not responded to {unanswered} consecutive messages.",
            })
            alert_to_store = fallback.get("alert")
    else:
        response = safe_generate(messages)

    re_engaging_state = ReEngagingState(reengagement_trigger="missed_checkin")

    parent_updates = {
        "consecutive_unanswered_count": unanswered,
        "current_backoff_step": backoff_step,
    }

    # Transition to dormant AFTER sending the message
    if unanswered >= 3:
        parent_updates["phase"] = PHASE_DORMANT
        parent_updates["clinician_alerted"] = True

    # Merge alert into parent state
    if alert_to_store:
        existing_alerts = parent_state.get("alerts", [])
        parent_updates["alerts"] = existing_alerts + [alert_to_store]

    return {
        "response": response,
        "re_engaging_state": re_engaging_state,
        "parent_updates": parent_updates,
    }


def run_warm_reengagement(
    parent_state: PatientState,
    patient_message: str,
) -> dict[str, Any]:
    """Handle a message from a patient who was in RE_ENGAGING or returning from DORMANT.

    Returns:
        - response: str
        - re_engaging_state: ReEngagingState
        - parent_updates: dict
    """
    goal = parent_state.get("goal") or {}

    prompt = WARM_REENGAGEMENT_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
    )

    messages = [SystemMessage(content=prompt)]
    for msg in parent_state["messages"][-4:]:
        if msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
    messages.append(HumanMessage(content=patient_message))

    response = safe_generate(messages)

    trigger = "returning_from_dormant" if parent_state["phase"] == PHASE_DORMANT else "backoff_response"
    re_engaging_state = ReEngagingState(reengagement_trigger=trigger)

    parent_updates = {
        "consecutive_unanswered_count": 0,
        "current_backoff_step": 0,
        "clinician_alerted": False,
        "phase": PHASE_ACTIVE,
    }

    return {
        "response": response,
        "re_engaging_state": re_engaging_state,
        "parent_updates": parent_updates,
    }
