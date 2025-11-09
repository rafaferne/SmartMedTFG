import { useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";

/**
 * Lanza la pantalla de login (Auth0) SOLO la primera vez que el usuario
 * entra en la app. En visitas posteriores no hace nada.
 *
 * Si quieres desactivar el auto-login en local,
 * borra localStorage.sm_has_visited o ejecuta:
 *   localStorage.removeItem('sm_has_visited')
 */
export default function FirstVisitGate() {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0();

  useEffect(() => {
    if (isLoading) return;

    // Si ya está autenticado, no hacemos nada
    if (isAuthenticated) return;

    // ¿Es la primera visita?
    const hasVisited = localStorage.getItem("sm_has_visited");
    if (!hasVisited) {
      // Marcamos ANTES de redirigir para evitar bucles
      localStorage.setItem("sm_has_visited", "1");
      // Muestra la ventana de login/registro de Auth0 (hosted page)
      loginWithRedirect().catch(() => {
        // Si falla por cualquier motivo, permitimos que la app siga cargando
        // y el usuario podrá pulsar el botón de login manualmente.
      });
    }
  }, [isAuthenticated, isLoading, loginWithRedirect]);

  return null;
}
