import { useState, useEffect, useCallback } from "react";
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
} from "./api";
import "./App.css";

export default function App() {
  const [patients, setPatients] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  const loadPatients = useCallback(async () => {
    const data = await fetchPatients();
    setPatients(data);
  }, []);

  const loadPatient = useCallback(async (id) => {
    const data = await fetchPatient(id);
    setSelectedPatient(data);
  }, []);

  useEffect(() => {
    loadPatients();
  }, [loadPatients]);

  useEffect(() => {
    if (selectedId) loadPatient(selectedId);
  }, [selectedId, loadPatient]);

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
    // Optimistic update — show user message immediately
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

  return (
    <div className="app">
      <Sidebar
        patients={patients}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCreate={handleCreate}
        onDelete={handleDelete}
      />
      <ChatWindow
        patient={selectedPatient}
        onSend={handleSend}
        onTrigger={handleTrigger}
        onConsent={handleConsent}
        loading={loading}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    </div>
  );
}
