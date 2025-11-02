import { useEffect, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Stack, Button, Typography, Grid, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert
} from "@mui/material";
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Legend, Tooltip
} from "recharts";
import { useApiFetch } from "../lib/apiFetch";

const clamp15 = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.max(1, Math.min(5, Math.round(n)));
};
const lastNonNull = (points) => {
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i]?.v != null) return clamp15(points[i].v);
  }
  return null;
};
const fmtLabel = (iso) => {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], { year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
};

export default function SimulationRadar({
  metrics = ["sleep", "activity", "stress"],
  labelsMap = { sleep: "Sueño", activity: "Actividad", stress: "Estrés" },
  reloadToken = 0,
  activeMetric,
  onReset,
}) {
  const { apiFetch } = useApiFetch();
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [err, setErr] = useState("");
  const [rows, setRows] = useState([]); // [{ key, label, actual, sim }]

  // ------- NUEVO: selector de fecha + modal de detalle -------
  const [datePick, setDatePick] = useState("");
  const [dateBtnLoading, setDateBtnLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTs, setDetailTs] = useState(null);
  const [simDetail, setSimDetail] = useState(null);
  const [simErr, setSimErr] = useState("");
  const chosenMetric = activeMetric || metrics[0]; // usamos la métrica activa del radar

  const loadMetric = async (metric) => {
    // actual: usa una ventana amplia (365 días) para asegurar dato
    const sr = await apiFetch(`/metrics/series?type=${encodeURIComponent(metric)}&minutes=525600`);
    const sj = await sr.json();
    const actual = (sr.ok && sj.ok) ? lastNonNull(sj.points || []) : null;

    // simulación: último punto de la última simulación
    let sim = null;
    try {
      const res = await apiFetch(`/simulations/latest?metric=${metric}`);
      const js = await res.json();
      if (res.ok && js.ok && Array.isArray(js.forecast) && js.forecast.length > 0) {
        const last = js.forecast[js.forecast.length - 1];
        sim = clamp15(last?.value);
      }
    } catch { /* sin overlay */ }

    return { key: metric, label: labelsMap[metric] || metric, actual, sim };
  };

  const loadAll = async () => {
    setLoading(true); setErr("");
    try {
      const results = await Promise.all(metrics.map(loadMetric));
      setRows(results);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, [reloadToken, metrics.join(",")]);

  const handleReset = async () => {
    if (!chosenMetric) return;
    if (resetting) return;
    setResetting(true); setErr("");
    try {
      const res = await apiFetch(`/simulations?metric=${encodeURIComponent(chosenMetric)}`, { method: "DELETE" });
      const json = await res.json();
      if (!res.ok || json.ok === false) {
        throw new Error(json.error || "No se pudo reiniciar");
      }
      setRows(prev => prev.map(r => r.key === chosenMetric ? { ...r, sim: null } : r));
      onReset?.(chosenMetric);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setResetting(false);
    }
  };

  const dataForChart = rows.map(r => ({
    subject: r.label,
    Actual: r.actual ?? 0,
    Simulación: r.sim ?? 0,
  }));

  // ------- NUEVO: abrir modal por fecha para ver base → sim (Δ), rationale e intervenciones -------
  const openDetailByDate = async () => {
    if (!datePick || !chosenMetric) return;
    setDateBtnLoading(true);
    setDetailOpen(true);
    setDetailTs(null);
    setSimDetail(null);
    setSimErr("");
    try {
      // Usa el endpoint específico por fecha (trae base, sim, delta, rationale, intervenciones y features)
      const r = await apiFetch(`/simulations/by_date?metric=${encodeURIComponent(chosenMetric)}&date=${encodeURIComponent(datePick)}`);
      const j = await r.json();
      if (!r.ok || j.ok === false) throw new Error(j.error || "No hay simulación para esa fecha");
      setDetailTs(j.ts || null);
      setSimDetail(j);
    } catch (e) {
      setSimErr(String(e?.message || e));
    } finally {
      setDateBtnLoading(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title="Malla de estado vs simulación"
        subheader="Escala 1–5 (más es mejor)"
      />
      <CardContent>
        {err && <Typography color="error" sx={{ mb: 1 }}>{err}</Typography>}

        {/* NUEVO: Selector de fecha para ver detalle de la simulación (intervenciones + Δ) */}
        <Grid container spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
          <Grid item xs={12} sm={8} md={6}>
            <Typography variant="body2" color="text.secondary">
              Selecciona una fecha para ver las <b>intervenciones</b>, el <b>rationale</b> y la mejora <b>Δ</b> de la simulación.
            </Typography>
          </Grid>
          <Grid item xs />
          <Grid item xs={12} sm="auto">
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField
                size="small"
                type="date"
                label={`Fecha (${labelsMap[chosenMetric] || chosenMetric})`}
                InputLabelProps={{ shrink: true }}
                value={datePick}
                onChange={(e) => setDatePick(e.target.value)}
              />
              <Button
                variant="contained"
                size="small"
                onClick={openDetailByDate}
                disabled={!datePick || dateBtnLoading}
              >
                {dateBtnLoading ? "Buscando…" : "Ver consejos"}
              </Button>
            </Stack>
          </Grid>
        </Grid>

        <ResponsiveContainer width="100%" height={380}>
          <RadarChart data={dataForChart} outerRadius="70%">
            <PolarGrid />
            <PolarAngleAxis dataKey="subject" />
            <PolarRadiusAxis angle={30} domain={[0, 5]} tickCount={6} />
            <Tooltip />
            <Legend />
            <Radar name="Actual" dataKey="Actual" stroke="#1e8449" fill="#1e8449" fillOpacity={0.25} />
            <Radar name="Simulación" dataKey="Simulación" stroke="#e74c3c" fill="#e74c3c" fillOpacity={0.2} />
          </RadarChart>
        </ResponsiveContainer>
        <Typography variant="caption" color="text.secondary">
          Si un valor es 0, indica “sin dato” para ese punto.
        </Typography>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={loadAll} disabled={loading}>
            {loading ? "Actualizando…" : "Actualizar"}
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleReset}
            disabled={resetting || !chosenMetric}
          >
            {resetting ? "Reiniciando…" : `Reiniciar: ${labelsMap[chosenMetric] || chosenMetric}`}
          </Button>
        </Stack>
      </CardActions>

      {/* NUEVO: MODAL detalle de simulación por fecha */}
      <Dialog open={detailOpen} onClose={() => setDetailOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Detalle de simulación — {labelsMap[chosenMetric] || chosenMetric}</DialogTitle>
        <DialogContent dividers>
          {!datePick && !simDetail && !simErr && (
            <Typography variant="body2">Elige una fecha y pulsa “Ver simulación”.</Typography>
          )}
          {detailTs && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Fecha/hora: {fmtLabel(detailTs)}
            </Typography>
          )}
          {simErr && <Alert severity="warning" sx={{ mb: 1 }}>{simErr}</Alert>}
          {simDetail && (
            <Stack spacing={1}>
              <Typography variant="body2">
                <b>Base:</b> {simDetail.base ?? "—"} → <b>Sim:</b> {simDetail.sim ?? "—"} ({simDetail.delta >= 0 ? "+" : ""}{simDetail.delta ?? 0})
              </Typography>
              {simDetail.rationale && (
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  <b>Rationale:</b> {simDetail.rationale}
                </Typography>
              )}
              {Array.isArray(simDetail.interventions) && simDetail.interventions.length > 0 && (
                <>
                  <Typography variant="body2" sx={{ mt: 0.5 }}><b>Intervenciones (IA):</b></Typography>
                  <ul style={{ marginTop: 4 }}>
                    {simDetail.interventions.map((it, i) => (
                      <li key={i}>
                        <b>{it.title || "Intervención"}</b>: {it.description || "—"} <i>({it.category || "general"}, esfuerzo {it.effort ?? "?"})</i>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {simDetail.features && (
                <>
                  <Typography variant="body2" sx={{ mt: 0.5 }}><b>Features del día (CSV):</b></Typography>
                  <pre style={{ whiteSpace: "pre-wrap", background: "#fafafa", padding: 10, borderRadius: 8, maxHeight: 220, overflow: "auto" }}>
{JSON.stringify(simDetail.features, null, 2)}
                  </pre>
                </>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailOpen(false)}>Cerrar</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
