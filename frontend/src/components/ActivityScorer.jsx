import { useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Grid, TextField, MenuItem, Button, Alert
} from "@mui/material";
import { useApiFetch } from "../lib/apiFetch";

const INTENSITY = [
  { value: "low", label: "Baja" },
  { value: "moderate", label: "Moderada" },
  { value: "vigorous", label: "Vigorosa" },
];

export default function ActivityScorer({ onScored }) {
  const { apiFetch } = useApiFetch();
  const [form, setForm] = useState({
    minutes: "",
    intensity: "moderate",
    steps: "",
    hr_zone_minutes: "",
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
        minutes: form.minutes !== "" ? Number(form.minutes) : null,
        intensity: form.intensity || "moderate",
        steps: form.steps !== "" ? Number(form.steps) : null,
        hr_zone_minutes: form.hr_zone_minutes !== "" ? Number(form.hr_zone_minutes) : null,
        notes: form.notes || "",
      };

      const res = await apiFetch("/ai/score/activity", {
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
      
      setMsg({ type: "success", text: `Actividad = ${data.score}/5. ${data.rationale || ""}` });
      onScored?.(); // recarga la serie en la gráfica
    } catch (err) {
      setMsg({ type: "error", text: String(err.message || err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader title="Calcular puntuación de Actividad (1–5)" />
      <CardContent>
        {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}
        <form id="activityForm" onSubmit={submit}>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Minutos totales"
                name="minutes"
                type="number"
                inputProps={{ step: 1, min: 0, max: 600 }}
                value={form.minutes}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                select
                label="Intensidad"
                name="intensity"
                value={form.intensity}
                onChange={ch}
                fullWidth
              >
                {INTENSITY.map(i => <MenuItem key={i.value} value={i.value}>{i.label}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Pasos"
                name="steps"
                type="number"
                inputProps={{ step: 1, min: 0, max: 100000 }}
                value={form.steps}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Min. zona cardiaca"
                name="hr_zone_minutes"
                type="number"
                inputProps={{ step: 1, min: 0, max: 600 }}
                value={form.hr_zone_minutes}
                onChange={ch}
                fullWidth
              />
            </Grid>
            <Grid item xs={12}>
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
        <Button type="submit" form="activityForm" variant="contained" disabled={saving}>
          {saving ? "Calculando..." : "Calcular y guardar"}
        </Button>
      </CardActions>
    </Card>
  );
}
