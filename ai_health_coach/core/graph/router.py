"""Parent router graph — consent gate + deterministic phase routing.

The LLM never decides phase transitions. All routing is pure Python.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_health_coach.core.graph.active import run_active_response, run_checkin
from ai_health_coach.core.graph.dormant import enter_dormant, handle_dormant_message
from ai_health_coach.core.graph.onboarding import run_onboarding
from ai_health_coach.core.graph.re_engaging import run_nudge, run_warm_reengagement
from ai_health_coach.core.safety.classifier import (
    CRISIS_MESSAGE,
    classify_message,
)
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_DORMANT,
    PHASE_ONBOARDING,
    PHASE_PENDING,
    PHASE_RE_ENGAGING,
    PatientState,
)
from ai_health_coach.core.tools.definitions import execute_tool


# ─── Consent Gate ───────────────────────────────────────────────────

def check_consent(state: PatientState) -> str:
    """First node, every interaction. Returns routing decision."""
    if state["has_logged_in"] and state["has_consented"]:
        return "proceed"
    elif not state["has_logged_in"] and not state["has_consented"]:
        return "never_consented"
    elif state["has_logged_in"] and not state["has_consented"]:
        return "revoked"
    else:
        # Logged in but consent unknown — treat as never consented
        return "never_consented"


NEVER_CONSENTED_MESSAGE = (
    "Welcome! To get started with your exercise coaching, "
    "please log in to MedBridge Go and opt in to coaching support."
)

REVOKED_MESSAGE = (
    "We respect your decision. If you'd like to re-enable coaching support "
    "in the future, you can do so in your MedBridge Go settings. "
    "Your progress will be right where you left it."
)


# ─── Phase Transitions (deterministic) ──────────────────────────────

def evaluate_transitions(state: PatientState) -> PatientState:
    """Apply deterministic phase transitions based on current state.

    Called before routing to ensure phase is up to date.
    """
    phase = state["phase"]

    # PENDING → ONBOARDING
    if phase == PHASE_PENDING and state["has_logged_in"] and state["has_consented"]:
        state = {**state, "phase": PHASE_ONBOARDING}

    # ONBOARDING → ACTIVE is handled by the onboarding subgraph when it completes

    # ACTIVE → RE_ENGAGING
    if phase == PHASE_ACTIVE and state["consecutive_unanswered_count"] >= 1:
        state = {**state, "phase": PHASE_RE_ENGAGING}

    # RE_ENGAGING → DORMANT
    if phase == PHASE_RE_ENGAGING and state["consecutive_unanswered_count"] >= 3:
        state = {**state, "phase": PHASE_DORMANT}

    return state


# ─── Main Router ────────────────────────────────────────────────────

def route_message(
    state: PatientState,
    patient_message: str | None = None,
    trigger_type: str | None = None,
    onboarding_state: dict | None = None,
) -> dict[str, Any]:
    """Main entry point — routes to the appropriate subgraph.

    Args:
        state: Current patient state.
        patient_message: Incoming message from patient (None for outbound triggers).
        trigger_type: CLI trigger type (e.g. 'day_2_checkin', 'backoff').
        onboarding_state: Persisted onboarding subgraph state (if in onboarding).

    Returns:
        Dict with:
            - response: str | None (message to send to patient)
            - state: updated PatientState
            - onboarding_state: updated onboarding state (if applicable)
    """
    # ─── Consent gate (every interaction) ───
    consent = check_consent(state)
    if consent == "never_consented":
        return {
            "response": NEVER_CONSENTED_MESSAGE,
            "state": state,
            "onboarding_state": onboarding_state,
        }
    if consent == "revoked":
        return {
            "response": REVOKED_MESSAGE,
            "state": state,
            "onboarding_state": onboarding_state,
        }

    # ─── Safety check on incoming patient messages ───
    if patient_message is not None:
        classification = classify_message(patient_message)
        if classification == "mental_health_crisis":
            execute_tool("alert_clinician", {
                "patient_id": state["patient_id"],
                "alert_type": "mental_health_crisis",
                "urgency": "urgent",
                "context": f"Patient message: {patient_message}",
            })
            state = _append_messages(state, patient_message, CRISIS_MESSAGE)
            state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
            return {
                "response": CRISIS_MESSAGE,
                "state": state,
                "onboarding_state": onboarding_state,
            }

    # ─── Apply deterministic transitions ───
    state = evaluate_transitions(state)
    phase = state["phase"]

    # ─── DORMANT: patient reaching out ───
    if phase == PHASE_DORMANT and patient_message is not None:
        dormant_result = handle_dormant_message(state, patient_message)
        state = _merge_updates(state, dormant_result["parent_updates"])
        # Now dispatch to re-engaging
        result = run_warm_reengagement(state, patient_message)
        state = _merge_updates(state, result["parent_updates"])
        if result["response"]:
            state = _append_messages(state, patient_message, result["response"])
            state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
        return {
            "response": result["response"],
            "state": state,
            "onboarding_state": onboarding_state,
        }

    # ─── PENDING ───
    if phase == PHASE_PENDING:
        return {
            "response": NEVER_CONSENTED_MESSAGE,
            "state": state,
            "onboarding_state": onboarding_state,
        }

    # ─── ONBOARDING ───
    if phase == PHASE_ONBOARDING:
        result = run_onboarding(state, onboarding_state, patient_message)
        state = _merge_updates(state, result["parent_updates"])
        if result["response"]:
            if patient_message:
                state = _append_messages(state, patient_message, result["response"])
            else:
                state = _append_message(state, "assistant", result["response"])
            state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
        return {
            "response": result["response"],
            "state": state,
            "onboarding_state": result["onboarding_state"],
        }

    # ─── ACTIVE ───
    if phase == PHASE_ACTIVE:
        if trigger_type is not None:
            # CLI-triggered check-in
            result = run_checkin(state, trigger_type)
            state = _merge_updates(state, result["parent_updates"])
            if result["response"]:
                state = _append_message(state, "assistant", result["response"])
                state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
            return {
                "response": result["response"],
                "state": state,
                "onboarding_state": onboarding_state,
            }
        elif patient_message is not None:
            result = run_active_response(state, patient_message)
            state = _merge_updates(state, result["parent_updates"])
            if result["response"]:
                state = _append_messages(state, patient_message, result["response"])
                state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
            return {
                "response": result["response"],
                "state": state,
                "onboarding_state": onboarding_state,
            }

    # ─── RE_ENGAGING ───
    if phase == PHASE_RE_ENGAGING:
        if patient_message is not None:
            # Patient responded during re-engagement
            result = run_warm_reengagement(state, patient_message)
            state = _merge_updates(state, result["parent_updates"])
            if result["response"]:
                state = _append_messages(state, patient_message, result["response"])
                state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
            return {
                "response": result["response"],
                "state": state,
                "onboarding_state": onboarding_state,
            }
        elif trigger_type == "backoff":
            result = run_nudge(state)
            state = _merge_updates(state, result["parent_updates"])
            if result["response"]:
                state = _append_message(state, "assistant", result["response"])
                state = {**state, "last_contact_date": datetime.now().strftime("%Y-%m-%d")}
            return {
                "response": result["response"],
                "state": state,
                "onboarding_state": onboarding_state,
            }

    # ─── DORMANT (no outbound) ───
    if phase == PHASE_DORMANT:
        enter_dormant(state)
        return {
            "response": None,
            "state": state,
            "onboarding_state": onboarding_state,
        }

    # Fallback
    return {
        "response": None,
        "state": state,
        "onboarding_state": onboarding_state,
    }


# ─── Helpers ────────────────────────────────────────────────────────

def _merge_updates(state: PatientState, updates: dict) -> PatientState:
    """Merge subgraph updates into parent state."""
    if not updates:
        return state
    return {**state, **updates}


def _append_message(state: PatientState, role: str, content: str) -> PatientState:
    """Append a single message to conversation history."""
    messages = state["messages"] + [{"role": role, "content": content}]
    return {**state, "messages": messages}


def _append_messages(
    state: PatientState, user_msg: str, assistant_msg: str
) -> PatientState:
    """Append a user message and assistant response to history."""
    messages = state["messages"] + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    return {**state, "messages": messages}
