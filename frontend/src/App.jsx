import { useState, useEffect, useCallback } from "react";
import LoginPage from "./components/LoginPage";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import {
  fetchPatients,
  fetchPatient,
  createPatient,
  deletePatient,
  sendMessage,
  triggerCheckin,
  updateConsent,
  getSimDate,
  setSimDate,
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
      }
    }
  }, [user, loadPatients]);

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

  async function handleCreate(formData) {
    setLoading(true);
    try {
      await createPatient(formData);
      await loadPatients();
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
    await loadPatients();
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
      await loadPatients();
    } finally {
      setLoading(false);
    }
  }

  async function handleTrigger(type) {
    setLoading(true);
    try {
      await triggerCheckin(selectedId, type);
      await loadPatient(selectedId);
      await loadPatients();
    } finally {
      setLoading(false);
    }
  }

  async function handleDateChange(date) {
    setLoading(true);
    try {
      await setSimDate(date);
      setSimDateState(date);
      // Reload everything — reminders may have fired
      await loadPatients();
      if (selectedId) await loadPatient(selectedId);
    } finally {
      setLoading(false);
    }
  }

  async function handleConsent(revoke) {
    setLoading(true);
    try {
      await updateConsent(selectedId, revoke);
      await loadPatient(selectedId);
      await loadPatients();
    } finally {
      setLoading(false);
    }
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

  // Clinician view — full dashboard
  return (
    <div className="app">
      <Sidebar
        patients={patients}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCreate={handleCreate}
        onDelete={handleDelete}
        onLogout={handleLogout}
        userEmail={user.email}
      />
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
      />
    </div>
  );
}
