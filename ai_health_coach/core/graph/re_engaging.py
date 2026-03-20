"""Re-engaging subgraph — handles missed check-ins and backoff responses.

Entered when consecutive_unanswered_count >= 1. Manages exponential backoff
and warm re-engagement when dormant patients return.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_health_coach.core.llm import get_llm
from ai_health_coach.core.safety.classifier import (
    SAFE_PROMPT_ADDITION,
    check_and_filter_message,
)
from ai_health_coach.core.state.schemas import (
    BACKOFF_SCHEDULE,
    PHASE_DORMANT,
    ReEngagingState,
    PatientState,
)
from ai_health_coach.core.tools.definitions import execute_tool

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
    unanswered = parent_state["consecutive_unanswered_count"]
    backoff_step = parent_state["current_backoff_step"] + 1
    goal = parent_state.get("goal") or {}

    # Check if we've hit dormant threshold
    if unanswered >= 3:
        # Transition to DORMANT + alert clinician
        if not parent_state["clinician_alerted"]:
            alert_result = execute_tool("alert_clinician", {
                "patient_id": parent_state["patient_id"],
                "alert_type": "disengagement",
                "urgency": "routine",
                "context": f"Patient has not responded to {unanswered} consecutive messages.",
            })
            parent_updates = {
                "phase": PHASE_DORMANT,
                "clinician_alerted": True,
                "current_backoff_step": backoff_step,
            }
            if not alert_result.get("success"):
                parent_updates["failed_alerts"] = parent_state["failed_alerts"] + [{
                    "type": "disengagement",
                    "patient_id": parent_state["patient_id"],
                    "error": alert_result.get("error", "unknown"),
                }]
        else:
            parent_updates = {
                "phase": PHASE_DORMANT,
                "current_backoff_step": backoff_step,
            }

        re_engaging_state = ReEngagingState(reengagement_trigger="missed_checkin")
        return {
            "response": None,
            "re_engaging_state": re_engaging_state,
            "parent_updates": parent_updates,
        }

    # Generate nudge
    prompt = NUDGE_PROMPT.format(
        patient_name=parent_state["patient_name"],
        goal_type=goal.get("goal_type", "exercise"),
        frequency=goal.get("frequency", "regularly"),
        time_of_day=goal.get("time_of_day", "your preferred time"),
        unanswered_count=unanswered,
        trigger="missed_checkin",
    )

    messages = [SystemMessage(content=prompt)]
    response = _safe_generate(messages)

    re_engaging_state = ReEngagingState(reengagement_trigger="missed_checkin")

    parent_updates = {
        "consecutive_unanswered_count": unanswered + 1,
        "current_backoff_step": backoff_step,
    }

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

    response = _safe_generate(messages)

    trigger = "returning_from_dormant" if parent_state["phase"] == PHASE_DORMANT else "backoff_response"
    re_engaging_state = ReEngagingState(reengagement_trigger=trigger)

    parent_updates = {
        "consecutive_unanswered_count": 0,
        "current_backoff_step": 0,
        "clinician_alerted": False,
        "phase": "ACTIVE",
    }

    return {
        "response": response,
        "re_engaging_state": re_engaging_state,
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
