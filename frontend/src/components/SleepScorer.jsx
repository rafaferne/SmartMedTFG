import { useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Grid, TextField, MenuItem, Button, Alert
} from "@mui/material";
import { useApiFetch } from "../lib/apiFetch";

const QUALITY = [
  { value: 1, label: "1 (fatal)" },
  { value: 2, label: "2" },
  { value: 3, label: "3" },
  { value: 4, label: "4" },
  { value: 5, label: "5 (perfecto)" },
];

export default function SleepScorer({ onScored }) {
  const { apiFetch } = useApiFetch();
  const [form, setForm] = useState({
    hours: "",
    awakenings: "",
    deep_minutes: "",
    rem_minutes: "",
    quality: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  const ch = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    
    try {
      const payload = {
        hours: form.hours !== "" ? Number(form.hours) : null,
        awakenings: form.awakenings !== "" ? Number(form.awakenings) : null,
        deep_minutes: form.deep_minutes !== "" ? Number(form.deep_minutes) : null,
        rem_minutes: form.rem_minutes !== "" ? Number(form.rem_minutes) : null,
        quality: form.quality !== "" ? Number(form.quality) : null,
        notes: form.notes || "",
      };

      const res = await apiFetch("/ai/score/sleep", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok || data.ok === false) {
        if (res.status === 429) {
          const secs = data.retry_after ?? 10;
          throw new Error(`Servicio limitado. Prueba de nuevo en ~${Math.ceil(secs)}s.`);
        }
        throw new Error(data.error || "Error en el servicio de evaluación");
      }

      setMsg({ type: "success", text: `Sueño = ${data.score}/5. ${data.rationale || ""}` });
      onScored?.(); // pídele a la gráfica que recargue
    } catch (err) {
      setMsg({ type: "error", text: String(err.message || err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader title="Calcular puntuación de Sueño (1–5)" />
      <CardContent>
        {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}
        <form id="sleepForm" onSubmit={submit}>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Horas dormidas"
                name="hours"
                type="number"
                inputProps={{ step: 0.1, min: 0, max: 14 }}
                value={form.hours}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Despertares"
                name="awakenings"
                type="number"
                inputProps={{ step: 1, min: 0, max: 20 }}
                value={form.awakenings}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Min. profundo"
                name="deep_minutes"
                type="number"
                inputProps={{ step: 1, min: 0, max: 600 }}
                value={form.deep_minutes}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Min. REM"
                name="rem_minutes"
                type="number"
                inputProps={{ step: 1, min: 0, max: 600 }}
                value={form.rem_minutes}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                select
                label="Calidad subjetiva"
                name="quality"
                value={form.quality}
                onChange={ch}
                fullWidth
              >
                <MenuItem value="">(sin dato)</MenuItem>
                {QUALITY.map(q => <MenuItem key={q.value} value={q.value}>{q.label}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={8}>
              <TextField
                label="Notas"
                name="notes"
                value={form.notes}
                onChange={ch}
                fullWidth
                multiline
                minRows={2}
              />
            </Grid>
          </Grid>
        </form>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Button type="submit" form="sleepForm" variant="contained" disabled={saving}>
          {saving ? "Calculando..." : "Calcular y guardar"}
        </Button>
      </CardActions>
    </Card>
  );
}
