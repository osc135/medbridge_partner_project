import { useState } from "react";

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !trimmed.includes("@")) {
      setError("Please enter a valid email address.");
      return;
    }

    const role = trimmed.endsWith("@healthcare.com") ? "clinician" : "patient";

    // For patients, their email IS their patient ID
    onLogin({ email: trimmed, role, patientId: role === "patient" ? trimmed : null });
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">+</div>
        <h1 className="login-title">AI Health Coach</h1>
        <p className="login-subtitle">Sign in with your email to continue</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setError("");
            }}
            autoFocus
            required
          />
          {error && <p className="login-error">{error}</p>}
          <button type="submit" className="btn-primary login-btn">
            Sign In
          </button>
        </form>

        <p className="login-hint">
          Use <strong>@healthcare.com</strong> for clinician access
        </p>
      </div>
    </div>
  );
}
