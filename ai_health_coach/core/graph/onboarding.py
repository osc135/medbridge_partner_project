"""Onboarding subgraph — multi-turn goal-setting conversation.

Steps: WELCOMING → ELICITING → EXTRACTING → CONFIRMING → COMPLETE
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_health_coach.core.llm import get_llm, safe_generate as _safe_generate, tool_calling_generate
from ai_health_coach.core.state.schemas import (
    MAX_CONFIRMATION_ATTEMPTS,
    MAX_GOAL_NEGOTIATION_ATTEMPTS,
    PHASE_ACTIVE,
    STEP_COMPLETE,
    STEP_CONFIRMING,
    STEP_ELICITING,
    STEP_WELCOMING,
    OnboardingState,
    PatientState,
)
from ai_health_coach.core.tools.definitions import execute_tool, get_tools_for_phase

EXTRACTION_PROMPT = """Extract a structured exercise goal from the conversation so far.
Return only JSON with these fields:
- goal_type: str (e.g. "exercise", "stretching")
- frequency: str (e.g. "daily", "3x per week")
- time_of_day: str (e.g. "morning", "evening", "morning on Tuesdays, afternoon other days")

For time_of_day, if the patient described a mixed schedule (e.g. different times on
different days), combine them into a single descriptive string. Do NOT leave it null
if the patient gave any time-related information.

If a field truly cannot be determined from the conversation, set it to null.

Conversation context:
{conversation_context}

