import { AppBar, Toolbar, Typography, Button, Box } from "@mui/material";
import LocalHospitalIcon from "@mui/icons-material/LocalHospital";
import { useAuth0 } from "@auth0/auth0-react";

export default function Header() {
  const { isAuthenticated, loginWithRedirect, logout, user } = useAuth0();

  return (
    <AppBar position="sticky" color="inherit" elevation={0} sx={{ borderBottom: "1px solid #E0F2E9" }}>
      <Toolbar sx={{ gap: 2 }}>
        <Box
          sx={{
            width: 40, height: 40, borderRadius: "50%",
            bgcolor: "primary.main", color: "primary.contrastText",
            display: "grid", placeItems: "center",
          }}
        >
          <LocalHospitalIcon fontSize="small" />
        </Box>
        <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 800, color: "primary.dark" }}>
          SmartMed
        </Typography>

        {!isAuthenticated ? (
          <Button variant="contained" onClick={() => loginWithRedirect()}>Iniciar sesión</Button>
        ) : (
          <>
            <Typography variant="body2" sx={{ mr: 1 }}>
              {user?.name?.split(" ")[0] ?? "Usuario"}
            </Typography>
            <Button variant="outlined" color="secondary"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>
              Cerrar sesión
            </Button>
          </>
        )}
      </Toolbar>
    </AppBar>
  );
}
