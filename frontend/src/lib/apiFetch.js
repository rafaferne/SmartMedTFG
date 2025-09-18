// src/lib/apiFetch.js
import { useAuth0 } from "@auth0/auth0-react";

export function useApiFetch() {
  const { getAccessTokenSilently } = useAuth0();
  const API = import.meta.env.VITE_API_BASE;
  const AUD = import.meta.env.VITE_AUTH0_AUDIENCE;

  async function withToken(initFresh = false) {
    // initFresh = true fuerza token nuevo (salta cache)
    const opts = initFresh ? { cacheMode: "off" } : {};
    const token = await getAccessTokenSilently({
      authorizationParams: { audience: AUD },
      ...opts,
    });
    return token;
  }

  async function apiFetch(path, options = {}, retry = true) {
    const token = await withToken(false);
    let res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    // Si el token del cache estaba inválido/expirado, intenta una vez más con token fresco
    if (res.status === 401 && retry) {
      const fresh = await withToken(true);
      res = await fetch(`${API}${path}`, {
        ...options,
        headers: {
          Authorization: `Bearer ${fresh}`,
          "Content-Type": "application/json",
          ...(options.headers || {}),
        },
      });
    }
    return res;
  }

  return { apiFetch };
}
