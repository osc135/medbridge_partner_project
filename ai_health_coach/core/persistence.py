"""Persistence layer — SQLite-backed state storage.

Uses a simple JSON-serialized approach via SQLite. LangGraph's checkpointer
can be layered on top, but this gives us direct control for the CLI.
Swap to Postgres by changing the connection string.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ai_health_coach.core.state.schemas import PatientState

def _get_connection() -> sqlite3.Connection:
    db_path = os.environ.get("HEALTH_COACH_DB", "patients.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_states (
            patient_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_state(state: PatientState) -> None:
    """Persist patient state to SQLite."""
    conn = _get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO patients (patient_id, state_json) VALUES (?, ?)",
        (state["patient_id"], json.dumps(state)),
    )
    conn.commit()
    conn.close()


def load_state(patient_id: str) -> PatientState | None:
    """Load patient state from SQLite. Returns None if not found."""
    conn = _get_connection()
    cursor = conn.execute(
        "SELECT state_json FROM patients WHERE patient_id = ?",
        (patient_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def save_onboarding_state(patient_id: str, onboarding_state: dict) -> None:
    """Persist onboarding subgraph state."""
    conn = _get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO onboarding_states (patient_id, state_json) VALUES (?, ?)",
        (patient_id, json.dumps(onboarding_state)),
    )
    conn.commit()
    conn.close()


def load_onboarding_state(patient_id: str) -> dict | None:
    """Load onboarding subgraph state."""
    conn = _get_connection()
    cursor = conn.execute(
        "SELECT state_json FROM onboarding_states WHERE patient_id = ?",
        (patient_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def list_patients() -> list[dict]:
    """List all patients with their current phase."""
    conn = _get_connection()
    cursor = conn.execute("SELECT patient_id, state_json FROM patients")
    patients = []
    for row in cursor:
        state = json.loads(row[1])
        patients.append({
            "patient_id": state["patient_id"],
            "patient_name": state["patient_name"],
            "phase": state["phase"],
        })
    conn.close()
    return patients


def delete_patient(patient_id: str) -> bool:
    """Delete a patient's state. Returns True if found and deleted."""
    conn = _get_connection()
    cursor = conn.execute("DELETE FROM patients WHERE patient_id = ?", (patient_id,))
    conn.execute("DELETE FROM onboarding_states WHERE patient_id = ?", (patient_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted
