import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { Auth0Provider } from "@auth0/auth0-react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import theme from "./theme";

const domain = import.meta.env.VITE_AUTH0_DOMAIN;
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID;
const audience = import.meta.env.VITE_AUTH0_AUDIENCE;
const redirectUri = import.meta.env.VITE_AUTH0_REDIRECT_URI;

createRoot(document.getElementById("root")).render(
  <Auth0Provider
    domain={domain}
    clientId={clientId}
    authorizationParams={{
      audience: audience,
      redirect_uri: redirectUri,
      scope: "openid profile email",
    }}
    cacheLocation="localstorage"
    useRefreshTokens
  >
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <StrictMode>
        <App />
      </StrictMode>
    </ThemeProvider>
  </Auth0Provider>
);
