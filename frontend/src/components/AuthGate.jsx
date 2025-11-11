import { useAuth0 } from "@auth0/auth0-react";
import {
  Box, Card, CardContent, Typography, Button, Stack, Divider, Chip, Tooltip
} from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";

export default function AuthGate() {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0();

  if (isLoading) return null;   // evita parpadeos
  if (isAuthenticated) return null;

  return (
    <Box
      sx={{
        position: "fixed",
        inset: 0,
        zIndex: 2000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #f6f9fc 0%, #eef2f7 100%)",
        p: 2,
      }}
    >
      <Card
        elevation={0}
        sx={{
          width: "100%",
          maxWidth: 560,
          borderRadius: 4,
          boxShadow: "0 12px 40px rgba(0,0,0,0.12)",
          overflow: "hidden",
          backdropFilter: "saturate(140%) blur(6px)",
        }}
      >
        {/* Header */}
        <Box
          sx={{
            px: { xs: 3, sm: 4 },
            pt: { xs: 3.5, sm: 4 },
            pb: 2,
            textAlign: "center",
          }}
        >
          <Stack spacing={1.2} alignItems="center">
            <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: 0.2 }}>
              Bienvenido a SmartMed
            </Typography>

            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 420 }}>
              Inicia sesión o regístrate para continuar y acceder a tus métricas, simulaciones y cargas de datos.
            </Typography>

            <Chip
              icon={<LockRoundedIcon />}
              label="Acceso seguro"
              size="small"
              sx={{
                mt: 0.5,
                background: "#e8f0fe",
                color: "#1f3a93",
                "& .MuiChip-icon": { color: "#1f3a93" },
                fontWeight: 600,
              }}
            />
          </Stack>
        </Box>

        <Divider />

        {/* Body */}
        <CardContent sx={{ px: { xs: 3, sm: 4 }, py: 3 }}>
          {/* Mini ventajas */}
          <Stack
            spacing={1.2}
            sx={{ mb: 2.5 }}
            alignItems="center"
          >
            <Feature text="Valoraciones diarias con IA (sueño, estrés, actividad)" />
            <Feature text="Simulaciones con gemelo digital y consejos personalizados" />
            <Feature text="Subida de CSV y fusión automática de datos" />
          </Stack>

          {/* Botones de acción */}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mt: 1 }}>
            <Button
              fullWidth
              variant="contained"
              size="large"
              startIcon={<LoginIcon />}
              aria-label="Iniciar sesión"
              onClick={() => loginWithRedirect()}
              sx={{
                borderRadius: 2.5,
                textTransform: "none",
                fontWeight: 700,
                py: 1.2,
                boxShadow: "none",
                "&:hover": { boxShadow: "0 6px 16px rgba(0,0,0,0.12)" },
              }}
            >
              Iniciar sesión
            </Button>

            <Button
              fullWidth
              variant="outlined"
              size="large"
              startIcon={<PersonAddIcon />}
              aria-label="Registrarse"
              onClick={() =>
                loginWithRedirect({
                  authorizationParams: { screen_hint: "signup" },
                })
              }
              sx={{
                borderRadius: 2.5,
                textTransform: "none",
                fontWeight: 700,
                py: 1.2,
                borderWidth: 2,
                "&:hover": { borderWidth: 2 },
              }}
            >
              Registrarse
            </Button>
          </Stack>

          {/* Separador “o” */}
          <Stack direction="row" alignItems="center" spacing={2} sx={{ my: 2.5 }}>
            <Divider sx={{ flex: 1 }} />
            <Typography variant="caption" color="text.secondary">o</Typography>
            <Divider sx={{ flex: 1 }} />
          </Stack>

          {/* Tip */}
          <Tooltip
            title="Usa tu cuenta habitual. Puedes completar tu perfil más tarde desde el apartado Perfil."
            placement="top"
            arrow
          >
            <Typography
              variant="body2"
              color="text.secondary"
              align="center"
              sx={{ maxWidth: 460, mx: "auto" }}
            >
              ¿Primera vez? Elige “Registrarse”. Si ya tienes cuenta, usa “Iniciar sesión”.
            </Typography>
          </Tooltip>
        </CardContent>

        <Divider />

        {/* Footer */}
        <Box sx={{ px: { xs: 3, sm: 4 }, py: 2 }}>
          <Typography variant="caption" color="text.secondary" align="center" display="block">
            Al continuar, aceptas nuestras condiciones de uso y la política de privacidad.
          </Typography>
        </Box>
      </Card>
    </Box>
  );
}

/** Item de lista de ventajas con icono y centrado */
function Feature({ text }) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ color: "text.secondary" }}>
      <CheckCircleRoundedIcon fontSize="small" />
      <Typography variant="body2" sx={{ textAlign: "center" }}>
        {text}
      </Typography>
    </Stack>
  );
}
