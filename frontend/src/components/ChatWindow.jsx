import { useState, useEffect, useRef } from "react";

export default function ChatWindow({ patient, onSend, onTrigger, onConsent, loading, theme, onToggleTheme }) {
  const [input, setInput] = useState("");
  const messagesEnd = useRef(null);

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
          <p className="empty-chat-sub">Select a patient or create one to begin</p>
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
          <h2>{patient.patient_name}</h2>
          <span className="header-id">{patient.patient_id}</span>
        </div>
        <div className="chat-header-meta">
          <button className="btn-theme-toggle" onClick={onToggleTheme}>
            {theme === "dark" ? "☀" : "☾"}
          </button>
          <span className={`phase-indicator phase-${patient.phase.toLowerCase()}`}>
            {patient.phase}
          </span>
          {patient.goal && (
            <span className="goal-badge">
              Goal: {patient.goal.goal_type} {patient.goal.frequency}{" "}
              {patient.goal.time_of_day && `in the ${patient.goal.time_of_day}`}
            </span>
          )}
        </div>
      </div>

      <div className="chat-toolbar">
        {needsConsent ? (
          <button
            className="btn-consent"
            onClick={() => onConsent(false)}
            disabled={loading}
          >
            Grant Consent
          </button>
        ) : (
          <button
            className="btn-revoke"
            onClick={() => onConsent(true)}
            disabled={loading}
          >
            Revoke Consent
          </button>
        )}

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
      </div>

      <div className="chat-messages">
        {needsConsent && (
          <div className="consent-banner">
            <div className="consent-banner-icon">!</div>
            <div className="consent-banner-text">
              {!patient.has_logged_in
                ? "This patient has not logged in or consented to coaching. Grant consent to begin."
                : "This patient has revoked consent. Coaching is paused — their progress is preserved and will resume if they re-consent."}
            </div>
          </div>
        )}
        {patient.messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-role">
              {msg.role === "assistant" ? "Coach" : "Patient"}
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

      {!needsConsent && (
        <form className="chat-input" onSubmit={handleSubmit}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message as the patient..."
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
