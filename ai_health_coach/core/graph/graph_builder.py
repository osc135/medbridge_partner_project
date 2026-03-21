"""LangGraph state graph — wires existing subgraph functions into a
compiled StateGraph with deterministic conditional edges.

The graph structure:

    START
      |
    [consent_gate]
      |  proceed / never_consented / revoked
      v
    [safety_check]  (skipped when no patient message)
      |  safe / mental_health_crisis
      v
    [evaluate_transitions]
      |  deterministic phase routing
      v
    [phase node]  -->  END
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ai_health_coach.core.graph.active import run_active_response, run_checkin
from ai_health_coach.core.graph.dormant import enter_dormant, handle_dormant_message
from ai_health_coach.core.graph.onboarding import run_onboarding
from ai_health_coach.core.graph.re_engaging import run_nudge, run_warm_reengagement
from ai_health_coach.core.safety.classifier import CRISIS_MESSAGE, classify_message
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_DORMANT,
    PHASE_ONBOARDING,
    PHASE_PENDING,
    PHASE_RE_ENGAGING,
    GraphState,
)
from ai_health_coach.core.simulation import get_current_date
from ai_health_coach.core.tools.definitions import execute_tool


# ─── Helpers (carried over from router.py) ─────────────────────────


def _merge_updates(state: dict, updates: dict) -> dict:
    if not updates:
        return state
    return {**state, **updates}


def _append_message(state: dict, role: str, content: str) -> dict:
    messages = state["messages"] + [{"role": role, "content": content}]
    return {**state, "messages": messages}


def _append_messages(state: dict, user_msg: str, assistant_msg: str) -> dict:
    messages = state["messages"] + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    return {**state, "messages": messages}


def _stamp_contact(patient_state: dict) -> dict:
    return {**patient_state, "last_contact_date": get_current_date()}


# ─── Node functions ────────────────────────────────────────────────
# Each takes GraphState and returns a partial GraphState update dict.


NEVER_CONSENTED_MESSAGE = (
    "Welcome! To get started with your exercise coaching, "
    "please log in to MedBridge Go and opt in to coaching support."
)

REVOKED_MESSAGE = (
    "We respect your decision. If you'd like to re-enable coaching support "
    "in the future, you can do so in your MedBridge Go settings. "
    "Your progress will be right where you left it."
)


def consent_gate_node(state: GraphState) -> dict:
    """Check consent and store the routing decision."""
    ps = state["patient_state"]
    if ps["has_logged_in"] and ps["has_consented"]:
        result = "proceed"
    elif ps["has_logged_in"] and not ps["has_consented"]:
        result = "revoked"
    else:
        result = "never_consented"
    print(f"  \033[96m◆ CONSENT GATE: {result}\033[0m")
    return {"consent_result": result}


def consent_denied_node(state: GraphState) -> dict:
    """Return the appropriate denial message."""
    if state["consent_result"] == "revoked":
        msg = REVOKED_MESSAGE
    else:
        msg = NEVER_CONSENTED_MESSAGE
    return {
        "response": msg,
        "updated_patient_state": state["patient_state"],
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def safety_check_node(state: GraphState) -> dict:
    """Classify incoming patient message for safety concerns."""
    patient_message = state.get("patient_message")
    if patient_message is None:
        return {"safety_result": "safe"}
    classification = classify_message(patient_message)
    return {"safety_result": classification}


def crisis_response_node(state: GraphState) -> dict:
    """Alert clinician and return crisis message."""
    ps = state["patient_state"]
    patient_message = state["patient_message"]

    execute_tool("alert_clinician", {
        "patient_id": ps["patient_id"],
        "alert_type": "mental_health_crisis",
        "urgency": "urgent",
        "context": f"Patient message: {patient_message}",
    })

    updated = _append_messages(ps, patient_message, CRISIS_MESSAGE)
    updated = _stamp_contact(updated)

    return {
        "response": CRISIS_MESSAGE,
        "updated_patient_state": updated,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def evaluate_transitions_node(state: GraphState) -> dict:
    """Apply deterministic phase transitions."""
    ps = state["patient_state"]
    phase = ps["phase"]

    if phase == PHASE_PENDING and ps["has_logged_in"] and ps["has_consented"]:
        print(f"  \033[95m⇒ PHASE: PENDING → ONBOARDING\033[0m")
        ps = {**ps, "phase": PHASE_ONBOARDING}

    if phase == PHASE_ACTIVE and ps["consecutive_unanswered_count"] >= 1:
        print(f"  \033[95m⇒ PHASE: ACTIVE → RE_ENGAGING (unanswered: {ps['consecutive_unanswered_count']})\033[0m")
        ps = {**ps, "phase": PHASE_RE_ENGAGING}

    if phase == PHASE_RE_ENGAGING and ps["consecutive_unanswered_count"] >= 3:
        print(f"  \033[95m⇒ PHASE: RE_ENGAGING → DORMANT (unanswered: {ps['consecutive_unanswered_count']})\033[0m")
        ps = {**ps, "phase": PHASE_DORMANT}

    print(f"  \033[96m◆ ROUTING: phase={ps['phase']}\033[0m")
    return {
        "patient_state": ps,
        "phase": ps["phase"],
    }


# ─── Phase-specific nodes ─────────────────────────────────────────


def pending_node(state: GraphState) -> dict:
    return {
        "response": NEVER_CONSENTED_MESSAGE,
        "updated_patient_state": state["patient_state"],
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def onboarding_node(state: GraphState) -> dict:
    ps = state["patient_state"]
    patient_message = state.get("patient_message")
    ob_state = state.get("onboarding_state")

    result = run_onboarding(ps, ob_state, patient_message)
    ps = _merge_updates(ps, result["parent_updates"])

    if result["response"]:
        if patient_message:
            ps = _append_messages(ps, patient_message, result["response"])
        else:
            ps = _append_message(ps, "assistant", result["response"])
        ps = _stamp_contact(ps)

    return {
        "response": result["response"],
        "updated_patient_state": ps,
        "updated_onboarding_state": result["onboarding_state"],
    }


def active_checkin_node(state: GraphState) -> dict:
    ps = state["patient_state"]
    trigger_type = state["trigger_type"]

    result = run_checkin(ps, trigger_type)
    ps = _merge_updates(ps, result["parent_updates"])

    if result["response"]:
        ps = _append_message(ps, "assistant", result["response"])
        ps = _stamp_contact(ps)

    return {
        "response": result["response"],
        "updated_patient_state": ps,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def post_checkin_transition_node(state: GraphState) -> dict:
    """Re-evaluate transitions after check-in updated unanswered count."""
    ps = state["updated_patient_state"]
    phase = ps["phase"]

    if phase == PHASE_ACTIVE and ps["consecutive_unanswered_count"] >= 1:
        print(f"  \033[95m⇒ PHASE: ACTIVE → RE_ENGAGING (unanswered: {ps['consecutive_unanswered_count']})\033[0m")
        ps = {**ps, "phase": PHASE_RE_ENGAGING}

    return {"updated_patient_state": ps}


def active_response_node(state: GraphState) -> dict:
    ps = state["patient_state"]
    patient_message = state["patient_message"]

    result = run_active_response(ps, patient_message)
    ps = _merge_updates(ps, result["parent_updates"])

    if result["response"]:
        ps = _append_messages(ps, patient_message, result["response"])
        ps = _stamp_contact(ps)

    return {
        "response": result["response"],
        "updated_patient_state": ps,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def warm_reengagement_node(state: GraphState) -> dict:
    ps = state.get("updated_patient_state", state["patient_state"])
    patient_message = state["patient_message"]

    result = run_warm_reengagement(ps, patient_message)
    ps = _merge_updates(ps, result["parent_updates"])

    if result["response"]:
        ps = _append_messages(ps, patient_message, result["response"])
        ps = _stamp_contact(ps)

    return {
        "response": result["response"],
        "updated_patient_state": ps,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def nudge_node(state: GraphState) -> dict:
    ps = state["patient_state"]
    trigger_type = state.get("trigger_type")

    result = run_nudge(ps)
    ps = _merge_updates(ps, result["parent_updates"])

    # Record trigger so it greys out in the UI
    if trigger_type and trigger_type not in ps.get("completed_checkins", []):
        ps = {**ps, "completed_checkins": ps["completed_checkins"] + [trigger_type]}

    if result["response"]:
        ps = _append_message(ps, "assistant", result["response"])
        ps = _stamp_contact(ps)

    return {
        "response": result["response"],
        "updated_patient_state": ps,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def post_nudge_transition_node(state: GraphState) -> dict:
    """Re-evaluate transitions after nudge updated unanswered count."""
    ps = state["updated_patient_state"]
    phase = ps["phase"]

    if phase == PHASE_RE_ENGAGING and ps["consecutive_unanswered_count"] >= 3:
        print(f"  \033[95m⇒ PHASE: RE_ENGAGING → DORMANT (unanswered: {ps['consecutive_unanswered_count']})\033[0m")
        ps = {**ps, "phase": PHASE_DORMANT}

    return {"updated_patient_state": ps}


def dormant_reactivate_node(state: GraphState) -> dict:
    """Patient reached out while dormant — transition to RE_ENGAGING."""
    ps = state["patient_state"]
    patient_message = state["patient_message"]

    result = handle_dormant_message(ps, patient_message)
    ps = _merge_updates(ps, result["parent_updates"])

    return {
        "updated_patient_state": ps,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


def dormant_silent_node(state: GraphState) -> dict:
    """Dormant patient, no outbound message."""
    ps = state["patient_state"]
    trigger_type = state.get("trigger_type")

    enter_dormant(ps)

    if trigger_type and trigger_type not in ps.get("completed_checkins", []):
        ps = {**ps, "completed_checkins": ps["completed_checkins"] + [trigger_type]}

    return {
        "response": None,
        "updated_patient_state": ps,
        "updated_onboarding_state": state.get("onboarding_state"),
    }


# ─── Conditional edge functions (deterministic) ───────────────────


def route_after_consent(state: GraphState) -> str:
    if state["consent_result"] == "proceed":
        return "safety_check"
    return "consent_denied"


def route_after_safety(state: GraphState) -> str:
    if state["safety_result"] == "mental_health_crisis":
        return "crisis_response"
    return "evaluate_transitions"


def route_after_phase(state: GraphState) -> str:
    phase = state["phase"]
    has_message = state.get("patient_message") is not None
    has_trigger = state.get("trigger_type") is not None

    # DORMANT + patient message → reactivation chain
    if phase == PHASE_DORMANT and has_message:
        return "dormant_reactivate"

    if phase == PHASE_PENDING:
        return "pending_response"

    if phase == PHASE_ONBOARDING:
        return "onboarding_node"

    if phase == PHASE_ACTIVE:
        if has_trigger:
            return "active_checkin"
        if has_message:
            return "active_response"

    if phase == PHASE_RE_ENGAGING:
        if has_message:
            return "warm_reengagement"
        if has_trigger:
            return "nudge_node"

    if phase == PHASE_DORMANT:
        return "dormant_silent"

    return "dormant_silent"  # Fallback


# ─── Graph construction ───────────────────────────────────────────


def build_graph() -> Any:
    """Build and compile the health coach routing graph."""
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("consent_gate", consent_gate_node)
    graph.add_node("consent_denied", consent_denied_node)
    graph.add_node("safety_check", safety_check_node)
    graph.add_node("crisis_response", crisis_response_node)
    graph.add_node("evaluate_transitions", evaluate_transitions_node)
    graph.add_node("pending_response", pending_node)
    graph.add_node("onboarding_node", onboarding_node)
    graph.add_node("active_checkin", active_checkin_node)
    graph.add_node("post_checkin_transition", post_checkin_transition_node)
    graph.add_node("active_response", active_response_node)
    graph.add_node("warm_reengagement", warm_reengagement_node)
    graph.add_node("nudge_node", nudge_node)
    graph.add_node("post_nudge_transition", post_nudge_transition_node)
    graph.add_node("dormant_reactivate", dormant_reactivate_node)
    graph.add_node("dormant_silent", dormant_silent_node)

    # Entry point
    graph.set_entry_point("consent_gate")

    # Conditional edges
    graph.add_conditional_edges("consent_gate", route_after_consent, {
        "safety_check": "safety_check",
        "consent_denied": "consent_denied",
    })
    graph.add_conditional_edges("safety_check", route_after_safety, {
        "crisis_response": "crisis_response",
        "evaluate_transitions": "evaluate_transitions",
    })
    graph.add_conditional_edges("evaluate_transitions", route_after_phase, {
        "dormant_reactivate": "dormant_reactivate",
        "pending_response": "pending_response",
        "onboarding_node": "onboarding_node",
        "active_checkin": "active_checkin",
        "active_response": "active_response",
        "warm_reengagement": "warm_reengagement",
        "nudge_node": "nudge_node",
        "dormant_silent": "dormant_silent",
    })

    # Sequential edges
    graph.add_edge("consent_denied", END)
    graph.add_edge("crisis_response", END)
    graph.add_edge("pending_response", END)
    graph.add_edge("onboarding_node", END)
    graph.add_edge("active_checkin", "post_checkin_transition")
    graph.add_edge("post_checkin_transition", END)
    graph.add_edge("active_response", END)
    graph.add_edge("warm_reengagement", END)
    graph.add_edge("nudge_node", "post_nudge_transition")
    graph.add_edge("post_nudge_transition", END)
    graph.add_edge("dormant_reactivate", "warm_reengagement")
    graph.add_edge("dormant_silent", END)

    return graph.compile()
