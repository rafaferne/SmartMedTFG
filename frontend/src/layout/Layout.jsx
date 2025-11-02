import { useEffect, useMemo, useRef, useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import {
  AppBar, Toolbar, IconButton, Typography, Drawer, List, ListItemButton,
  ListItemText, Box, Divider, CssBaseline, useMediaQuery, Button
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import CloseIcon from "@mui/icons-material/Close";
import LogoutIcon from "@mui/icons-material/Logout";
import HomeIcon from "@mui/icons-material/Home";
import PersonIcon from "@mui/icons-material/Person";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import InsightsIcon from "@mui/icons-material/Insights";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";
import { useAuth0 } from "@auth0/auth0-react";
import { usePermissions } from "../hooks/usePermissions";

const drawerWidth = 260;

export default function Layout() {
  const isDesktop = useMediaQuery("(min-width:900px)");
  const [open, setOpen] = useState(false);
  const initialized = useRef(false);

  const { isAuthenticated, loginWithRedirect, logout } = useAuth0();
  const { has, loading: permsLoading } = usePermissions();
  const navigate = useNavigate();

  // Inicializa (solo 1 vez): abierto en desktop, cerrado en móvil
  useEffect(() => {
    if (!initialized.current) {
      setOpen(isDesktop);
      initialized.current = true;
    }
  }, [isDesktop]);

  const items = useMemo(() => {
    const base = [
      { to: "/", label: "Inicio", icon: <HomeIcon /> },
      { to: "/perfil", label: "Perfil", icon: <PersonIcon /> },
      { to: "/metricas", label: "Métricas", icon: <MonitorHeartIcon /> },
      { to: "/simulacion", label: "Simulación", icon: <InsightsIcon /> },
    ];
    if (isAuthenticated && !permsLoading && has("read:users")) {
      base.push({ to: "/admin", label: "Admin", icon: <AdminPanelSettingsIcon /> });
    }
    return base;
  }, [isAuthenticated, permsLoading, has]);

  const drawerContent = (
    <Box role="presentation" sx={{ width: drawerWidth }}>
      {/* Espaciador para no quedar bajo el AppBar */}
      <Toolbar />
      {/* Solo botón de cerrar dentro del menú (sin título SmartMed aquí) */}
      <Divider />
      <List sx={{ py: 0 }}>
        {items.map((it) => (
          <ListItemButton
            key={it.to}
            component={NavLink}
            to={it.to}
            onClick={() => !isDesktop && setOpen(false)}
            sx={{ "&.active": { bgcolor: "action.selected" } }}
          >
            {it.icon}
            <ListItemText primary={it.label} sx={{ ml: 1 }} />
          </ListItemButton>
        ))}
      </List>
      <Divider sx={{ my: 1 }} />
      <Box sx={{ p: 2, display: "flex", gap: 1 }}>
        {!isAuthenticated ? (
          <Button fullWidth variant="contained" onClick={() => loginWithRedirect()}>
            Iniciar sesión
          </Button>
        ) : (
          <Button
            fullWidth
            variant="outlined"
            color="error"
            startIcon={<LogoutIcon />}
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            Cerrar sesión
          </Button>
        )}
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: "flex" }}>
      <CssBaseline />

      {/* Barra superior */}
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          bgcolor: "#e6f5eb",
          color: "#145a32",
          borderBottom: "1px solid rgba(0,0,0,0.08)",
          zIndex: (theme) => theme.zIndex.drawer + 1,
        }}
      >
        <Toolbar>
          {/* Botón hamburguesa */}
          <IconButton color="inherit" edge="start" onClick={() => setOpen(o => !o)} sx={{ mr: 1 }}>
            <MenuIcon />
          </IconButton>

          {/* Icono verde con cruz (HealthAndSafety) */}
          <HealthAndSafetyIcon
            sx={{ color: "#1e8449", mr: 1 }}
            fontSize="medium"
            aria-label="Icono salud"
          />

          {/* Título principal arriba (mantener) */}
          <Typography variant="h6" sx={{ flexGrow: 1, cursor: "pointer" }} onClick={() => navigate("/")}>
            SmartMed
          </Typography>
        </Toolbar>
      </AppBar>

      {/* Drawer: persistente en desktop, temporal en móvil */}
      <Drawer
        variant={isDesktop ? "persistent" : "temporary"}
        anchor="left"
        open={open}
        onClose={() => setOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          "& .MuiDrawer-paper": {
            width: drawerWidth,
            boxSizing: "border-box",
            borderRight: "1px solid rgba(0,0,0,0.08)",
          }
        }}
      >
        {drawerContent}
      </Drawer>

      {/* Contenido principal */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          transition: "margin-left 150ms ease",
          ...(isDesktop && open ? { ml: `${drawerWidth}px` } : { ml: 0 }),
        }}
      >
        {/* Espaciador para no quedar bajo el AppBar */}
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
