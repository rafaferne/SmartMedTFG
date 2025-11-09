import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useApiFetch } from "../lib/apiFetch";

export function useProfile() {
  const { isAuthenticated } = useAuth0();
  const { apiFetch } = useApiFetch();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    if (!isAuthenticated) {
      setProfile(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const res = await apiFetch("/me");

      if (res.ok) {
        const data = await res.json();
        // ⚠️ Soporta las dos formas de respuesta:
        //  - { ok: true, user: { ... } }
        //  - { ok: true, ...camposUsuario }
        const user = data.user || data;
        setProfile(user);
      } else if (res.status === 401) {
        console.warn("401 en /me; vuelve a iniciar sesión si persiste.");
      } else if (res.status === 404) {
        console.warn("Perfil no encontrado en backend; probablemente es la primera vez que entras.");
        setProfile(null);
      } else {
        console.error("Error /me:", res.status);
      }
    } catch (e) {
      console.error("Load profile error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [isAuthenticated]);

  return { profile, setProfile, loading, refresh };
}
