// src/theme.js
import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#2FBF71",        // verde “mint” principal
      dark: "#1E9E5B",
      light: "#A8E6C7",
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#00A3A3",        // turquesa médico
    },
    background: {
      default: "#F5FBF7",     // fondo verdoso muy claro
      paper: "#ffffff",
    },
    success: { main: "#2E7D32" },
    info:    { main: "#0288D1" },
    warning: { main: "#EF6C00" },
    error:   { main: "#D32F2F" },
  },
  shape: { borderRadius: 16 }, // tarjetas suaves
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 999,     // pill buttons
          textTransform: "none",
          fontWeight: 600,
        },
      },
    },
    MuiTextField: {
      defaultProps: { variant: "outlined", fullWidth: true },
    },
    MuiCard: {
      styleOverrides: {
        root: { boxShadow: "0 8px 24px rgba(47,191,113,0.15)" },
      },
    },
  },
  typography: {
    fontFamily: `'Inter', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif`,
    h1: { fontWeight: 700 },
    h2: { fontWeight: 700 },
    h3: { fontWeight: 700 },
  },
});

export default theme;
