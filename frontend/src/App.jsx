import { useState, useEffect, useCallback } from "react";
import LoginPage from "./components/LoginPage";
import ChatWindow from "./components/ChatWindow";
import Dashboard from "./components/Dashboard";
import {
  fetchPatients,
  fetchPatient,
  fetchDashboard,
  createPatient,
  deletePatient,
  sendMessage,
  triggerCheckin,
  updateConsent,
  getSimDate,
  setSimDate,
  fetchAllAlerts,
  acknowledgeAlert,
} from "./api";
import "./App.css";

export default function App() {
  // Auth state
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem("user");
    return saved ? JSON.parse(saved) : null;
  });

  // App state
  const [patients, setPatients] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [loading, setLoading] = useState(false);
  const [simDate, setSimDateState] = useState("");
  const [allAlerts, setAllAlerts] = useState([]);
  const [dashboardData, setDashboardData] = useState([]);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  async function handleLogin(loginData) {
    setUser(loginData);
    localStorage.setItem("user", JSON.stringify(loginData));

    if (loginData.role === "patient") {
      setSelectedId(loginData.patientId);
    }
  }

  function handleLogout() {
    setUser(null);
    setSelectedId(null);
    setSelectedPatient(null);
    localStorage.removeItem("user");
  }

  const loadPatients = useCallback(async () => {
    const data = await fetchPatients();
    setPatients(data);
  }, []);

  const loadAlerts = useCallback(async () => {
    try {
      const data = await fetchAllAlerts();
      setAllAlerts(data);
    } catch {
      setAllAlerts([]);
    }
  }, []);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await fetchDashboard();
      setDashboardData(data);
    } catch {
      setDashboardData([]);
    }
  }, []);

  const loadPatient = useCallback(async (id) => {
    try {
      const data = await fetchPatient(id);
      setSelectedPatient(data);
    } catch {
      setSelectedPatient(null);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadPatients();
      if (user.role === "clinician") {
        getSimDate().then((d) => setSimDateState(d.date));
        loadAlerts();
        loadDashboard();
      }
    }
  }, [user, loadPatients, loadAlerts]);

  useEffect(() => {
    if (selectedId) loadPatient(selectedId);
  }, [selectedId, loadPatient]);

  // Patient view: poll for updates every 2 seconds (paused while sending)
  useEffect(() => {
    if (!user || user.role !== "patient" || !selectedId || loading) return;
    const interval = setInterval(() => {
      loadPatient(selectedId);
    }, 2000);
    return () => clearInterval(interval);
  }, [user, selectedId, loadPatient, loading]);

  async function reloadAll() {
    await loadPatients();
    await loadAlerts();
    await loadDashboard();
  }

  async function handleCreate(formData) {
    setLoading(true);
    try {
      await createPatient(formData);
      await reloadAll();
      setSelectedId(formData.patientId);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id) {
    await deletePatient(id);
    if (selectedId === id) {
      setSelectedId(null);
      setSelectedPatient(null);
    }
    await reloadAll();
  }

  async function handleSend(message) {
    setSelectedPatient((prev) => ({
      ...prev,
      messages: [...prev.messages, { role: "user", content: message }],
    }));
    setLoading(true);
    try {
      await sendMessage(selectedId, message);
      await loadPatient(selectedId);
      await reloadAll();
    } finally {
      setLoading(false);
    }
  }

  async function handleTrigger(type) {
    setLoading(true);
    try {
      await triggerCheckin(selectedId, type);
      await loadPatient(selectedId);
      await reloadAll();
    } finally {
      setLoading(false);
    }
  }

  async function handleDateChange(date) {
    setLoading(true);
    try {
      await setSimDate(date);
      setSimDateState(date);
      await reloadAll();
      if (selectedId) await loadPatient(selectedId);
    } finally {
      setLoading(false);
    }
  }

  async function handleAcknowledgeAlert(patientId, alertId) {
    await acknowledgeAlert(patientId, alertId);
    await loadAlerts();
    await loadDashboard();
    if (selectedId) await loadPatient(selectedId);
  }

  async function handleConsent(revoke) {
    setLoading(true);
    try {
      await updateConsent(selectedId, revoke);
      await loadPatient(selectedId);
      await reloadAll();
    } finally {
      setLoading(false);
    }
  }

  function handleDashboardSelectPatient(patientId) {
    setSelectedId(patientId);
  }

  function handleBackToDashboard() {
    setSelectedId(null);
    setSelectedPatient(null);
    reloadAll();
  }

  // Not logged in — show login page
  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const isClinician = user.role === "clinician";

  // Patient view — no sidebar, just their own chat
  if (!isClinician) {
    return (
      <div className="app">
        <div className="patient-topbar">
          <span className="patient-topbar-greeting">
            Signed in as <strong>{user.email}</strong>
          </span>
          <button className="btn-logout" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
        <ChatWindow
          patient={selectedPatient}
          onSend={handleSend}
          onTrigger={handleTrigger}
          onConsent={handleConsent}
          loading={loading}
          theme={theme}
          onToggleTheme={toggleTheme}
          role="patient"
        />
      </div>
    );
  }

  // Clinician view — Dashboard or Patient Chat
  const showingChat = selectedId && selectedPatient;

  return (
    <div className="app app-clinician">
      <div className="clinician-topbar">
        <div className="clinician-topbar-left">
          {showingChat && (
            <button className="btn-back" onClick={handleBackToDashboard}>
              ← Dashboard
            </button>
          )}
          {!showingChat && (
            <span className="clinician-topbar-title">AI Health Coach</span>
          )}
        </div>
        <div className="clinician-topbar-right">
          <span className="clinician-topbar-email">{user.email}</span>
          <button className="btn-logout" onClick={handleLogout}>Sign Out</button>
        </div>
      </div>
      {showingChat ? (
        <ChatWindow
          patient={selectedPatient}
          onSend={handleSend}
          onTrigger={handleTrigger}
          onConsent={handleConsent}
          loading={loading}
          theme={theme}
          onToggleTheme={toggleTheme}
          role="clinician"
          simDate={simDate}
          onDateChange={handleDateChange}
          onAcknowledgeAlert={handleAcknowledgeAlert}
          onBack={handleBackToDashboard}
        />
      ) : (
        <Dashboard
          data={dashboardData}
          onSelectPatient={handleDashboardSelectPatient}
          onAcknowledgeAlert={handleAcknowledgeAlert}
          onCreatePatient={handleCreate}
          onDeletePatient={handleDelete}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
      )}
    </div>
  );
}
