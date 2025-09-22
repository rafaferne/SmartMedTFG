import { useEffect, useMemo, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  FormControl, InputLabel, Select, MenuItem,
  TextField, Stack, Button, Typography
} from "@mui/material";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import { useApiFetch } from "../lib/apiFetch";

const DEFAULT_METRICS = [
  { value: "heart_rate", label: "Frecuencia cardiaca (bpm)" },
  { value: "temp", label: "Temperatura (°C)" },
  { value: "spo2", label: "SpO₂ (%)" },
  { value: "bp_sys", label: "Presión sistólica (mmHg)" },
  { value: "bp_dia", label: "Presión diastólica (mmHg)" },
];

function fmtTime(iso) {
  // hh:mm local
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export default function MetricsChart({
  metricOptions = DEFAULT_METRICS,
  defaultMetric = "heart_rate",
  defaultMinutes = 60,
  pollMs = 5000,
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
      const points = json.points.map(p => ({ time: fmtTime(p.t), value: p.v }));
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
  }, [metric, minutes]);

  const yDomain = useMemo(() => {
    const vals = data.map(d => d.value).filter(v => v != null);
    if (!vals.length) return [0, 1];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pad = (max - min) * 0.1 || 1;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [data]);

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title="Evolución minuto a minuto"
        subheader={
          <Typography variant="body2" color="text.secondary">
            Actualiza cada {(pollMs/1000)|0}s
          </Typography>
        }
      />
      <CardContent>
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
            <YAxis domain={yDomain} />
            <Tooltip
              formatter={(val) => (val == null ? "sin dato" : val)}
              labelFormatter={(label) => `Minuto: ${label}`}
            />
            <Line
              type="monotone"
              dataKey="value"
              dot={false}
              isAnimationActive={!loading}
              connectNulls={false} // no unir huecos
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Typography variant="caption" color="text.secondary">
          Los huecos (minutos sin dato) aparecen como cortes en la línea.
        </Typography>
      </CardActions>
    </Card>
  );
}
