import { AppBar, Toolbar, Typography, Button, Box, Avatar } from "@mui/material";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";
import { useAuth0 } from "@auth0/auth0-react";

export default function Header() {
  const { isAuthenticated, loginWithRedirect, logout, user } = useAuth0();

  const firstName = (user?.name || "").split(" ")[0] || "Usuario";

  return (
    <AppBar position="static" elevation={0}>
      <Toolbar sx={{ gap: 2 }}>
        <HealthAndSafetyIcon />
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          SmartMed
        </Typography>

        {!isAuthenticated ? (
          <Button
            variant="contained"
            onClick={() => loginWithRedirect()}
          >
            Iniciar sesión
          </Button>
        ) : (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Avatar
              src={user?.picture || undefined}
              alt={user?.name || "Usuario"}
              sx={{ width: 32, height: 32 }}
            />
            <Typography variant="body2">{firstName}</Typography>
            <Button
              variant="outlined"
              color="error"
              onClick={() =>
                logout({ logoutParams: { returnTo: window.location.origin } })
              }
            >
              Cerrar sesión
            </Button>
          </Box>
        )}
      </Toolbar>
    </AppBar>
  );
}
