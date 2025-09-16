import { useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";

const API = import.meta.env.VITE_API_BASE;
const AUD = import.meta.env.VITE_AUTH0_AUDIENCE;

export default function SyncOnLogin({ onSynced }) {
  const { isAuthenticated, user, getAccessTokenSilently } = useAuth0();

  useEffect(() => {
    if (!isAuthenticated) return;
    (async () => {
      try {
        const token = await getAccessTokenSilently({
          authorizationParams: { audience: AUD },
        });
        await fetch(`${API}/me/sync`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email: user?.email,
            name: user?.name,
            picture: user?.picture,
          }),
        });
        onSynced?.();
      } catch (e) {
        console.error("Sync error:", e);
      }
    })();
  }, [isAuthenticated]);

  return null;
}