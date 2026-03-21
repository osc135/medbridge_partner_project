"""Safety classifier — keyword-based with LLM upgrade path.

Runs inside every subgraph after message generation, before delivery.
Swap classify_message() internals for an LLM-based classifier later;
nothing else in the system changes.
"""

CLINICAL_KEYWORDS = [
    "pain", "symptom", "medication", "diagnosis", "treatment",
    "doctor", "prescription", "side effect", "injury", "swelling",
]

CRISIS_KEYWORDS = [
    # Direct statements
    "suicide", "kill myself", "end my life", "want to die",
    "don't want to live", "take my own life",
    # Hopelessness
    "no point", "hopeless", "nothing matters", "give up",
    "can't go on", "what's the point", "nobody cares",
    "better off without me", "can't take it anymore",
    # Self harm
    "hurt myself", "self harm", "cutting", "harming myself",
    # Withdrawal
    "disappear", "not here anymore", "end it all",
    "escape everything", "done with everything",
]

CLINICAL_REDIRECT = (
    "That's a great question for your care team. "
    "Please reach out to your clinician directly for anything related "
    "to your symptoms or treatment."
)

CRISIS_MESSAGE = (
    "I hear you, and I want you to know that support is available. "
    "Please reach out to the 988 Suicide & Crisis Lifeline by calling or texting 988. "
    "Your care team has also been notified and will be reaching out to you."
)

FALLBACK_MESSAGE = (
    "I'm not able to help with that, but your care team "
    "is always available to answer your questions."
)

SAFE_PROMPT_ADDITION = """
Important: Do not reference symptoms, medications, diagnoses, or treatments.
If the patient has raised clinical concerns, direct them to their care team only.
"""


def classify_message(message: str) -> str:
    """Classify a message as safe, clinical, or mental_health_crisis.

    Crisis is checked first — always escalate to higher severity.
    """
    message_lower = message.lower()

    if any(kw in message_lower for kw in CRISIS_KEYWORDS):
        return "mental_health_crisis"
    elif any(kw in message_lower for kw in CLINICAL_KEYWORDS):
        return "clinical"
    return "safe"


def check_and_filter_message(
    message: str,
    regenerate_fn=None,
) -> dict:
    """Run the full safety check pipeline on a generated message.

    Args:
        message: The LLM-generated message to check.
        regenerate_fn: Optional callable that returns a new message string
                       (called with SAFE_PROMPT_ADDITION appended to prompt).

    Returns:
        SafetyCheckState dict with final_message and metadata.
    """
    classification = classify_message(message)
    preview = message[:80] + ("..." if len(message) > 80 else "")

    if classification == "safe":
        print(f"  \033[92m  ✓ SAFETY: safe — \"{preview}\"\033[0m")
        return {
            "original_message": message,
            "flagged": False,
            "flag_reason": None,
            "retry_count": 0,
            "final_message": message,
        }

    if classification == "mental_health_crisis":
        print(f"  \033[91m  ✗ SAFETY: CRISIS DETECTED — \"{preview}\"\033[0m")
        return {
            "original_message": message,
            "flagged": True,
            "flag_reason": "mental_health_crisis",
            "retry_count": 0,
            "final_message": CRISIS_MESSAGE,
        }

    # Clinical — retry once with augmented prompt, then fallback
    print(f"  \033[93m  ⚠ SAFETY: clinical content — \"{preview}\"\033[0m")
    if regenerate_fn is not None:
        print(f"  \033[93m  ↻ SAFETY: retrying with safe prompt...\033[0m")
        retry_message = regenerate_fn()
        if classify_message(retry_message) == "safe":
            print(f"  \033[92m  ✓ SAFETY: retry passed\033[0m")
            return {
                "original_message": message,
                "flagged": True,
                "flag_reason": "clinical",
                "retry_count": 1,
                "final_message": retry_message,
            }
        print(f"  \033[91m  ✗ SAFETY: retry also flagged — using fallback\033[0m")

    return {
        "original_message": message,
        "flagged": True,
        "flag_reason": "clinical",
        "retry_count": 1 if regenerate_fn else 0,
        "final_message": FALLBACK_MESSAGE,
    }
