import { useState } from "react";
import { BrowserRouter, Routes, Route, Link as RouterLink } from "react-router-dom";
import Layout from "./layout/Layout.jsx";
import SyncOnLogin from "./components/SyncOnLogin.jsx";
import { useAuth0 } from "@auth0/auth0-react";
import {
  Container, Alert, Tabs, Tab, Box,
  Grid, Card, CardActionArea, CardContent, Typography, Stack
} from "@mui/material";
import PersonIcon from "@mui/icons-material/Person";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import AutoGraphIcon from "@mui/icons-material/AutoGraph";

import UserProfileCard from "./components/userProfileCard.jsx";
import OnboardingForm from "./components/FormRegistro.jsx";
import { useProfile } from "./hooks/useProfile.js";
import MetricsTabs from "./components/MetricsTabs.jsx";
import SimulationRadar from "./components/SimulationRadar.jsx";
import SimulateInterventions from "./components/SimulateInterventions.jsx";
import AuthGate from "./components/AuthGate.jsx"; // bloquea la app si no hay login

const METRICS = [
  { value: "sleep",  label: "Sueño" },
  { value: "stress", label: "Estrés" },
  { value: "activity", label: "Actividad física" },
];

function Dashboard() {
  const cards = [
    {
      title: "Perfil",
      desc: "Consulta o completa tu información personal para mejorar las recomendaciones de la IA.",
      icon: <PersonIcon sx={{ fontSize: 48 }} />,
      to: "/perfil",
      color: "linear-gradient(135deg, #e8f5e9, #d0f0d8)",
    },
    {
      title: "Métricas",
      desc: "Sube tus CSV y consulta las valoraciones diarias de la IA sobre sueño, estrés y actividad.",
      icon: <ShowChartIcon sx={{ fontSize: 48 }} />,
      to: "/metricas",
      color: "linear-gradient(135deg, #e3f2fd, #d0e6ff)",
    },
    {
      title: "Simulación",
      desc: "Genera tu gemelo digital y observa cómo mejoran tus resultados con las intervenciones sugeridas.",
      icon: <AutoGraphIcon sx={{ fontSize: 48 }} />,
      to: "/simulacion",
      color: "linear-gradient(135deg, #fff3e0, #ffe0b2)",
    },
  ];

  return (
    <Container
      maxWidth="lg"
      sx={{
        minHeight: "calc(100vh - 120px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        py: 6,
      }}
    >
      <Grid
        container
        spacing={6}
        justifyContent="center"
        alignItems="center"
      >
        {cards.map((card) => (
          <Grid key={card.title} item xs={12} sm={6} md={4}>
            <Card
              component={RouterLink}
              to={card.to}
              sx={{
                textDecoration: "none",
                borderRadius: 6,
                p: 6,
                height: 500,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 10px 25px rgba(0,0,0,0.08)",
                transition: "all 0.25s ease",
                "&:hover": {
                  transform: "translateY(-4px)",
                  boxShadow: "0 14px 30px rgba(0,0,0,0.12)",
                },
              }}
            >
              {/* Icono dentro del recuadro */}
              <Box
                sx={{
                  width: 100,
                  height: 80,
                  borderRadius: 4,
                  background: card.color,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  mb: 3,
                }}
              >
                {card.icon}
              </Box>

              {/* Título */}
              <Typography
                variant="h5"
                sx={{ fontWeight: 700, mb: 1, textAlign: "center" }}
              >
                {card.title}
              </Typography>

              {/* Descripción */}
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                  textAlign: "center",
                  px: 2,
                  maxWidth: 250,
                }}
              >
                {card.desc}
              </Typography>
            </Card>
          </Grid>
        ))}
      </Grid>
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
  return (
    <Container maxWidth="lg">
      <MetricsTabs />
    </Container>
  );
}

function Simulacion() {
  const [activeMetric, setActiveMetric] = useState("sleep");
  const [reload, setReload] = useState(0);

  const simTabs = [
    { value: "sleep",  label: "Sueño" },
    { value: "stress", label: "Estrés" },
    { value: "activity", label: "Actividad física" },
  ];
  const handleTab = (_e, v) => { if (v !== null) setActiveMetric(v); };

  return (
    <Container maxWidth="lg">
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs value={activeMetric} onChange={handleTab} variant="scrollable" scrollButtons="auto">
          {simTabs.map(t => (<Tab key={t.value} value={t.value} label={t.label} />))}
        </Tabs>
      </Box>

      <SimulationRadar
        metrics={simTabs.map(m => m.value)}
        reloadToken={reload}
        activeMetric={activeMetric}
        onReset={() => setReload(v => v + 1)}
      />

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
      <AuthGate />      {/* bloquea toda la app si no hay login */}
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
