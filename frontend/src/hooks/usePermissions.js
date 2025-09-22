import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useApiFetch } from "../lib/apiFetch";

export function usePermissions() {
  const { isAuthenticated } = useAuth0();
  const { apiFetch } = useApiFetch();
  const [perms, setPerms] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ignore = false;
    (async () => {
      if (!isAuthenticated) { setPerms([]); setLoading(false); return; }
      setLoading(true);
      try {
        const res = await apiFetch("/me/permissions");
        if (res.ok) {
          const data = await res.json();
          if (!ignore) setPerms(data.permissions || []);
        } else {
          if (!ignore) setPerms([]);
        }
      } catch {
        if (!ignore) setPerms([]);
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => { ignore = true; };
  }, [isAuthenticated]);

  const has = (...required) => required.every(p => perms.includes(p));
  const hasAny = (...candidates) => candidates.some(p => perms.includes(p));

  return { perms, has, hasAny, loading };
}
