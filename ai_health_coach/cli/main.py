"""CLI interface — thin wrapper around core logic.

Commands:
    python -m ai_health_coach.cli.main new       -- Create a new patient
    python -m ai_health_coach.cli.main chat       -- Interactive conversation
    python -m ai_health_coach.cli.main trigger    -- Fire a scheduled check-in
    python -m ai_health_coach.cli.main patients   -- List all patients
    python -m ai_health_coach.cli.main reset      -- Delete a patient
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from ai_health_coach.core.graph.router import route_message
from ai_health_coach.core.persistence import (
    delete_patient,
    list_patients,
    load_onboarding_state,
    load_state,
    save_onboarding_state,
    save_state,
)
from ai_health_coach.core.state.schemas import (
    PHASE_ONBOARDING,
    create_initial_state,
)


def cmd_new(args: argparse.Namespace) -> None:
    """Create a new patient and start onboarding."""
    patient_id = args.patient_id
    name = args.name
    # Parse "Name:sets:reps,Name:sets:reps" format
    exercises = []
    for entry in args.exercises.split(","):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) == 3:
            exercises.append({"name": parts[0], "sets": int(parts[1]), "reps": int(parts[2])})
        else:
            exercises.append({"name": parts[0], "sets": 3, "reps": 10})
    start_date = args.start_date or datetime.now().strftime("%Y-%m-%d")

    state = create_initial_state(
        patient_id=patient_id,
        patient_name=name,
        assigned_exercises=exercises,
        program_start_date=start_date,
        has_logged_in=not args.no_consent,
        has_consented=not args.no_consent,
    )
    save_state(state)

    # Run initial onboarding (welcome message)
    result = route_message(state, patient_message=None)
    state = result["state"]
    save_state(state)
    if result.get("onboarding_state"):
        save_onboarding_state(patient_id, result["onboarding_state"])

    if result["response"]:
        print(f"\nCoach: {result['response']}\n")


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive chat loop with a patient."""
    patient_id = args.patient_id
    state = load_state(patient_id)
    if state is None:
        print(f"Patient {patient_id} not found. Use 'new' to create one.")
        return

    print(f"\nChatting as {state['patient_name']} (phase: {state['phase']})")
    print("Type 'quit' to exit.\n")

    # Show last few messages for context
    for msg in state["messages"][-4:]:
        role = "Coach" if msg["role"] == "assistant" else "You"
        print(f"{role}: {msg['content']}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        onboarding_state = None
        if state["phase"] == PHASE_ONBOARDING:
            onboarding_state = load_onboarding_state(patient_id)

        result = route_message(
            state,
            patient_message=user_input,
            onboarding_state=onboarding_state,
        )

        state = result["state"]
        save_state(state)
        if result.get("onboarding_state"):
            save_onboarding_state(patient_id, result["onboarding_state"])

        if result["response"]:
            print(f"\nCoach: {result['response']}\n")
        else:
            print("\n(No response generated)\n")


def cmd_trigger(args: argparse.Namespace) -> None:
    """Fire a scheduled check-in trigger."""
    patient_id = args.patient_id
    trigger_type = args.type

    state = load_state(patient_id)
    if state is None:
        print(f"Patient {patient_id} not found.")
        return

    # Sanity checks
    if trigger_type in state.get("completed_checkins", []):
        print(f"Check-in {trigger_type} already completed for {patient_id}.")
        return

    if trigger_type != "backoff" and not _is_due(trigger_type, state["program_start_date"]):
        print(f"Check-in {trigger_type} is not yet due for {patient_id}.")
        return

    onboarding_state = load_onboarding_state(patient_id)
    result = route_message(
        state,
        trigger_type=trigger_type,
        onboarding_state=onboarding_state,
    )

    state = result["state"]
    save_state(state)

    if result["response"]:
        print(f"\nCoach: {result['response']}\n")
    else:
        print(f"\n(No message sent — patient may be dormant)\n")


def cmd_patients(_args: argparse.Namespace) -> None:
    """List all patients."""
    patients = list_patients()
    if not patients:
        print("No patients found.")
        return

    print(f"\n{'ID':<12} {'Name':<20} {'Phase':<15}")
    print("-" * 47)
    for p in patients:
        print(f"{p['patient_id']:<12} {p['patient_name']:<20} {p['phase']:<15}")
    print()


def cmd_consent(args: argparse.Namespace) -> None:
    """Grant or revoke consent for a patient."""
    state = load_state(args.patient_id)
    if state is None:
        print(f"Patient {args.patient_id} not found.")
        return

    if args.revoke:
        state = {**state, "has_consented": False}
        save_state(state)
        print(f"Consent revoked for {state['patient_name']}. Phase preserved at {state['phase']}.")
    else:
        state = {**state, "has_logged_in": True, "has_consented": True}
        save_state(state)
        print(f"Consent granted for {state['patient_name']}. Phase: {state['phase']}.")

        # If still PENDING, kick off onboarding
        result = route_message(state, patient_message=None)
        state = result["state"]
        save_state(state)
        if result.get("onboarding_state"):
            save_onboarding_state(args.patient_id, result["onboarding_state"])
        if result["response"]:
            print(f"\nCoach: {result['response']}\n")


def cmd_reset(args: argparse.Namespace) -> None:
    """Delete a patient's state."""
    if delete_patient(args.patient_id):
        print(f"Patient {args.patient_id} deleted.")
    else:
        print(f"Patient {args.patient_id} not found.")


def _is_due(trigger_type: str, program_start_date: str) -> bool:
    """Check if a check-in is due based on program start date."""
    day_map = {"day_2_checkin": 2, "day_5_checkin": 5, "day_7_checkin": 7}
    days = day_map.get(trigger_type)
    if days is None:
        return True  # Unknown trigger type — allow it

    start = datetime.strptime(program_start_date, "%Y-%m-%d")
    now = datetime.now()
    return (now - start).days >= days


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Health Coach CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # new
    new_parser = subparsers.add_parser("new", help="Create a new patient")
    new_parser.add_argument("--patient-id", required=True, help="Patient ID (e.g. P001)")
    new_parser.add_argument("--name", required=True, help="Patient name")
    new_parser.add_argument(
        "--exercises",
        required=True,
        help="Exercises as 'Name:sets:reps,...' (e.g. 'Quad Sets:3:10,Lunges:2:15')",
    )
    new_parser.add_argument("--start-date", help="Program start date (YYYY-MM-DD, default: today)")
    new_parser.add_argument("--no-consent", action="store_true", help="Create patient without login/consent (demo consent gate)")

    # chat
    chat_parser = subparsers.add_parser("chat", help="Chat with a patient")
    chat_parser.add_argument("--patient-id", required=True, help="Patient ID")

    # trigger
    trigger_parser = subparsers.add_parser("trigger", help="Fire a scheduled check-in")
    trigger_parser.add_argument("--patient-id", required=True, help="Patient ID")
    trigger_parser.add_argument(
        "--type",
        required=True,
        choices=["day_2_checkin", "day_5_checkin", "day_7_checkin", "backoff"],
        help="Trigger type",
    )

    # consent
    consent_parser = subparsers.add_parser("consent", help="Grant or revoke consent")
    consent_parser.add_argument("--patient-id", required=True, help="Patient ID")
    consent_parser.add_argument("--revoke", action="store_true", help="Revoke consent instead of granting")

    # patients
    subparsers.add_parser("patients", help="List all patients")

    # reset
    reset_parser = subparsers.add_parser("reset", help="Delete a patient")
    reset_parser.add_argument("--patient-id", required=True, help="Patient ID")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "new": cmd_new,
        "chat": cmd_chat,
        "trigger": cmd_trigger,
        "consent": cmd_consent,
        "patients": cmd_patients,
        "reset": cmd_reset,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
