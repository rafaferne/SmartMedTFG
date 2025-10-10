import { useEffect, useMemo, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  FormControl, InputLabel, Select, MenuItem,
  TextField, Stack, Button, Typography
} from "@mui/material";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from "recharts";
import { useApiFetch } from "../lib/apiFetch";

// 🚦 Solo estas dos métricas (1–5)
const DEFAULT_METRICS = [
  { value: "sleep",    label: "Sueño" },
  { value: "activity", label: "Actividad física" },
];

// Mapea 1..5 a etiquetas cualitativas genéricas
const SCALE_LABEL = {
  1: "Muy bajo",
  2: "Bajo",
  3: "Medio",
  4: "Alto",
  5: "Muy alto",
};

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

// Normaliza a entero 1..5 (mantiene nulls para huecos)
function normalizeDiscrete(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.min(5, Math.max(1, Math.round(n)));
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
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = async () => {
    setErr("");
    try {
      const res = await apiFetch(`/metrics/series?type=${encodeURIComponent(metric)}&minutes=${minutes}`);
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "Error cargando serie");
      const points = json.points.map(p => ({
        time: fmtTime(p.t),
        value: normalizeDiscrete(p.v),
      }));
      setData(points);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, minutes, reloadToken]);

  // Eje Y fijo a 1..5, sin decimales
  const yTicks = useMemo(() => [1, 2, 3, 4, 5], []);
  const yDomain = useMemo(() => [1, 5], []);

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
          {err && <Typography color="error" sx={{ ml: "auto" }}>{err}</Typography>}
        </Stack>

        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" minTickGap={24} />
            <YAxis
              domain={yDomain}
              ticks={yTicks}
              allowDecimals={false}
              tickFormatter={(t) => `${t}`}
            />
            <Tooltip
              formatter={(val) => {
                if (val == null) return ["sin dato", ""];
                const label = SCALE_LABEL[val] || val;
                return [label, "Nivel"];
              }}
              labelFormatter={(label) => `Minuto: ${label}`}
            />
            {/* Líneas guía opcionales (puedes quitarlas si no te gustan) */}
            <ReferenceLine y={3} strokeDasharray="3 3" />
            <Line
              type="stepAfter"
              dataKey="value"
              dot={false}
              isAnimationActive={!loading}
              connectNulls={false} 
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Typography variant="caption" color="text.secondary">
          1 = Muy bajo · 3 = Medio · 5 = Muy alto. Los huecos aparecen como cortes en la línea.
        </Typography>
      </CardActions>
    </Card>
  );
}
