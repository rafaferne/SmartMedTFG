import { useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Button, Stack, Typography, Alert, LinearProgress, Divider
} from "@mui/material";
import { useApiFetch } from "../lib/apiFetch";

export default function SimulateInterventions({
  metric = "sleep",
  title = "Simulación",
  onDone,
}) {
  const { apiFetch } = useApiFetch();
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [last, setLast] = useState(null);

  const runSimulation = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await apiFetch(`/ai/simulate/${encodeURIComponent(metric)}`, {
        method: "POST",
        body: { scope: "all" },
      });
      const json = await res.json();

      if (!res.ok || json.ok === false) {
        setLast(null);
        setMsg({
          type: "error",
          text: json.error || "Error generando simulación (IA)",
        });
        return;
      }

      setLast(json);
      setMsg({ type: "success", text: "Simulación generada con intervención de la IA." });
      onDone?.(json);
    } catch (e) {
      setMsg({ type: "error", text: String(e.message || e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title={title}
        subheader="Genera una simulación alineada a cada fecha/hora con datos reales (sólo con intervenciones de IA)."
      />
      <CardContent>
        {loading && <LinearProgress sx={{ mb: 2 }} />}
        {msg && <Alert severity={msg.type} sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{msg.text}</Alert>}

        {last ? (
          <Stack spacing={1} sx={{ mb: 1 }}>
            {last.forecast_mode === "absolute_ts" && (
              <Typography variant="body2" color="text.secondary">
                Rango simulado: {new Date(last.start_ts).toLocaleString()} — {new Date(last.end_ts).toLocaleString()}
              </Typography>
            )}

            <Divider sx={{ my: 1 }} />
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Aún no has generado una simulación para “{metric}”.
          </Typography>
        )}
      </CardContent>
      <CardActions>
        <Button variant="contained" onClick={runSimulation} disabled={loading}>
          Generar simulación (todo el histórico)
        </Button>
      </CardActions>
    </Card>
  );
}
