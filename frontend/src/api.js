const BASE = "http://localhost:8000/api";

export async function fetchPatients() {
  const res = await fetch(`${BASE}/patients`);
  return res.json();
}

export async function fetchDashboard() {
  const res = await fetch(`${BASE}/dashboard`);
  return res.json();
}

export async function fetchPatient(patientId) {
  const res = await fetch(`${BASE}/patients/${patientId}`);
  if (!res.ok) throw new Error("Patient not found");
  return res.json();
}

export async function createPatient({ patientId, name, exercises, noConsent }) {
  const res = await fetch(`${BASE}/patients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      patient_id: patientId,
      name,
      exercises,
      no_consent: noConsent || false,
    }),
  });
  return res.json();
}

export async function deletePatient(patientId) {
  await fetch(`${BASE}/patients/${patientId}`, { method: "DELETE" });
}

export async function sendMessage(patientId, message) {
  const res = await fetch(`${BASE}/patients/${patientId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return res.json();
}

export async function triggerCheckin(patientId, triggerType) {
  const res = await fetch(`${BASE}/patients/${patientId}/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trigger_type: triggerType }),
  });
  return res.json();
}

export async function updateConsent(patientId, revoke = false) {
  const res = await fetch(`${BASE}/patients/${patientId}/consent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revoke }),
  });
  return res.json();
}

export async function fetchAllAlerts() {
  const res = await fetch(`${BASE}/alerts`);
  return res.json();
}

export async function acknowledgeAlert(patientId, alertId) {
  const res = await fetch(
    `${BASE}/patients/${patientId}/alerts/${alertId}/acknowledge`,
    { method: "POST" }
  );
  return res.json();
}

export async function getSimDate() {
  const res = await fetch(`${BASE}/simulation/date`);
  return res.json();
}

export async function setSimDate(date) {
  const res = await fetch(`${BASE}/simulation/date`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date }),
  });
  return res.json();
}
