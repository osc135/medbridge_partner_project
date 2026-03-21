"""Parent router — thin wrapper that invokes the LangGraph state graph.

The LLM never decides phase transitions. All routing is deterministic
and defined via conditional edges in graph_builder.py.
"""

from __future__ import annotations

from typing import Any

from ai_health_coach.core.graph.graph_builder import (
    NEVER_CONSENTED_MESSAGE,
    REVOKED_MESSAGE,
    build_graph,
)
from ai_health_coach.core.state.schemas import (
    PHASE_ACTIVE,
    PHASE_DORMANT,
    PHASE_ONBOARDING,
    PHASE_PENDING,
    PHASE_RE_ENGAGING,
    PatientState,
)

# Re-export constants so existing imports in tests/cli still work
__all__ = [
    "NEVER_CONSENTED_MESSAGE",
    "REVOKED_MESSAGE",
    "check_consent",
    "evaluate_transitions",
    "route_message",
]

# ─── Lazy-compiled graph singleton ─────────────────────────────────

_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


# ─── Consent Gate (kept for direct test imports) ───────────────────

def check_consent(state: PatientState) -> str:
    """First node, every interaction. Returns routing decision."""
    if state["has_logged_in"] and state["has_consented"]:
        return "proceed"
    elif not state["has_logged_in"] and not state["has_consented"]:
        return "never_consented"
    elif state["has_logged_in"] and not state["has_consented"]:
        return "revoked"
    else:
        # Not logged in but has consent flag — treat as never consented
        return "never_consented"


# ─── Phase Transitions (kept for direct test imports) ──────────────

def evaluate_transitions(state: PatientState) -> PatientState:
    """Apply deterministic phase transitions based on current state."""
    phase = state["phase"]

    if phase == PHASE_PENDING and state["has_logged_in"] and state["has_consented"]:
        state = {**state, "phase": PHASE_ONBOARDING}

    if phase == PHASE_ACTIVE and state["consecutive_unanswered_count"] >= 1:
        state = {**state, "phase": PHASE_RE_ENGAGING}

    if phase == PHASE_RE_ENGAGING and state["consecutive_unanswered_count"] >= 3:
        state = {**state, "phase": PHASE_DORMANT}

    return state


# ─── Main entry point ─────────────────────────────────────────────

def route_message(
    state: PatientState,
    patient_message: str | None = None,
    trigger_type: str | None = None,
    onboarding_state: dict | None = None,
) -> dict[str, Any]:
    """Main entry point — invokes the LangGraph state graph.

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
    graph = _get_graph()

    graph_input = {
        "patient_state": state,
        "patient_message": patient_message,
        "trigger_type": trigger_type,
        "onboarding_state": onboarding_state,
        "response": None,
        "updated_patient_state": state,
        "updated_onboarding_state": onboarding_state,
        "consent_result": "",
        "safety_result": "",
        "phase": state["phase"],
    }

    result = graph.invoke(graph_input)

    return {
        "response": result.get("response"),
        "state": result.get("updated_patient_state", state),
        "onboarding_state": result.get("updated_onboarding_state", onboarding_state),
    }
