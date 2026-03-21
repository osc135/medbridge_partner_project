from __future__ import annotations

from typing import Optional, TypedDict


class PatientState(TypedDict):
    """Parent state — persists across the entire patient relationship."""

    # Patient identity
    patient_id: str
    patient_name: str

    # Consent & access (checked every interaction)
    has_logged_in: bool
    has_consented: bool

    # Phase routing
    phase: str  # PENDING | ONBOARDING | ACTIVE | RE_ENGAGING | DORMANT

    # Goal (structured, confirmed — never a draft)
    goal: dict | None

    # Exercises — each: {"name": str, "sets": int, "reps": int}
    assigned_exercises: list[dict]

    # Scheduling
    program_start_date: str
    last_contact_date: str | None
    completed_checkins: list[str]
    reminders: list[dict]

    # Disengagement
    consecutive_unanswered_count: int
    current_backoff_step: int
    clinician_alerted: bool
    failed_alerts: list[dict]

    # Adherence tracking — each: {"date": str, "completed": bool, "source": str}
    exercise_log: list[dict]

    # Conversation history
    messages: list[dict]


class OnboardingState(TypedDict):
    """Private state for the onboarding subgraph."""

    onboarding_step: str  # WELCOMING | ELICITING | EXTRACTING | CONFIRMING | COMPLETE
    confirmation_attempts: int
    goal_negotiation_attempts: int
    goal_draft: dict | None


class ActiveState(TypedDict):
    """Private state for the active subgraph."""

    current_checkin: str  # "day_2" | "day_5" | "day_7"
    interaction_tone: str  # "celebration" | "nudge" | "checkin" | "encouragement"


class ReEngagingState(TypedDict):
    """Private state for the re-engaging subgraph."""

    reengagement_trigger: str  # "missed_checkin" | "returning_from_dormant" | "backoff_response"


class DormantState(TypedDict):
    """Private state for the dormant subgraph."""

    dormant_since: str
    reactivation_message: str | None


class SafetyCheckState(TypedDict):
    """Tracks safety classification for a single message."""

    original_message: str
    flagged: bool
    flag_reason: str | None  # "clinical" | "mental_health_crisis" | None
    retry_count: int
    final_message: str


class GraphState(TypedDict, total=False):
    """Ephemeral state for a single LangGraph invocation.

    Not persisted — exists only during graph execution. Uses total=False
    so fields can be omitted when constructing partial updates from nodes.
    """

    # Inputs (set before graph invocation)
    patient_state: PatientState
    patient_message: Optional[str]
    trigger_type: Optional[str]
    onboarding_state: Optional[dict]

    # Outputs (populated by nodes)
    response: Optional[str]
    updated_patient_state: PatientState
    updated_onboarding_state: Optional[dict]

    # Internal routing (used by conditional edges)
    consent_result: str
    safety_result: str
    phase: str


# Phase constants
PHASE_PENDING = "PENDING"
PHASE_ONBOARDING = "ONBOARDING"
PHASE_ACTIVE = "ACTIVE"
PHASE_RE_ENGAGING = "RE_ENGAGING"
PHASE_DORMANT = "DORMANT"

# Onboarding step constants
STEP_WELCOMING = "WELCOMING"
STEP_ELICITING = "ELICITING"
STEP_EXTRACTING = "EXTRACTING"
STEP_CONFIRMING = "CONFIRMING"
STEP_COMPLETE = "COMPLETE"

# Backoff schedule: step -> days to wait
BACKOFF_SCHEDULE = {
    1: 1,
    2: 2,
    3: 3,
}

MAX_CONFIRMATION_ATTEMPTS = 3
MAX_GOAL_NEGOTIATION_ATTEMPTS = 3


def create_initial_state(
    patient_id: str,
    patient_name: str,
    assigned_exercises: list[dict],
    program_start_date: str,
    has_logged_in: bool = False,
    has_consented: bool = False,
) -> PatientState:
    """Create the initial state for a new patient."""
    return PatientState(
        patient_id=patient_id,
        patient_name=patient_name,
        has_logged_in=has_logged_in,
        has_consented=has_consented,
        phase=PHASE_PENDING,
        goal=None,
        assigned_exercises=assigned_exercises,
        program_start_date=program_start_date,
        last_contact_date=None,
        completed_checkins=[],
        reminders=[],
        consecutive_unanswered_count=0,
        current_backoff_step=0,
        clinician_alerted=False,
        failed_alerts=[],
        exercise_log=[],
        messages=[],
    )
