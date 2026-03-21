"""FastAPI routes — thin wrapper around core logic."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_health_coach.core.graph.router import route_message
from ai_health_coach.core.persistence import (
    delete_patient,
    list_patients,
    load_onboarding_state,
    load_state,
    save_onboarding_state,
    save_state,
)
from ai_health_coach.core.state.schemas import PHASE_ONBOARDING, create_initial_state

app = FastAPI(title="AI Health Coach API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ────────────────────────────────────────


class CreatePatientRequest(BaseModel):
    patient_id: str
    name: str
    exercises: list[dict]  # [{"name": str, "sets": int, "reps": int}]
    start_date: Optional[str] = None
    no_consent: bool = False


class ChatRequest(BaseModel):
    message: str


class TriggerRequest(BaseModel):
    trigger_type: str  # day_2_checkin | day_5_checkin | day_7_checkin | backoff


class ConsentRequest(BaseModel):
    revoke: bool = False


class PatientResponse(BaseModel):
    patient_id: str
    patient_name: str
    phase: str
    has_logged_in: bool
    has_consented: bool
    goal: Optional[dict] = None
    messages: list[dict]
    consecutive_unanswered_count: int
    completed_checkins: list[str]
    assigned_exercises: list[dict]
    exercise_log: list[dict]


class ChatResponse(BaseModel):
    response: Optional[str]
    phase: str


# ─── Endpoints ──────────────────────────────────────────────────────


@app.get("/api/patients")
def get_patients():
    return list_patients()


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str):
    state = load_state(patient_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return PatientResponse(
        patient_id=state["patient_id"],
        patient_name=state["patient_name"],
        phase=state["phase"],
        has_logged_in=state["has_logged_in"],
        has_consented=state["has_consented"],
        goal=state.get("goal"),
        messages=state["messages"],
        consecutive_unanswered_count=state["consecutive_unanswered_count"],
        completed_checkins=state["completed_checkins"],
        assigned_exercises=state["assigned_exercises"],
        exercise_log=state.get("exercise_log", []),
    )


@app.post("/api/patients")
def create_patient(req: CreatePatientRequest):
    start_date = req.start_date or datetime.now().strftime("%Y-%m-%d")
    state = create_initial_state(
        patient_id=req.patient_id,
        patient_name=req.name,
        assigned_exercises=req.exercises,
        program_start_date=start_date,
        has_logged_in=not req.no_consent,
        has_consented=not req.no_consent,
    )
    save_state(state)

    # Run initial routing (triggers onboarding welcome if consented)
    result = route_message(state, patient_message=None)
    state = result["state"]
    save_state(state)
    if result.get("onboarding_state"):
        save_onboarding_state(req.patient_id, result["onboarding_state"])

    return ChatResponse(response=result["response"], phase=state["phase"])


@app.delete("/api/patients/{patient_id}")
def remove_patient(patient_id: str):
    if not delete_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"deleted": True}


@app.post("/api/patients/{patient_id}/chat")
def chat(patient_id: str, req: ChatRequest):
    state = load_state(patient_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    onboarding_state = None
    if state["phase"] == PHASE_ONBOARDING:
        onboarding_state = load_onboarding_state(patient_id)

    result = route_message(
        state,
        patient_message=req.message,
        onboarding_state=onboarding_state,
    )

    state = result["state"]
    save_state(state)
    if result.get("onboarding_state"):
        save_onboarding_state(patient_id, result["onboarding_state"])

    return ChatResponse(response=result["response"], phase=state["phase"])


@app.post("/api/patients/{patient_id}/trigger")
def trigger(patient_id: str, req: TriggerRequest):
    state = load_state(patient_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Only block duplicate check-ins while still in ACTIVE phase
    if state["phase"] == "ACTIVE" and req.trigger_type in state.get("completed_checkins", []):
        raise HTTPException(status_code=400, detail=f"Check-in {req.trigger_type} already completed")

    onboarding_state = load_onboarding_state(patient_id)
    result = route_message(
        state,
        trigger_type=req.trigger_type,
        onboarding_state=onboarding_state,
    )

    state = result["state"]
    save_state(state)

    return ChatResponse(response=result["response"], phase=state["phase"])


@app.post("/api/patients/{patient_id}/consent")
def update_consent(patient_id: str, req: ConsentRequest):
    state = load_state(patient_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    if req.revoke:
        state = {**state, "has_consented": False}
        save_state(state)
        return ChatResponse(response=None, phase=state["phase"])
    else:
        state = {**state, "has_logged_in": True, "has_consented": True}
        save_state(state)

        result = route_message(state, patient_message=None)
        state = result["state"]
        save_state(state)
        if result.get("onboarding_state"):
            save_onboarding_state(patient_id, result["onboarding_state"])

        return ChatResponse(response=result["response"], phase=state["phase"])
