import { useState } from "react";
import { Card, CardHeader, CardContent, CardActions, Button, Alert, LinearProgress, Typography } from "@mui/material";
import { useApiFetch } from "../lib/apiFetch";

export default function StressScorer() {
  const { apiFetch } = useApiFetch();
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const runBulk = async () => {
    setLoading(true); setMsg(null);
    try {
      const res = await apiFetch("/ai/score/stress/from_csv/bulk_llm", { method: "POST" });
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "No se pudo ejecutar el scoring");
      const s = json.summary || {};
      setMsg({ type: "success", text: `Filas: ${s.total_rows||0} · Escritas: ${s.written_measurements||0} · Errores LLM: ${s.llm_errors||0}` });
    } catch (e) {
      setMsg({ type: "error", text: String(e?.message || e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ mt: 2 }}>
      <CardHeader title="Valorar Estrés con IA (lote)" subheader="Genera la puntuación (1–5) y consejo para cada día del CSV de estrés." />
      <CardContent>
        {loading && <LinearProgress sx={{ mb: 2 }}/>}
        {msg && <Alert severity={msg.type} sx={{ mb: 1, whiteSpace:"pre-wrap" }}>{msg.text}</Alert>}
        <Typography variant="caption" color="text.secondary">
          Requiere LLM_API_KEY en el servidor. Escribe en la colección <i>measurements</i> con type=stress.
        </Typography>
      </CardContent>
      <CardActions>
        <Button variant="contained" disabled={loading} onClick={runBulk}>Valorar todo</Button>
      </CardActions>
    </Card>
  );
}
