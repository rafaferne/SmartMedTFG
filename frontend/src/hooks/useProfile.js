import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";

const API = import.meta.env.VITE_API_BASE;
const AUD = import.meta.env.VITE_AUTH0_AUDIENCE;

export function useProfile() {
  const { isAuthenticated, getAccessTokenSilently } = useAuth0();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    if (!isAuthenticated) { setProfile(null); setLoading(false); return; }
    setLoading(true);
    try {
      const token = await getAccessTokenSilently({
        authorizationParams: { audience: AUD },
      });
      const res = await fetch(`${API}/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setProfile(data);
    } catch (e) {
      console.error("Load profile error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [isAuthenticated]);
  return { profile, setProfile, loading, refresh };
}
