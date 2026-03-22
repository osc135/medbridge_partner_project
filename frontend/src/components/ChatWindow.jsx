import { useState, useEffect, useRef } from "react";

export default function ChatWindow({ patient, onSend, onTrigger, onConsent, loading, theme, onToggleTheme, role = "clinician", onAcknowledgeAlert, onBack }) {
  const [input, setInput] = useState("");
  const messagesEnd = useRef(null);

  const isClinician = role === "clinician";
  const isPatient = role === "patient";

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [patient?.messages]);

  if (!patient) {
    return (
      <div className="chat-window empty">
        <div className="top-bar">
          <button className="btn-theme-toggle" onClick={onToggleTheme}>
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
        <div className="empty-chat-state">
          <div className="empty-chat-icon">+</div>
          <p className="empty-chat-title">AI Health Coach</p>
          <p className="empty-chat-sub">
            {isClinician
              ? "Select a patient or create one to begin"
              : "No account found for this email. Ask your clinician to set you up."}
          </p>
        </div>
      </div>
    );
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSend(input.trim());
    setInput("");
  }

  const canTrigger = (type) => !patient.completed_checkins.includes(type);
  const needsConsent = !patient.has_logged_in || !patient.has_consented;

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div className="chat-header-info">
          {onBack && (
            <button className="btn-back-chat" onClick={onBack} title="Back to Dashboard">
              ←
            </button>
          )}
          <h2>{patient.patient_name}</h2>
          {isClinician && <span className="header-id">{patient.patient_id}</span>}
        </div>
        <div className="chat-header-meta">
          <button className="btn-theme-toggle" onClick={onToggleTheme}>
            {theme === "dark" ? "☀" : "☾"}
          </button>
          {isClinician && (
            <>
              <span className={`phase-indicator phase-${patient.phase.toLowerCase()}`}>
                {patient.phase}
              </span>
              {patient.goal && (
                <span className="goal-badge">
                  Goal: {patient.goal.goal_type} {patient.goal.frequency}{" "}
                  {patient.goal.time_of_day && `in the ${patient.goal.time_of_day}`}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      <div className="chat-toolbar">
        {/* Consent controls — patient only */}
        {isPatient && needsConsent && (
          <button
            className="btn-consent"
            onClick={() => onConsent(false)}
            disabled={loading}
          >
            I Consent to Coaching
          </button>
        )}
        {isPatient && !needsConsent && (
          <button
            className="btn-revoke"
            onClick={() => onConsent(true)}
            disabled={loading}
          >
            Revoke Consent
          </button>
        )}
        {/* Clinician sees status only */}
        {isClinician && needsConsent && (
          <span className="consent-status consent-status-pending">No Consent</span>
        )}
        {isClinician && !needsConsent && (
          <span className="consent-status consent-status-granted">Consented</span>
        )}

        {/* Clinician-only: triggers and date picker */}
        {isClinician && (
          <>
            <div className="trigger-buttons">
              <span className="trigger-label">Triggers:</span>
              {["day_2_checkin", "day_5_checkin", "day_7_checkin"].map((type) => (
                <button
                  key={type}
                  className={`btn-trigger ${!canTrigger(type) ? "completed" : ""}`}
                  onClick={() => onTrigger(type)}
                  disabled={!canTrigger(type) || loading}
                  title={!canTrigger(type) ? "Already sent" : `Fire ${type}`}
                >
                  {type.replace("_checkin", "").replace("_", " ")}
                  {!canTrigger(type) && " ✓"}
                </button>
              ))}
            </div>

          </>
        )}
      </div>

      <div className="chat-messages">
        {/* Alert banners for clinician */}
        {isClinician && patient.alerts && patient.alerts.filter(a => !a.acknowledged).map((alert) => (
          <div key={alert.id} className={`alert-banner alert-banner-${alert.urgency}`}>
            <div className={`alert-banner-icon ${alert.urgency === "urgent" ? "alert-banner-icon-urgent" : "alert-banner-icon-routine"}`}>
              {alert.urgency === "urgent" ? "!" : "?"}
            </div>
            <div className="alert-banner-body">
              <div className="alert-banner-top">
                <span className="alert-banner-label">
                  {alert.alert_type === "mental_health_crisis" ? "Crisis Alert" : "Disengagement Alert"}
                </span>
                <span className="alert-banner-time">{alert.timestamp}</span>
              </div>
              <div className="alert-banner-context">{alert.context}</div>
            </div>
            <button
              className="btn-acknowledge"
              onClick={() => onAcknowledgeAlert(patient.patient_id, alert.id)}
            >
              Acknowledge
            </button>
          </div>
        ))}

        {needsConsent && !isClinician && (
          <div className="consent-banner">
            <div className="consent-banner-icon">!</div>
            <div className="consent-banner-text">
              Your coaching is currently paused. Click "I Consent to Coaching" above to get started.
            </div>
          </div>
        )}
        {needsConsent && isClinician && (
          <div className="consent-banner">
            <div className="consent-banner-icon">!</div>
            <div className="consent-banner-text">
              {!patient.has_logged_in
                ? "This patient has not logged in or consented to coaching yet. Coaching will begin once they log in and consent."
                : "This patient has revoked consent. Coaching is paused — their progress is preserved and will resume if they re-consent."}
            </div>
          </div>
        )}
        {patient.messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-role">
              {msg.role === "assistant" ? "Coach" : (isClinician ? "Patient" : "You")}
            </div>
            <div className="message-content">{msg.content}</div>
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="message-role">Coach</div>
            <div className="message-content typing">Thinking...</div>
          </div>
        )}
        <div ref={messagesEnd} />
      </div>

      {/* Only patients can type — clinicians are read-only */}
      {isPatient && !needsConsent && (
        <form className="chat-input" onSubmit={handleSubmit}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>
      )}
    </div>
  );
}
