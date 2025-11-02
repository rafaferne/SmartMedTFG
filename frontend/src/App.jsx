import { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./layout/Layout.jsx";
import SyncOnLogin from "./components/SyncOnLogin.jsx";
import { useAuth0 } from "@auth0/auth0-react";
import { Container, Alert, Tabs, Tab, Box } from "@mui/material";
import UserProfileCard from "./components/userProfileCard.jsx";
import OnboardingForm from "./components/FormRegistro.jsx";
import { useProfile } from "./hooks/useProfile.js";
import MetricsTabs from "./components/MetricsTabs.jsx";
import SimulationRadar from "./components/SimulationRadar.jsx";
import SimulateInterventions from "./components/SimulateInterventions.jsx";

const METRICS = [
  { value: "sleep",    label: "Sueño" },
  { value: "activity", label: "Actividad física" },
  { value: "stress",   label: "Estrés" },
];

function Dashboard() {
  return (
    <Container maxWidth="lg">
      <Alert severity="success">Bienvenido a SmartMed</Alert>
    </Container>
  );
}

function Perfil() {
  const { isAuthenticated } = useAuth0();
  const { profile, setProfile, loading } = useProfile();
  if (!isAuthenticated) return <Alert severity="info">Inicia sesión para ver tu perfil.</Alert>;
  if (loading) return <Alert severity="info">Cargando…</Alert>;
  return profile?.profileComplete
    ? <UserProfileCard doc={profile} onUpdated={setProfile} />
    : <OnboardingForm onDone={(u) => setProfile(u)} />;
}

function Metricas() {
  // La vista de métricas queda igual que estaba: MetricsTabs se encarga de todo
  return (
    <Container maxWidth="lg">
      <MetricsTabs />
    </Container>
  );
}

function Simulacion() {
  // ✅ En simulación ya no usamos MetricsTabs (que pintaba gráficas/tablas de métricas)
  //    Solo pestañas locales para elegir la métrica activa y mostrar Radar + Simulación.
  const [activeMetric, setActiveMetric] = useState("sleep");
  const [reload, setReload] = useState(0);

  // pestañas locales (solo sleep / stress para simulación)
  const simTabs = [
    { value: "sleep",  label: "Sueño" },
    { value: "stress", label: "Estrés" },
  ];

  const handleTab = (_e, v) => { if (v !== null) setActiveMetric(v); };

  return (
    <Container maxWidth="lg">
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs
          value={activeMetric}
          onChange={handleTab}
          variant="scrollable"
          scrollButtons="auto"
        >
          {simTabs.map(t => (
            <Tab key={t.value} value={t.value} label={t.label} />
          ))}
        </Tabs>
      </Box>

      {/* 🔵 Malla radar de simulación: solo métricas de simulación */}
      <SimulationRadar
        metrics={simTabs.map(m => m.value)}   // ["sleep","stress"]
        reloadToken={reload}
        activeMetric={activeMetric}
        onReset={() => setReload(v => v + 1)}
      />

      {/* 🟣 Tarjeta para lanzar simulación del histórico de la métrica activa */}
      <SimulateInterventions
        metric={activeMetric}
        title={`Simulación — ${simTabs.find(x => x.value === activeMetric)?.label || activeMetric}`}
        onDone={() => setReload(v => v + 1)}
      />
    </Container>
  );
}

function Admin() { return <Alert severity="info">Zona admin.</Alert>; }
function NotFound() { return <Alert severity="warning">Página no encontrada</Alert>; }

export default function App() {
  return (
    <BrowserRouter>
      <SyncOnLogin />
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/perfil" element={<Perfil />} />
          <Route path="/metricas" element={<Metricas />} />
          <Route path="/simulacion" element={<Simulacion />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
