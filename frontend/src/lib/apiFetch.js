// src/lib/apiFetch.js
import { useAuth0 } from "@auth0/auth0-react";

export function useApiFetch() {
  const { getAccessTokenSilently } = useAuth0();
  const API = import.meta.env.VITE_API_BASE || "http://localhost:5000/api";
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

  function buildRequest(url, options, token) {
    const opts = options || {};
    const isForm = opts.body instanceof FormData;

    // Partimos de los headers del caller
    const headersFromCaller = opts.headers ? { ...opts.headers } : {};

    // Si es FormData NO seteamos Content-Type: el navegador pondrá el boundary correcto
    const baseHeaders = {
      ...headersFromCaller,
      Authorization: `Bearer ${token}`,
      ...(isForm ? {} : { "Content-Type": "application/json" }),
    };

    // Body: si es FormData lo pasamos tal cual; si es objeto -> JSON.stringify
    let body = opts.body;
    if (!isForm && body && typeof body === "object" && !(body instanceof Blob)) {
      body = JSON.stringify(body);
    }

    return [
      url,
      {
        ...opts,
        headers: baseHeaders,
        body: body,
      },
    ];
  }

  async function apiFetch(path, options = {}, retry = true) {
    const token = await withToken(false);
    const url = `${API}${path}`;

    // Primera llamada
    let [reqUrl, reqInit] = buildRequest(url, options, token);
    let res = await fetch(reqUrl, reqInit);

    // Si el token del cache estaba inválido/expirado, reintenta una vez con token fresco
    if (res.status === 401 && retry) {
      const fresh = await withToken(true);
      [reqUrl, reqInit] = buildRequest(url, options, fresh);
      res = await fetch(reqUrl, reqInit);
    }

    return res;
  }

  return { apiFetch };
}
