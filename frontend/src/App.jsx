import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import Header from "./components/header.jsx";
import SyncOnLogin from "./components/SyncOnLogin.jsx";
import OnboardingForm from "./components/FormRegistro.jsx";
import { useProfile } from "./hooks/useProfile.js";
import { Container, Box, Button, Card, CardContent, Typography, Stack, Alert } from "@mui/material";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";
import UserProfileCard from "./components/userProfileCard.jsx";
import { usePermissions } from "./hooks/usePermissions.js";
import { useApiFetch } from "./lib/apiFetch.js";
import MetricsChart from "./components/MetricsChart.jsx";
import SleepScorer from "./components/SleepScorer.jsx";
import ActivityScorer from "./components/ActivityScorer.jsx";

const API = import.meta.env.VITE_API_BASE;

export default function App() {
  const { isAuthenticated, loginWithRedirect, getAccessTokenSilently } = useAuth0();
  const { profile, setProfile, loading, refresh } = useProfile();
  const { has, hasAny, loading: permsLoading } = usePermissions();
  const { apiFetch } = useApiFetch();
  const [apiMsg, setApiMsg] = useState("");
  const [chartReload, setChartReload] = useState(0);

  const callPublic = async () => {
    const res = await fetch(`${API}/ping`);
    setApiMsg(JSON.stringify(await res.json(), null, 2));
  };

  const callPrivate = async () => {
    try {
      const res = await apiFetch("/user");
      const data = await res.json();
      setApiMsg(JSON.stringify(data, null, 2));
    } catch (e) {
      setApiMsg(String(e?.message || e));
    }
  };

  return (
    <>
      <Header />
      <SyncOnLogin onSynced={refresh} />

      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <HealthAndSafetyIcon color="primary" />
          <Typography variant="h4" color="primary.dark">Panel de SmartMed</Typography>
        </Stack>

        {!isAuthenticated && (
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>Bienvenido</Typography>
              <Typography variant="body1" sx={{ mb: 2 }}>
                Inicia sesión para ver o completar tu perfil médico.
              </Typography>
              <Button variant="contained" onClick={() => loginWithRedirect()}>Iniciar sesión</Button>
            </CardContent>
          </Card>
        )}

        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <Button variant="outlined" onClick={callPublic}>Ping público</Button>
          <Button variant="contained" onClick={callPrivate} disabled={!isAuthenticated}>
            Llamar /user (protegido)
          </Button>
          {isAuthenticated && !permsLoading && has("read:users") && (
            <Button variant="outlined">Panel Admin</Button>
          )}
          {isAuthenticated && !permsLoading && hasAny("read:reports", "read:users") && (
            <Button variant="text">Ver informes</Button>
          )}
        </Stack>

        {loading ? (
          <Alert severity="info">Cargando perfil…</Alert>
        ) : isAuthenticated ? (
          profile?.profileComplete ? (
          <>
            <UserProfileCard doc={profile} onUpdated={setProfile} />
            <MetricsChart reloadToken={chartReload} />
            {/* Formularios de puntuación (guardan y refrescan la serie) */}
            <SleepScorer onScored={() => setChartReload(v => v + 1)} />
            <ActivityScorer onScored={() => setChartReload(v => v + 1)} />
          </>
          ) : (
            <OnboardingForm onDone={(u) => setProfile(u)} />
          )
        ) : null}

        {apiMsg && (
          <Box component="pre" sx={{ mt: 3, bgcolor: "#EEF8F2", p: 2, borderRadius: 2 }}>
            {apiMsg}
          </Box>
        )}
      </Container>
    </>
  );
}
