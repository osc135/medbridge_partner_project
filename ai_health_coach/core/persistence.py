"""Persistence layer — Postgres via DATABASE_URL."""

from __future__ import annotations

import json
import os

import psycopg2

from ai_health_coach.core.state.schemas import PatientState


def _get_connection():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_states (
            patient_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_state(state: PatientState) -> None:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO patients (patient_id, state_json) VALUES (%s, %s) "
        "ON CONFLICT (patient_id) DO UPDATE SET state_json = EXCLUDED.state_json",
        (state["patient_id"], json.dumps(state)),
    )
    conn.commit()
    conn.close()


def load_state(patient_id: str) -> PatientState | None:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT state_json FROM patients WHERE patient_id = %s", (patient_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def save_onboarding_state(patient_id: str, onboarding_state: dict) -> None:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO onboarding_states (patient_id, state_json) VALUES (%s, %s) "
        "ON CONFLICT (patient_id) DO UPDATE SET state_json = EXCLUDED.state_json",
        (patient_id, json.dumps(onboarding_state)),
    )
    conn.commit()
    conn.close()


def load_onboarding_state(patient_id: str) -> dict | None:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT state_json FROM onboarding_states WHERE patient_id = %s", (patient_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def list_patients() -> list[dict]:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT patient_id, state_json FROM patients")
    patients = []
    for row in cur:
        state = json.loads(row[1])
        patients.append({
            "patient_id": state["patient_id"],
            "patient_name": state["patient_name"],
            "phase": state["phase"],
        })
    conn.close()
    return patients


def delete_patient(patient_id: str) -> bool:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM patients WHERE patient_id = %s", (patient_id,))
    deleted = cur.rowcount > 0
    cur.execute("DELETE FROM onboarding_states WHERE patient_id = %s", (patient_id,))
    conn.commit()
    conn.close()
    return deleted