Latest patient message: {patient_message}"""


def _build_system_prompt(state: PatientState) -> str:
    exercise_details = []
    for ex in state["assigned_exercises"]:
        exercise_details.append(f"- {ex['name']}: {ex['sets']} sets x {ex['reps']} reps")
    exercises_str = "\n".join(exercise_details) or "No exercises assigned"

    return (
        "You are a warm but accountability-focused health coach helping a patient stay on track "
        "with their home exercise program. Your job is to help them commit to a goal and follow through. "
        "Be encouraging but never validate skipping. You are NOT a clinician — never give "
        "clinical advice. If the patient asks clinical questions, redirect them "
        "to their care team.\n\n"
        "IMPORTANT: You have access to the patient's real prescribed program below. When the patient "
        "asks about their exercises, sets, reps, or how many to do, ONLY reference the exact "
        "data below. These numbers were set by their care provider. "
        "NEVER guess, estimate, or suggest 'typical ranges.'\n\n"
        f"Patient name: {state['patient_name']}\n"
        f"Prescribed exercises:\n{exercises_str}\n"
    )


def run_onboarding(
    parent_state: PatientState,
    onboarding_state: OnboardingState | None = None,
    patient_message: str | None = None,
) -> dict[str, Any]:
    """Run one step of the onboarding flow.

    Returns a dict with keys:
        - response: str (message to send to patient)
        - onboarding_state: updated OnboardingState
        - parent_updates: dict of fields to merge into parent state
    """
    if onboarding_state is None:
        onboarding_state = OnboardingState(
            onboarding_step=STEP_WELCOMING,
            confirmation_attempts=0,
            goal_negotiation_attempts=0,
            goal_draft=None,
        )

    step = onboarding_state["onboarding_step"]
    system_msg = _build_system_prompt(parent_state)
    messages_history = [SystemMessage(content=system_msg)]

    # Rebuild conversation context from parent messages
    for msg in parent_state["messages"]:
        if msg["role"] == "assistant":
            messages_history.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "user":
            messages_history.append(HumanMessage(content=msg["content"]))

    parent_updates: dict[str, Any] = {}

    # --- WELCOMING ---
    if step == STEP_WELCOMING:
        messages_history.append(
            SystemMessage(
                content=(
                    "Welcome this patient by name. Mention their assigned exercises. "
                    "Then ask them an open-ended question about what exercise goal "
                    "they'd like to set for themselves. Keep it warm and brief."
                )
            )
        )
        response = _safe_generate(messages_history)
        onboarding_state = OnboardingState(
            onboarding_step=STEP_ELICITING,
            confirmation_attempts=0,
            goal_negotiation_attempts=0,
            goal_draft=None,
        )
        return {
            "response": response,
            "onboarding_state": onboarding_state,
            "parent_updates": parent_updates,
        }

    # --- ELICITING (waiting for patient response) ---
    if step == STEP_ELICITING:
        if patient_message is None:
            # Patient hasn't responded — handled by disengagement logic in router
            return {
                "response": None,
                "onboarding_state": onboarding_state,
                "parent_updates": parent_updates,
            }

        # Patient responded — move to extraction
        messages_history.append(HumanMessage(content=patient_message))

        # Extract structured goal via dedicated LLM call (with conversation context)
        llm = get_llm()
        conversation_context = "\n".join(
            f"{'Coach' if m['role'] == 'assistant' else 'Patient'}: {m['content']}"
            for m in parent_state["messages"][-6:]
        )
        extraction_response = llm.invoke(
            [SystemMessage(content=EXTRACTION_PROMPT.format(
                conversation_context=conversation_context,
                patient_message=patient_message,
            ))]
        )

        try:
            # Try to parse the JSON from the response
            content = extraction_response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            goal_draft = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            goal_draft = {"goal_type": None, "frequency": None, "time_of_day": None}

        # Merge with existing partial goal if we had one
        existing_draft = onboarding_state.get("goal_draft")
        if existing_draft:
            for key in ["goal_type", "frequency", "time_of_day"]:
                if not goal_draft.get(key) and existing_draft.get(key):
                    goal_draft[key] = existing_draft[key]

        # Check for unrealistic goals
        negotiation_attempts = onboarding_state["goal_negotiation_attempts"]
        if _is_unrealistic_goal(goal_draft) and negotiation_attempts < MAX_GOAL_NEGOTIATION_ATTEMPTS:
            messages_history.append(
                SystemMessage(
                    content=(
                        "The patient's goal seems unrealistic or too ambitious. "
                        "Gently suggest a smaller, more achievable goal. "
                        "Be encouraging, not dismissive."
                    )
                )
            )
            response = _safe_generate(messages_history)
            onboarding_state = OnboardingState(
                onboarding_step=STEP_ELICITING,
                confirmation_attempts=0,
                goal_negotiation_attempts=negotiation_attempts + 1,
                goal_draft=None,
            )
            return {
                "response": response,
                "onboarding_state": onboarding_state,
                "parent_updates": parent_updates,
            }

        # Check for missing fields — ask follow-up before confirming
        # But don't loop forever: after a few rounds, accept what we have
        eliciting_rounds = onboarding_state["goal_negotiation_attempts"]
        missing = []
        if not goal_draft.get("frequency"):
            missing.append("how often (e.g. daily, 3x per week)")
        if not goal_draft.get("time_of_day"):
            missing.append("what time of day (morning, afternoon, or evening)")

        if missing and eliciting_rounds < 2:
            # Save what we have so far and ask for the rest
            onboarding_state = OnboardingState(
                onboarding_step=STEP_ELICITING,
                confirmation_attempts=0,
                goal_negotiation_attempts=onboarding_state["goal_negotiation_attempts"],
                goal_draft=goal_draft,  # Preserve partial goal
            )
            missing_str = " and ".join(missing)
            messages_history.append(
                SystemMessage(
                    content=(
                        f"The patient gave a partial goal but didn't specify {missing_str}. "
                        "Ask them a brief, friendly follow-up question to fill in the missing details. "
                        "Don't repeat what they already told you."
                    )
                )
            )
            response = _safe_generate(messages_history)
            return {
                "response": response,
                "onboarding_state": onboarding_state,
                "parent_updates": parent_updates,
            }

        # Fill in defaults for any remaining missing fields
        if not goal_draft.get("goal_type"):
            exercise_names = [ex["name"] for ex in parent_state["assigned_exercises"]]
            goal_draft["goal_type"] = ", ".join(exercise_names) if exercise_names else "exercise"
        if not goal_draft.get("frequency"):
            goal_draft["frequency"] = "daily"
        if not goal_draft.get("time_of_day"):
            goal_draft["time_of_day"] = "morning"

        # Goal looks good — move to confirmation
        onboarding_state = OnboardingState(
            onboarding_step=STEP_CONFIRMING,
            confirmation_attempts=0,
            goal_negotiation_attempts=onboarding_state["goal_negotiation_attempts"],
            goal_draft=goal_draft,
        )

        # Present structured goal back to patient
        goal_desc = _format_goal(goal_draft)
        messages_history.append(
            SystemMessage(
                content=(
                    f"Present this goal back to the patient for confirmation: {goal_desc}. "
                    "Ask them to confirm with a simple yes or no. "
                    "Be warm and encouraging about their choice."
                )
            )
        )
        response = _safe_generate(messages_history)
        return {
            "response": response,
            "onboarding_state": onboarding_state,
            "parent_updates": parent_updates,
        }

    # --- CONFIRMING ---
    if step == STEP_CONFIRMING:
        if patient_message is None:
            return {
                "response": None,
                "onboarding_state": onboarding_state,
                "parent_updates": parent_updates,
            }

        messages_history.append(HumanMessage(content=patient_message))
        confirmation_attempts = onboarding_state["confirmation_attempts"] + 1

        if _is_confirmation(patient_message):
            # Patient confirmed — let the LLM autonomously call tools
            goal = onboarding_state["goal_draft"]

            start = datetime.strptime(parent_state["program_start_date"], "%Y-%m-%d")
            day_2 = (start + timedelta(days=2)).strftime("%Y-%m-%d")
            day_5 = (start + timedelta(days=5)).strftime("%Y-%m-%d")
            day_7 = (start + timedelta(days=7)).strftime("%Y-%m-%d")

            pid = parent_state["patient_id"]
            goal_desc = _format_goal(goal)
            messages_history.append(
                SystemMessage(
                    content=(
                        f"The patient confirmed their goal: {goal_desc}. "
                        f"You MUST now:\n"
                        f"1. Call set_goal with patient_id='{pid}', "
                        f"goal_type='{goal.get('goal_type') or 'exercise'}', "
                        f"frequency='{goal.get('frequency') or 'daily'}', "
                        f"time_of_day='{goal.get('time_of_day') or 'morning'}'\n"
                        f"2. Call set_reminder with patient_id='{pid}', "
                        f"scheduled_for='{day_2}', interaction_type='day_2_checkin'\n"
                        f"3. Call set_reminder with patient_id='{pid}', "
                        f"scheduled_for='{day_5}', interaction_type='day_5_checkin'\n"
                        f"4. Call set_reminder with patient_id='{pid}', "
                        f"scheduled_for='{day_7}', interaction_type='day_7_checkin'\n"
                        f"5. After all tools succeed, celebrate this moment with the patient. "
                        f"Let them know you'll check in with them over the coming days. "
                        f"Keep it brief and encouraging."
                    )
                )
            )

            tools = get_tools_for_phase("ONBOARDING")
            result = tool_calling_generate(messages_history, tools)

            # Verify set_goal was actually called
            goal_saved = any(
                tc["name"] == "set_goal" and tc["result"].get("success")
                for tc in result["tool_calls_made"]
            )

            if not goal_saved:
                # LLM didn't call set_goal — fall back to direct calls
                execute_tool("set_goal", {
                    "patient_id": pid,
                    "goal_type": goal.get("goal_type") or "exercise",
                    "frequency": goal.get("frequency") or "daily",
                    "time_of_day": goal.get("time_of_day") or "morning",
                })

            # Ensure all 3 reminders are scheduled (fallback for any the LLM missed)
            scheduled = {tc["args"].get("interaction_type") for tc in result["tool_calls_made"] if tc["name"] == "set_reminder"}
            for day_date, day_type in [(day_2, "day_2_checkin"), (day_5, "day_5_checkin"), (day_7, "day_7_checkin")]:
                if day_type not in scheduled:
                    execute_tool("set_reminder", {
                        "patient_id": pid,
                        "scheduled_for": day_date,
                        "interaction_type": day_type,
                    })

            onboarding_state = OnboardingState(
                onboarding_step=STEP_COMPLETE,
                confirmation_attempts=confirmation_attempts,
                goal_negotiation_attempts=onboarding_state["goal_negotiation_attempts"],
                goal_draft=goal,
            )

            parent_updates["goal"] = goal
            parent_updates["phase"] = PHASE_ACTIVE

            return {
                "response": result["message"],
                "onboarding_state": onboarding_state,
                "parent_updates": parent_updates,
            }

        elif _is_rejection(patient_message):
            if confirmation_attempts >= MAX_CONFIRMATION_ATTEMPTS:
                # Patient refuses to commit — let LLM call alert_clinician
                messages_history.append(
                    SystemMessage(
                        content=(
                            "The patient doesn't want to commit to a goal after multiple attempts. "
                            f"You MUST call alert_clinician with patient_id='{parent_state['patient_id']}', "
                            f"alert_type='disengagement', urgency='routine', "
                            f"context='Patient refused to commit to a goal after multiple attempts during onboarding.'\n"
                            "After calling the tool, respond to the patient: be understanding, "
                            "let them know their care team will follow up, and they can set a "
                            "goal whenever they're ready."
                        )
                    )
                )
                tools = get_tools_for_phase("ONBOARDING")
                result = tool_calling_generate(messages_history, tools)

                # Verify alert was sent — fall back if LLM didn't call it
                alert_sent = any(
                    tc["name"] == "alert_clinician" and tc["result"].get("success")
                    for tc in result["tool_calls_made"]
                )
                if not alert_sent:
                    execute_tool("alert_clinician", {
                        "patient_id": parent_state["patient_id"],
                        "alert_type": "disengagement",
                        "urgency": "routine",
                        "context": "Patient refused to commit to a goal after multiple attempts during onboarding.",
                    })

                return {
                    "response": result["message"],
                    "onboarding_state": onboarding_state,
                    "parent_updates": parent_updates,
                }
            else:
                # Go back to eliciting
                onboarding_state = OnboardingState(
                    onboarding_step=STEP_ELICITING,
                    confirmation_attempts=confirmation_attempts,
                    goal_negotiation_attempts=onboarding_state["goal_negotiation_attempts"],
                    goal_draft=None,
                )
                messages_history.append(
                    SystemMessage(
                        content=(
                            "The patient didn't confirm the goal. Ask what they'd like to "
                            "change or if they have a different goal in mind. Stay encouraging."
                        )
                    )
                )
                response = _safe_generate(messages_history)
                return {
                    "response": response,
                    "onboarding_state": onboarding_state,
                    "parent_updates": parent_updates,
                }
        else:
            # Patient asked a question or gave an ambiguous response.
            # Answer their question using program data, then steer back to confirmation.
            exercises = ", ".join(
                f"{ex['name']} ({ex['sets']} sets x {ex['reps']} reps)"
                for ex in parent_state["assigned_exercises"]
            )
            onboarding_state = OnboardingState(
                onboarding_step=STEP_CONFIRMING,
                confirmation_attempts=confirmation_attempts,
                goal_negotiation_attempts=onboarding_state["goal_negotiation_attempts"],
                goal_draft=onboarding_state["goal_draft"],
            )
            goal_desc = _format_goal(onboarding_state["goal_draft"])
            messages_history.append(
                SystemMessage(
                    content=(
                        f"The patient asked a question or gave an unclear response instead of confirming. "
                        f"Their assigned exercises are: {exercises}. "
                        f"Their proposed goal is: {goal_desc}. "
                        "Answer their question helpfully using their program details (exercises, sets, reps). "
                        "This is NOT clinical advice — you are just referencing what their clinician assigned. "
                        "After answering, gently steer back to confirming their goal."
                    )
                )
            )
            response = _safe_generate(messages_history)
            return {
                "response": response,
                "onboarding_state": onboarding_state,
                "parent_updates": parent_updates,
            }

    # Fallback — shouldn't reach here
    return {
        "response": None,
        "onboarding_state": onboarding_state,
        "parent_updates": parent_updates,
    }


def _is_unrealistic_goal(goal: dict) -> bool:
    """Heuristic check for unrealistic goals."""
    freq = (goal.get("frequency") or "").lower()
    unrealistic_markers = ["5x", "6x", "7x", "twice a day", "three times a day", "every hour"]
    return any(marker in freq for marker in unrealistic_markers)


def _is_confirmation(message: str) -> bool:
    """Check if the patient's message is a confirmation."""
    positive = ["yes", "yeah", "yep", "sure", "sounds good", "that's right", "correct", "confirmed", "let's do it", "absolutely", "perfect"]
    msg_lower = message.lower().strip()
    return any(word in msg_lower for word in positive)


def _is_rejection(message: str) -> bool:
    """Check if the patient's message is a rejection."""
    negative = ["no", "nah", "nope", "not really", "don't want", "change", "different", "wrong"]
    msg_lower = message.lower().strip()
    return any(word in msg_lower for word in negative)


def _format_goal(goal: dict) -> str:
    """Format a goal dict into a readable string."""
    parts = []
    if goal.get("goal_type"):
        parts.append(goal["goal_type"])
    if goal.get("frequency"):
        parts.append(goal["frequency"])
    if goal.get("time_of_day"):
        parts.append(f"in the {goal['time_of_day']}")
    return " ".join(parts) if parts else "an exercise goal"
