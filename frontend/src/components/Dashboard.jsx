import { useState } from "react";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "at_risk", label: "At Risk" },
  { key: "dormant", label: "Dormant" },
  { key: "has_alerts", label: "Has Alerts" },
];

const PHASE_CLASSES = {
  PENDING: "phase-pending",
  ONBOARDING: "phase-onboarding",
  ACTIVE: "phase-active",
  RE_ENGAGING: "phase-re_engaging",
  DORMANT: "phase-dormant",
};

const EMPTY_EXERCISE = { name: "", sets: "", reps: "" };

export default function Dashboard({ data, onSelectPatient, onAcknowledgeAlert, onCreatePatient, onDeletePatient, theme, onToggleTheme }) {
  const [filter, setFilter] = useState("all");
  const [sortCol, setSortCol] = useState("patient_name");
  const [sortAsc, setSortAsc] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [formData, setFormData] = useState({ patientId: "", name: "", noConsent: false });
  const [exercises, setExercises] = useState([{ ...EMPTY_EXERCISE }]);

  // Summary counts
  const total = data.length;
  const active = data.filter((p) => p.phase === "ACTIVE").length;
  const atRisk = data.filter(
    (p) => p.phase === "RE_ENGAGING" || p.consecutive_unanswered_count >= 1
  ).length;
  const dormant = data.filter((p) => p.phase === "DORMANT").length;
  const alertCount = data.reduce((sum, p) => sum + (p.active_alerts?.length || 0), 0);

  // Filter
  const filtered = data.filter((p) => {
    if (filter === "active") return p.phase === "ACTIVE";
    if (filter === "at_risk") return p.phase === "RE_ENGAGING" || p.consecutive_unanswered_count >= 1;
    if (filter === "dormant") return p.phase === "DORMANT";
    if (filter === "has_alerts") return (p.active_alerts?.length || 0) > 0;
    return true;
  });

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    let aVal = a[sortCol];
    let bVal = b[sortCol];

    // Special handling for alerts — sort by count
    if (sortCol === "active_alerts") {
      aVal = a.active_alerts?.length || 0;
      bVal = b.active_alerts?.length || 0;
    }

    // Nulls to the bottom
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;

    if (typeof aVal === "string") {
      return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }
    return sortAsc ? aVal - bVal : bVal - aVal;
  });

  function handleSort(col) {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
  }

  function sortIndicator(col) {
    if (sortCol !== col) return "";
    return sortAsc ? " \u25B2" : " \u25BC";
  }

  function handleCardClick(filterKey) {
    setFilter(filter === filterKey ? "all" : filterKey);
  }

  function handleCreateSubmit(e) {
    e.preventDefault();
    const parsed = exercises
      .filter((ex) => ex.name.trim())
      .map((ex) => ({
        name: ex.name.trim(),
        sets: parseInt(ex.sets) || 3,
        reps: parseInt(ex.reps) || 10,
      }));
    if (parsed.length === 0) return;
    onCreatePatient({
      patientId: formData.patientId.trim().toLowerCase(),
      name: formData.name,
      exercises: parsed,
      noConsent: formData.noConsent,
    });
    setFormData({ patientId: "", name: "", noConsent: false });
    setExercises([{ ...EMPTY_EXERCISE }]);
    setShowCreate(false);
  }

  function addExercise() {
    setExercises([...exercises, { ...EMPTY_EXERCISE }]);
  }

  function updateExercise(index, field, value) {
    setExercises(exercises.map((ex, i) => (i === index ? { ...ex, [field]: value } : ex)));
  }

  function removeExercise(index) {
    if (exercises.length === 1) return;
    setExercises(exercises.filter((_, i) => i !== index));
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Dashboard</h1>
        <div className="dashboard-header-actions">
          <button className="btn-theme-toggle" onClick={onToggleTheme}>
            {theme === "dark" ? "\u2600" : "\u263E"}
          </button>
          <button
            className="btn-primary dash-btn-create"
            onClick={() => setShowCreate(!showCreate)}
          >
            {showCreate ? "Cancel" : "+ New Patient"}
          </button>
        </div>
      </div>

      {/* Create Patient Form */}
      {showCreate && (
        <form className="dash-create-form" onSubmit={handleCreateSubmit}>
          <input
            type="email"
            placeholder="Patient email (e.g. jane@gmail.com)"
            value={formData.patientId}
            onChange={(e) => setFormData({ ...formData, patientId: e.target.value.toLowerCase() })}
            required
          />
          <input
            placeholder="Patient name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            required
          />
          <div className="dash-exercises-row">
            <span className="dash-exercises-label">Exercises</span>
            <button type="button" className="btn-add-exercise" onClick={addExercise}>+ Add</button>
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
                <button type="button" className="btn-remove-exercise" onClick={() => removeExercise(i)}>&times;</button>
              )}
            </div>
          ))}
          <div className="dash-create-footer">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={formData.noConsent}
                onChange={(e) => setFormData({ ...formData, noConsent: e.target.checked })}
              />
              No consent (demo)
            </label>
            <button type="submit" className="btn-primary">Create</button>
          </div>
        </form>
      )}

      {/* Summary Cards */}
      <div className="dashboard-cards">
        <div
          className={`dash-card ${filter === "all" ? "dash-card-active" : ""}`}
          onClick={() => handleCardClick("all")}
        >
          <div className="dash-card-value">{total}</div>
          <div className="dash-card-label">Total Patients</div>
        </div>
        <div
          className={`dash-card dash-card-green ${filter === "active" ? "dash-card-active" : ""}`}
          onClick={() => handleCardClick("active")}
        >
          <div className="dash-card-value">{active}</div>
          <div className="dash-card-label">Active</div>
        </div>
        <div
          className={`dash-card dash-card-orange ${filter === "at_risk" ? "dash-card-active" : ""}`}
          onClick={() => handleCardClick("at_risk")}
        >
          <div className="dash-card-value">{atRisk}</div>
          <div className="dash-card-label">At Risk</div>
        </div>
        <div
          className={`dash-card dash-card-red ${filter === "dormant" ? "dash-card-active" : ""}`}
          onClick={() => handleCardClick("dormant")}
        >
          <div className="dash-card-value">{dormant}</div>
          <div className="dash-card-label">Dormant</div>
        </div>
        <div
          className={`dash-card dash-card-red ${filter === "has_alerts" ? "dash-card-active" : ""}`}
          onClick={() => handleCardClick("has_alerts")}
        >
          <div className="dash-card-value">{alertCount}</div>
          <div className="dash-card-label">Alerts</div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="dashboard-filters">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`dash-filter ${filter === f.key ? "dash-filter-active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
        <span className="dash-filter-count">{filtered.length} patient{filtered.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Patient Table */}
      <div className="dashboard-table-wrap">
        <table className="dashboard-table">
          <thead>
            <tr>
              <th onClick={() => handleSort("patient_name")}>Name{sortIndicator("patient_name")}</th>
              <th onClick={() => handleSort("phase")}>Phase{sortIndicator("phase")}</th>
              <th onClick={() => handleSort("goal_summary")}>Goal{sortIndicator("goal_summary")}</th>
              <th onClick={() => handleSort("adherence_rate")}>Adherence{sortIndicator("adherence_rate")}</th>
              <th onClick={() => handleSort("last_contact_date")}>Last Contact{sortIndicator("last_contact_date")}</th>
              <th onClick={() => handleSort("consecutive_unanswered_count")}>Unanswered{sortIndicator("consecutive_unanswered_count")}</th>
              <th onClick={() => handleSort("active_alerts")}>Alerts{sortIndicator("active_alerts")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr
                key={p.patient_id}
                className={`dash-row dash-row-${p.phase.toLowerCase()}`}
                onClick={() => onSelectPatient(p.patient_id)}
              >
                <td>
                  <div className="dash-cell-name">
                    <span className="dash-patient-name">{p.patient_name}</span>
                    <span className="dash-patient-id">{p.patient_id}</span>
                  </div>
                </td>
                <td>
                  <span className={`phase-indicator ${PHASE_CLASSES[p.phase] || ""}`}>
                    {p.phase}
                  </span>
                </td>
                <td>
                  <span className="dash-cell-goal">{p.goal_summary || "\u2014"}</span>
                </td>
                <td>
                  {p.adherence_rate != null ? (
                    <span className={`dash-adherence ${p.adherence_rate >= 0.7 ? "good" : p.adherence_rate >= 0.4 ? "mid" : "low"}`}>
                      {Math.round(p.adherence_rate * 100)}%
                    </span>
                  ) : (
                    <span className="dash-cell-na">\u2014</span>
                  )}
                </td>
                <td>
                  <span className="dash-cell-date">{p.last_contact_date || "Never"}</span>
                </td>
                <td>
                  {p.consecutive_unanswered_count > 0 ? (
                    <span className="dash-unanswered">{p.consecutive_unanswered_count}</span>
                  ) : (
                    <span className="dash-cell-zero">0</span>
                  )}
                </td>
                <td>
                  {(p.active_alerts?.length || 0) > 0 ? (
                    <div className="dash-cell-alerts">
                      {p.active_alerts.map((alert) => (
                        <span
                          key={alert.id}
                          className={`dash-alert-chip ${alert.urgency === "urgent" ? "dash-alert-urgent" : "dash-alert-routine"}`}
                          title={alert.context}
                          onClick={(e) => {
                            e.stopPropagation();
                            onAcknowledgeAlert(p.patient_id, alert.id);
                          }}
                        >
                          {alert.alert_type === "mental_health_crisis" ? "Crisis" : "Disengaged"}
                          <span className="dash-alert-x">&times;</span>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="dash-cell-zero">\u2014</span>
                  )}
                </td>
                <td>
                  <button
                    className="btn-delete-row"
                    title="Delete patient"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeletePatient(p.patient_id);
                    }}
                  >
                    &times;
                  </button>
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={8} className="dash-empty">No patients match this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
