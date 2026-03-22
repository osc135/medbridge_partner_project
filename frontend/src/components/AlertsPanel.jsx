export default function AlertsPanel({ alerts, onSelectPatient, onAcknowledge }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="alerts-panel">
      <div className="alerts-panel-header">
        <span className="alerts-panel-title">Alerts</span>
        <span className="alerts-panel-count">{alerts.length}</span>
      </div>
      <div className="alerts-panel-list">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`alert-item alert-${alert.urgency}`}
            onClick={() => onSelectPatient(alert.patient_id)}
          >
            <div className="alert-item-icon">
              {alert.urgency === "urgent" ? "!" : "?"}
            </div>
            <div className="alert-item-body">
              <div className="alert-item-top">
                <span className="alert-item-patient">{alert.patient_name}</span>
                <span className={`alert-item-type alert-type-${alert.alert_type}`}>
                  {alert.alert_type === "mental_health_crisis" ? "Crisis" : "Disengaged"}
                </span>
              </div>
              <div className="alert-item-context">{alert.context}</div>
              <div className="alert-item-bottom">
                <span className="alert-item-time">{alert.timestamp}</span>
                <button
                  className="btn-acknowledge-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAcknowledge(alert.patient_id, alert.id);
                  }}
                >
                  Acknowledge
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
