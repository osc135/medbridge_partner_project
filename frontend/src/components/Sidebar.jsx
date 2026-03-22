import { useState } from "react";
import AlertsPanel from "./AlertsPanel";

const PHASE_COLORS = {
  PENDING: "#9ca3af",
  ONBOARDING: "#3b82f6",
  ACTIVE: "#22c55e",
  RE_ENGAGING: "#f59e0b",
  DORMANT: "#ef4444",
};

const EMPTY_EXERCISE = { name: "", sets: "", reps: "" };

export default function Sidebar({
  patients,
  selectedId,
  onSelect,
  onCreate,
  onDelete,
  onLogout,
  userEmail,
  alerts,
  onAcknowledgeAlert,
}) {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    patientId: "",
    name: "",
    noConsent: false,
  });
  const [exercises, setExercises] = useState([{ ...EMPTY_EXERCISE }]);

  function addExercise() {
    setExercises([...exercises, { ...EMPTY_EXERCISE }]);
  }

  function updateExercise(index, field, value) {
    const updated = exercises.map((ex, i) =>
      i === index ? { ...ex, [field]: value } : ex
    );
    setExercises(updated);
  }

  function removeExercise(index) {
    if (exercises.length === 1) return;
    setExercises(exercises.filter((_, i) => i !== index));
  }

  function handleSubmit(e) {
    e.preventDefault();
    const parsed = exercises
      .filter((ex) => ex.name.trim())
      .map((ex) => ({
        name: ex.name.trim(),
        sets: parseInt(ex.sets) || 3,
        reps: parseInt(ex.reps) || 10,
      }));

    if (parsed.length === 0) return;

    onCreate({
      patientId: formData.patientId.trim().toLowerCase(),
      name: formData.name,
      exercises: parsed,
      noConsent: formData.noConsent,
    });
    setFormData({ patientId: "", name: "", noConsent: false });
    setExercises([{ ...EMPTY_EXERCISE }]);
    setShowForm(false);
  }

  return (
    <div className="sidebar">
      <div className="sidebar-user">
        <span className="sidebar-user-email">{userEmail}</span>
        <button className="btn-logout-sm" onClick={onLogout}>Sign Out</button>
      </div>
      <div className="sidebar-header">
        <h2>Patients</h2>
        <button className="btn-icon" onClick={() => setShowForm(!showForm)}>
          {showForm ? "×" : "+"}
        </button>
      </div>

      <AlertsPanel
        alerts={alerts}
        onSelectPatient={onSelect}
        onAcknowledge={onAcknowledgeAlert}
      />

      {showForm && (
        <form className="new-patient-form" onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Patient email (e.g. jane@gmail.com)"
            value={formData.patientId}
            onChange={(e) =>
              setFormData({ ...formData, patientId: e.target.value.toLowerCase() })
            }
            required
          />
          <input
            placeholder="Name"
            value={formData.name}
            onChange={(e) =>
              setFormData({ ...formData, name: e.target.value })
            }
            required
          />

          <div className="exercises-section">
            <div className="exercises-header">
              <span className="exercises-label">Exercises</span>
              <button type="button" className="btn-add-exercise" onClick={addExercise}>
                + Add
              </button>
            </div>
            {exercises.map((ex, i) => (
              <div key={i} className="exercise-row">
                <input
                  className="exercise-name"
                  placeholder="Exercise name"
                  value={ex.name}
                  onChange={(e) => updateExercise(i, "name", e.target.value)}
                  required
                />
                <input
                  className="exercise-num"
                  type="number"
                  placeholder="Sets"
                  min="1"
                  value={ex.sets}
                  onChange={(e) => updateExercise(i, "sets", e.target.value)}
                  required
                />
                <input
                  className="exercise-num"
                  type="number"
                  placeholder="Reps"
                  min="1"
                  value={ex.reps}
                  onChange={(e) => updateExercise(i, "reps", e.target.value)}
                  required
                />
                {exercises.length > 1 && (
                  <button
                    type="button"
                    className="btn-remove-exercise"
                    onClick={() => removeExercise(i)}
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={formData.noConsent}
              onChange={(e) =>
                setFormData({ ...formData, noConsent: e.target.checked })
              }
            />
            No consent (demo consent gate)
          </label>
          <button type="submit" className="btn-primary">
            Create Patient
          </button>
        </form>
      )}

      <div className="patient-list">
        {patients.map((p) => {
          const alertCount = (alerts || []).filter(
            (a) => a.patient_id === p.patient_id
          ).length;
          const hasUrgent = (alerts || []).some(
            (a) => a.patient_id === p.patient_id && a.urgency === "urgent"
          );
          return (
          <div
            key={p.patient_id}
            className={`patient-item ${selectedId === p.patient_id ? "selected" : ""}`}
            onClick={() => onSelect(p.patient_id)}
          >
            <div className="patient-info">
              <span className="patient-name">
                {p.patient_name}
                {alertCount > 0 && (
                  <span className={`alert-badge ${hasUrgent ? "alert-badge-urgent" : "alert-badge-routine"}`}>
                    {alertCount}
                  </span>
                )}
              </span>
              <span
                className="phase-badge"
                style={{ backgroundColor: PHASE_COLORS[p.phase] || "#6b7280" }}
              >
                {p.phase}
              </span>
            </div>
            <span className="patient-id">{p.patient_id}</span>
            <button
              className="btn-delete"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(p.patient_id);
              }}
            >
              ×
            </button>
          </div>
          );
        })}
        {patients.length === 0 && (
          <p className="empty-state">No patients yet. Click + to create one.</p>
        )}
      </div>
    </div>
  );
}
