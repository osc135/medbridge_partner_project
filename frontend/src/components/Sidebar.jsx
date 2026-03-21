import { useState } from "react";

const PHASE_COLORS = {
  PENDING: "#9ca3af",
  ONBOARDING: "#3b82f6",
  ACTIVE: "#22c55e",
  RE_ENGAGING: "#f59e0b",
  DORMANT: "#ef4444",
};

export default function Sidebar({
  patients,
  selectedId,
  onSelect,
  onCreate,
  onDelete,
}) {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    patientId: "",
    name: "",
    exercises: "",
    noConsent: false,
  });

  function handleSubmit(e) {
    e.preventDefault();
    onCreate({
      patientId: formData.patientId,
      name: formData.name,
      exercises: formData.exercises.split(",").map((s) => s.trim()),
      noConsent: formData.noConsent,
    });
    setFormData({ patientId: "", name: "", exercises: "", noConsent: false });
    setShowForm(false);
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h2>Patients</h2>
        <button className="btn-icon" onClick={() => setShowForm(!showForm)}>
          {showForm ? "×" : "+"}
        </button>
      </div>

      {showForm && (
        <form className="new-patient-form" onSubmit={handleSubmit}>
          <input
            placeholder="Patient ID (e.g. P001)"
            value={formData.patientId}
            onChange={(e) =>
              setFormData({ ...formData, patientId: e.target.value })
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
          <input
            placeholder="Exercises (comma-separated)"
            value={formData.exercises}
            onChange={(e) =>
              setFormData({ ...formData, exercises: e.target.value })
            }
            required
          />
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
        {patients.map((p) => (
          <div
            key={p.patient_id}
            className={`patient-item ${selectedId === p.patient_id ? "selected" : ""}`}
            onClick={() => onSelect(p.patient_id)}
          >
            <div className="patient-info">
              <span className="patient-name">{p.patient_name}</span>
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
        ))}
        {patients.length === 0 && (
          <p className="empty-state">No patients yet. Click + to create one.</p>
        )}
      </div>
    </div>
  );
}
