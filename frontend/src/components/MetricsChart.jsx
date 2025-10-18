import { useEffect, useMemo, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  FormControl, InputLabel, Select, MenuItem,
  TextField, Stack, Button, Typography
} from "@mui/material";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from "recharts";
import { useApiFetch } from "../lib/apiFetch";

const DEFAULT_METRICS = [
  { value: "sleep",    label: "Sueño" },
  { value: "activity", label: "Actividad física" },
];

const SCALE_LABEL = { 1: "Muy bajo", 2: "Bajo", 3: "Medio", 4: "Alto", 5: "Muy alto" };

function fmtTime(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

function normalizeDiscrete(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.min(5, Math.max(1, Math.round(n)));
}

// (opcional) arrastrar último valor para continuidad visual
function forwardFill(series) {
  let last = null;
  return series.map(p => {
    if (p.value != null) last = p.value;
    return { ...p, value: p.value ?? last };
  });
}

export default function MetricsChart({
  metricOptions = DEFAULT_METRICS,
  defaultMetric = "sleep",
  defaultMinutes = 60,
  pollMs = 5000,
  reloadToken = 0,
}) {
  const { apiFetch } = useApiFetch();
  const [metric, setMetric] = useState(defaultMetric);
  const [minutes, setMinutes] = useState(defaultMinutes);

  const [data, setData] = useState([]);
  const [overlay, setOverlay] = useState([]);
  const [overlayMeta, setOverlayMeta] = useState(null);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = async () => {
    setErr("");
    try {
      const res = await apiFetch(`/metrics/series?type=${encodeURIComponent(metric)}&minutes=${minutes}`);
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "Error cargando serie");
      const points = (json.points || []).map(p => ({
        time: fmtTime(p.t),
        value: normalizeDiscrete(p.v),
      }));
      // Puedes usar forwardFill(points) si prefieres continuidad
      setData(points);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const loadOverlay = async () => {
    try {
      const res = await apiFetch(`/simulations/latest?metric=${metric}`);
      const json = await res.json();
      if (res.ok && json.ok) {
        const now = Date.now();
        const points = (json.forecast || []).map(it => ({
          time: fmtTime(new Date(now + it.minute * 60 * 1000).toISOString()),
          value: normalizeDiscrete(it.value),
        }));
        setOverlay(points);
        setOverlayMeta({
          created_at: json.created_at,
          horizon: json.horizon_min,
          interventions: json.interventions || []
        });
      } else {
        setOverlay([]);
        setOverlayMeta(null);
      }
    } catch {
      setOverlay([]);
      setOverlayMeta(null);
    }
  };

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, minutes, reloadToken]);

  useEffect(() => {
    loadOverlay();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, reloadToken]);

  const merged = useMemo(() => {
    const map = new Map(); // time -> { time, real, sim }
    for (const p of data) {
      const t = p.time;
      const row = map.get(t) || { time: t, real: null, sim: null };
      row.real = p.value ?? null;
      map.set(t, row);
    }
    for (const p of overlay) {
      const t = p.time;
      const row = map.get(t) || { time: t, real: null, sim: null };
      row.sim = p.value ?? null;
      map.set(t, row);
    }
    return Array.from(map.values()).sort((a, b) => a.time.localeCompare(b.time));
  }, [data, overlay]);

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title="Evolución minuto a minuto"
        subheader={
          <Typography variant="body2" color="text.secondary">
            Actualiza cada {Math.floor(pollMs / 1000)}s
          </Typography>
        }
      />
      <CardContent>
        {data.length === 0 && !err && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            No hay datos en la ventana seleccionada.
          </Typography>
        )}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Métrica</InputLabel>
            <Select label="Métrica" value={metric} onChange={e => setMetric(e.target.value)}>
              {metricOptions.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="Ventana (min)"
            size="small"
            type="number"
            inputProps={{ min: 5, max: 1440 }}
            value={minutes}
            onChange={e => setMinutes(Math.max(5, Math.min(1440, Number(e.target.value) || 60)))}
          />
          <Button variant="outlined" onClick={load}>Actualizar</Button>
          {err && <Typography color="error" sx={{ ml: { sm: "auto" } }}>{err}</Typography>}
        </Stack>

        <ResponsiveContainer width="100%" height={360}>
          {/* El gráfico ahora usa "merged" */}
          <LineChart data={merged}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" minTickGap={24} />
            <YAxis domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} allowDecimals={false} />
            <Tooltip
              formatter={(val, name) => {
                if (val == null) return ["sin dato", name === "real" ? "Real" : "Simulación"];
                const label = SCALE_LABEL[val] || val;
                return [label, name === "real" ? "Real" : "Simulación"];
              }}
              labelFormatter={(label) => `Minuto: ${label}`}
            />
            <Legend />
            <ReferenceLine y={3} strokeDasharray="3 3" />
            {/* Serie real */}
            <Line
              name="Real"
              type="stepAfter"
              dataKey="real"
              dot={false}
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
            />
            {/* Serie simulada */}
            {overlay.length > 0 && (
              <Line
                name="Simulación"
                type="stepAfter"
                dataKey="sim"
                dot={false}
                strokeWidth={2}
                strokeDasharray="6 6"
                connectNulls
                isAnimationActive={false}
              />
            )}
          </LineChart>
        </ResponsiveContainer>

        {overlayMeta?.interventions?.length > 0 && (
          <Stack sx={{ mt: 2 }} spacing={0.5}>
            <Typography variant="subtitle2">Intervenciones sugeridas:</Typography>
            {overlayMeta.interventions.map((it, idx) => (
              <Typography key={idx} variant="body2" color="text.secondary">
                • <strong>{it.title || "Sin título"}</strong> — {it.description || "—"}
              </Typography>
            ))}
          </Stack>
        )}
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Typography variant="caption" color="text.secondary">
          1 = Muy bajo · 3 = Medio · 5 = Muy alto. La línea discontinua muestra la proyección.
        </Typography>
      </CardActions>
    </Card>
  );
}
