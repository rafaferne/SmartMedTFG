import { useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useApiFetch } from "../lib/apiFetch";

export default function SyncOnLogin({ onSynced }) {
  const { isAuthenticated, user } = useAuth0();
  const { apiFetch } = useApiFetch();

  useEffect(() => {
    if (!isAuthenticated) return;

    (async () => {
      try {
        await apiFetch("/me/sync", {
          method: "POST",
          body: JSON.stringify({
            email: user?.email ?? null,
            name: user?.name ?? null,
            picture: user?.picture ?? null,
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
