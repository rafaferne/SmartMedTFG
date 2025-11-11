import { useEffect, useMemo, useRef, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Stack, Button, Typography, ToggleButton, ToggleButtonGroup,
  TextField, MenuItem, Divider, Tooltip as MuiTooltip,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert,
  Grid, Box, Paper, IconButton, Collapse
} from "@mui/material";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend, Brush
} from "recharts";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import { useApiFetch } from "../lib/apiFetch";

const SCALE_LABEL = { 1: "Muy bajo", 2: "Bajo", 3: "Medio", 4: "Alto", 5: "Muy alto" };

function toISO(dt) { return new Date(dt).toISOString(); }
function fmtLabel(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], { year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
function fmtTick(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
function normalizeDiscrete(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.min(5, Math.max(1, Math.round(n)));
}
function minutesBetween(a, b) { return Math.max(1, Math.round((b.getTime() - a.getTime()) / 60000)); }

const QUICK_PRESETS = [
  { key: "60", label: "60 min", minutes: 60 },
  { key: "1440", label: "24 h", minutes: 1440 },
  { key: "10080", label: "7 días", minutes: 10080 },
  { key: "43200", label: "30 días", minutes: 43200 },
  { key: "525600", label: "365 días", minutes: 525600 },
];

// Etiquetas legibles por métrica
const LABEL_MAPS = {
  sleep: {
    sleep_log_entry_id: "Log del sueño",
    overall_score: "Puntuación media",
    revitalization_score: "Puntuación de revitalización",
    deep_sleep_in_minutes: "Minutos de sueño profundo",
    resting_heart_rate: "Frecuencia cardíaca en reposo",
    restlessness: "Agitación",
    spo2_avg: "SpO₂ medio (%)"
  },
  stress: {
    eda_level_real: "Nivel EDA (real)",
    spo2_avg: "SpO₂ medio (%)"
  },
  activity: {
    tracker_total_calories: "Calorías totales (kcal)",
    tracker_total_steps: "Número de pasos",
    tracker_total_distance_mm: "Distancia total (m)",
    tracker_total_altitude_mm: "Desnivel total (m)",
    tracker_avg_heart_rate: "Frecuencia cardíaca media",
    tracker_peak_heart_rate: "Frecuencia cardíaca máxima",
    tracker_cardio_load: "Carga cardiovascular",
    spo2_avg: "SpO₂ medio (%)"
  },
};

function prettifyKey(k) {
  if (!k) return "";
  return String(k)
    .replace(/\s+/g, " ")
    .replace(/_/g, " ")
    .trim()
    .replace(/^\w/, (m) => m.toUpperCase());
}

// ---------- Tooltip ----------
function CustomTooltip({ active, payload, label, hasOverlay }) {
  if (!active || !payload || payload.length === 0) return null;
  const items = payload.filter(it => {
    if (it?.dataKey === "real") return true;
    if (it?.dataKey === "sim" && hasOverlay) return true;
    return false;
  });
  if (items.length === 0) return null;

  return (
    <div className="recharts-default-tooltip" style={{ background: "#fff", border: "1px solid #e0e0e0", borderRadius: 8, padding: 10, boxShadow: "0 4px 10px rgba(0,0,0,0.06)" }}>
      <div style={{ marginBottom: 6, fontWeight: 600 }}>{fmtLabel(label)}</div>
      {items.map((it, idx) => {
        const v = it?.value;
        const name = it?.dataKey === "real" ? "Real" : "Simulación";
        const txt = v == null ? "sin dato" : (SCALE_LABEL[v] || v);
        return (
          <div key={idx} style={{ display: "flex", gap: 8 }}>
            <span style={{ width: 100, color: "#666" }}>{name} :</span>
            <span>{txt}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function MetricsChart({ metric, title = "Evolución", defaultMode = "relative", defaultMinutes = 60, pollMs = 0 }) {
  const { apiFetch } = useApiFetch();

  const [mode, setMode] = useState(defaultMode);
  const [relMinutes, setRelMinutes] = useState(defaultMinutes);

  const now = useMemo(() => new Date(), []);
  const thirtyDaysAgo = useMemo(() => new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), []);
  const [absFrom, setAbsFrom] = useState(() => new Date(thirtyDaysAgo));
  const [absTo, setAbsTo] = useState(() => new Date(now));

  const [data, setData] = useState([]);            // [{tISO, value}]
  const [overlay, setOverlay] = useState([]);      // [{time, value}]
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const pollRef = useRef(null);

  // UI modal detalle
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState("");
  const [detail, setDetail] = useState(null);
  const [selectedTs, setSelectedTs] = useState(null);

  // Selector de fecha (advice IA)
  const [adviceDate, setAdviceDate] = useState("");
  const [adviceMsg, setAdviceMsg] = useState(null);
  const [adviceLoading, setAdviceLoading] = useState(false);

  const [dayDate, setDayDate] = useState("");
  const [dayLoading, setDayLoading] = useState(false);
  const [dayErr, setDayErr] = useState("");
  const [dayDetail, setDayDetail] = useState(null);
  const [adviceExpanded, setAdviceExpanded] = useState(false);

  const currentRange = useMemo(() => {
    if (mode === "absolute") {
      return { from: absFrom, to: absTo };
    }
    const to = new Date();
    const from = new Date(Date.now() - relMinutes * 60 * 1000);
    return { from, to };
  }, [mode, relMinutes, absFrom, absTo]);

  const load = async () => {
    setErr("");
    try {
      let url = `/metrics/series?type=${encodeURIComponent(metric)}`;
      if (mode === "absolute") {
        const fromISO = absFrom.toISOString();
        const toISO_  = absTo.toISOString();
        url += `&from=${encodeURIComponent(fromISO)}&to=${encodeURIComponent(toISO_)}`;
      } else {
        url += `&minutes=${relMinutes}`;
      }
      const res = await apiFetch(url);
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "Error cargando serie");
      const points = (json.points || []).map(p => ({ tISO: p.t, value: normalizeDiscrete(p.v) }));
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
        const mode = json.forecast_mode || "minutes_ahead";
        let points = [];
        if (mode === "absolute_ts") {
          points = (json.forecast || []).map(it => ({ time: it.ts, value: normalizeDiscrete(it.value) }));
        } else {
          const nowMs = Date.now();
          points = (json.forecast || []).map(it => ({
            time: new Date(nowMs + (it.minute || 0) * 60 * 1000).toISOString(),
            value: normalizeDiscrete(it.value)
          }));
        }
        setOverlay(points);
      } else {
        setOverlay([]);
      }
    } catch {
      setOverlay([]);
    }
  };

  useEffect(() => {
    setLoading(true);
    load();
    if (pollMs > 0) {
      clearInterval(pollRef.current);
      pollRef.current = setInterval(load, pollMs);
      return () => clearInterval(pollRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, mode, relMinutes, absFrom.getTime(), absTo.getTime()]);

  useEffect(() => { loadOverlay(); /* eslint-disable-next-line */ }, [metric]);

  const filteredOverlay = useMemo(() => {
    if (!overlay.length || !data.length) return [];
    const fromMs = currentRange.from.getTime();
    const toMs = currentRange.to.getTime();
    const realTimes = new Set(
      data
        .map(p => p.tISO)
        .filter(ts => {
          const t = Date.parse(ts);
          return Number.isFinite(t) && t >= fromMs && t <= toMs;
        })
    );
    return overlay.filter(p => realTimes.has(p.time));
  }, [overlay, data, currentRange]);

  const merged = useMemo(() => {
    const map = new Map();
    for (const p of data) {
      const t = p.tISO;
      map.set(t, { time: t, real: p.value ?? null, sim: null });
    }
    for (const p of filteredOverlay) {
      const t = p.time;
      const row = map.get(t);
      if (row) row.sim = p.value ?? null;
    }
    return Array.from(map.values()).sort((a, b) => a.time.localeCompare(b.time));
  }, [data, filteredOverlay]);

  const hasOverlay = filteredOverlay.length > 0;

  const applyAbsolute = () => {
    if (!(absFrom instanceof Date) || !(absTo instanceof Date)) return;
    if (absFrom >= absTo) { setErr("El 'desde' debe ser anterior al 'hasta'."); return; }
    load();
  };

  const onPreset = (m) => { setMode("relative"); setRelMinutes(m); };
  const onModeChange = (_e, v) => { if (!v) return; setMode(v); };

  const absFromInput = useMemo(() => {
    const d = absFrom; const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }, [absFrom]);
  const absToInput = useMemo(() => {
    const d = absTo; const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }, [absTo]);

  const fetchDetail = async (tsISO) => {
    setDetailLoading(true); setDetailErr(""); setDetail(null);
    try {
      const res = await apiFetch(`/metrics/detail?type=${encodeURIComponent(metric)}&ts=${encodeURIComponent(tsISO)}`);
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "No hay detalle para ese punto");
      setDetail(json);
    } catch (e) {
      setDetailErr(String(e?.message || e));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleChartClick = (state) => {
    const p = state?.activePayload?.[0]?.payload;
    if (!p || !p.time) return;
    setSelectedTs(p.time);
    setDetailOpen(true);
    fetchDetail(p.time);
  };

  // Etiqueta por clave
  const labelFor = (key) => {
    const map = LABEL_MAPS[metric] || {};
    const base = map[key] || String(key).replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase());
    // Si detectamos *_mm, forzamos "(m)" en la etiqueta
    if (metric === "activity" && /(^|_)dist(ance)?_?mm(s)?$/i.test(key)) {
      return "Distancia (m)";
    }
    if (metric === "activity" && /(altitude|alt|elevation|ascent|descent)(_?mm(s)?)?$/i.test(key)) {
      return "Altitud/Desnivel (m)";
    }
    return base;
  };

  // --- Conversión de distancia y altitud/desnivel al mostrar ---
  const formatFeatureValue = (key, value) => {
    if (value == null) return "—";
    if (metric !== "activity") return typeof value === "object" ? JSON.stringify(value) : String(value);

    const k = String(key).toLowerCase();
    const num = Number(value);

    // DISTANCIA
    if (/(^|_)dist(ance)?_?mm(s)?$/.test(k) || /(millimeter|millimetre)/.test(k)) {
      return Number.isFinite(num) ? `${(num / 1000).toFixed(2)} m` : String(value);
    }
    if (/(^|_)dist(ance)?_(?!(mm|mms?)$)m$/.test(k)) {
      return Number.isFinite(num) ? `${num.toFixed(2)} m` : String(value);
    }
    if (/(^|_)dist(ance)?_?km$/.test(k)) {
      return Number.isFinite(num) ? `${num.toFixed(3)} km` : String(value);
    }
    if (/(^|_)distance$/.test(k) || /(^|_)dist$/.test(k)) {
      if (Number.isFinite(num)) {
        if (num > 10000) return `${(num / 1000).toFixed(2)} m`;
        if (num > 100) return `${num.toFixed(2)} m`;
        return `${num.toFixed(3)} km`;
      }
      return String(value);
    }

    // ALTITUD / ELEVACIÓN / DESNIVEL
    if (/(^|_)(altitude|alt|elevation|ascent|descent|gain|loss)(_?mm(s)?)?$/.test(k) && /mm/.test(k)) {
      return Number.isFinite(num) ? `${(num / 1000).toFixed(2)} m` : String(value);
    }
    if (/(^|_)(altitude|alt|elevation|ascent|descent|gain|loss)_(?!(mm|mms?)$)m$/.test(k)) {
      return Number.isFinite(num) ? `${num.toFixed(2)} m` : String(value);
    }
    if (/(^|_)(altitude|alt|elevation|ascent|descent|gain|loss)_?km$/.test(k)) {
      return Number.isFinite(num) ? `${num.toFixed(3)} km` : String(value);
    }
    if (/(^|_)(altitude|alt|elevation|ascent|descent|gain|loss)$/.test(k)) {
      if (Number.isFinite(num)) {
        if (num > 10000) return `${(num / 1000).toFixed(2)} m`;
        if (num > 100) return `${num.toFixed(2)} m`;
        return `${num.toFixed(3)} km`;
      }
      return String(value);
    }

    // por defecto
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  };

  // --- Día seleccionado (features) ---
  const fetchDayDetail = async () => {
    if (!dayDate) return;
    setDayLoading(true); setDayErr(""); setDayDetail(null); setAdviceExpanded(false);
    try {
      const r = await apiFetch(`/metrics/detail/by_date?type=${encodeURIComponent(metric)}&date=${encodeURIComponent(dayDate)}`);
      const j = await r.json();
      if (!r.ok || j.ok === false) throw new Error(j?.error || "No hay medición para esa fecha");
      setDayDetail(j);
    } catch (e) {
      setDayErr(String(e?.message || e));
    } finally {
      setDayLoading(false);
    }
  };

  // === filtro visual de features 0/nulas en actividad ===
  const filteredDayFeatures = useMemo(() => {
    const feats = dayDetail?.features || null;
    if (!feats) return null;
    if (metric !== "activity") return feats;
    const out = {};
    for (const [k, v] of Object.entries(feats)) {
      if (k === "samples") { out[k] = v; continue; }
      if (v == null) continue;
      if (typeof v === "number" && v === 0) continue;
      if (typeof v === "string" && v.trim() === "") continue;
      out[k] = v;
    }
    return out;
  }, [dayDetail, metric]);

  return (
    <Card sx={{ mt: 3, borderRadius: 3, boxShadow: "0 6px 20px rgba(0,0,0,0.06)" }}>
      <CardHeader
        title={title}
        subheader={
          <Box sx={{ width: "100%", mt: 1 }}>
            <Grid container spacing={1.5} alignItems="center">
              <Grid item xs={12} md="auto">
                <ToggleButtonGroup size="small" value={mode} exclusive onChange={(_e, v) => v && setMode(v)} sx={{ flexWrap: "wrap" }}>
                  <ToggleButton value="relative">Rango relativo</ToggleButton>
                  <ToggleButton value="absolute">Rango absoluto</ToggleButton>
                </ToggleButtonGroup>
              </Grid>

              {mode === "relative" && (
                <>
                  <Grid item xs={12} sm={6} md={3} lg={2}>
                    <TextField
                      size="small"
                      select
                      fullWidth
                      label="Últimos"
                      value={String(relMinutes)}
                      onChange={(e) => setRelMinutes(Number(e.target.value))}
                    >
                      {QUICK_PRESETS.map(p => (<MenuItem key={p.key} value={p.minutes}>{p.label}</MenuItem>))}
                    </TextField>
                  </Grid>
                </>
              )}

              {mode === "absolute" && (
                <>
                  <Grid item xs={12} sm={6} md={3}>
                    <TextField
                      size="small"
                      label="Desde"
                      type="datetime-local"
                      fullWidth
                      value={absFromInput}
                      onChange={(e) => setAbsFrom(new Date(e.target.value))}
                      InputLabelProps={{ shrink: true }}
                    />
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <TextField
                      size="small"
                      label="Hasta"
                      type="datetime-local"
                      fullWidth
                      value={absToInput}
                      onChange={(e) => setAbsTo(new Date(e.target.value))}
                      InputLabelProps={{ shrink: true }}
                    />
                  </Grid>
                  <Grid item xs={12} sm="auto">
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Button size="small" variant="contained" onClick={applyAbsolute} sx={{ borderRadius: 2, px: 2 }}>
                        Aplicar
                      </Button>
                    </Stack>
                  </Grid>
                </>
              )}
            </Grid>
          </Box>
        } 
      />

      <CardContent sx={{ pt: 1 }}>
        {adviceMsg && <Alert severity={adviceMsg.type} sx={{ mb: 2, whiteSpace: "pre-wrap" }}>{adviceMsg.text}</Alert>}
        {loading && <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Cargando…</Typography>}
        {err && <Typography color="error" sx={{ mb: 1 }}>{err}</Typography>}
        {!loading && merged.length === 0 && !err && (<Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>No hay datos en el rango seleccionado.</Typography>)}

        <ResponsiveContainer width="100%" height={380}>
          <LineChart data={merged} onClick={handleChartClick}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tickFormatter={fmtTick} minTickGap={24} />
            <YAxis domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} allowDecimals={false} />
            <Tooltip content={<CustomTooltip hasOverlay={hasOverlay} />} />
            <Legend />
            <ReferenceLine y={3} strokeDasharray="3 3" />
            <Line name="Real" type="stepAfter" dataKey="real" dot={false} activeDot={{ r: 5 }} stroke="#1e8449" strokeWidth={2} connectNulls isAnimationActive={false} />
            {hasOverlay && <Line name="Simulación" type="stepAfter" dataKey="sim" dot={false} stroke="#e74c3c" strokeWidth={2} connectNulls={false} isAnimationActive={false} />}
            <Brush dataKey="time" height={26} travellerWidth={10} tickFormatter={(v) => {
              try { const d = new Date(v); return d.toLocaleDateString([], { month: "2-digit", day: "2-digit" }); }
              catch { return v; }
            }} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>

      <Paper elevation={0} sx={{ mt: 2, p: 2, borderRadius: 2, border: "1px solid #eee" }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "flex-start", md: "center" }} sx={{ mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>
            Datos medidos del día (para la valoración)
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ width: { xs: "100%", md: "auto" } }}>
            <TextField size="small" type="date" label="Fecha" InputLabelProps={{ shrink: true }} value={dayDate} onChange={(e) => setDayDate(e.target.value)} />
            <Button variant="contained" size="small" onClick={fetchDayDetail} disabled={!dayDate || dayLoading}>
              {dayLoading ? "Cargando…" : "Ver datos del día"}
            </Button>
          </Stack>
        </Stack>

        {dayErr && <Alert severity="error" sx={{ mb: 1 }}>{dayErr}</Alert>}

        {!dayErr && dayDetail && (
          <Box>
            <Grid container spacing={5} sx={{ mb: 1 }}>
              <Grid item xs={12} md={3}>
                <Typography variant="body2" color="text.secondary">Fecha medición</Typography>
                <Typography variant="body1">
                  {(() => { try { return new Date(dayDetail.ts).toLocaleString(); } catch { return dayDetail.ts; } })()}
                </Typography>
              </Grid>
              <Grid item xs={6} md={2}>
                <Typography variant="body2" color="text.secondary">Puntuación</Typography>
                <Typography variant="body1">{dayDetail.value == null ? "—" : `${dayDetail.value} / 5`}</Typography>
              </Grid>
              <Grid item xs={6} md={2}>
                <Typography variant="body2" color="text.secondary">Fuente</Typography>
                <Typography variant="body1">Gemini</Typography>
              </Grid>
              <Grid item xs={12} md={5} sx={{ display: "flex", alignItems: "center" }}>
                <Typography variant="body2" color="text" sx={{ mr: 1 }}>Comentario IA</Typography>
                <IconButton size="small" onClick={() => setAdviceExpanded(s => !s)} aria-label="toggle-advice">
                  {adviceExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Grid>
            </Grid>

            <Collapse in={adviceExpanded} unmountOnExit>
              <Box sx={{ p: 1.5, background: "#fafafa", border: "1px solid #eee", borderRadius: 1, mb: 1 }}>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {dayDetail.advice || "—"}
                </Typography>
              </Box>
            </Collapse>

            <Divider sx={{ my: 1 }} />

            {(() => {
              // 🔒 usar el objeto con ceros/nulos filtrados (actividad) y aplicar además el filtro de claves ocultas
              const HIDE_KEYS = new Set(["sleep_log_entry_id", "exercise_id"]);

              const feats = filteredDayFeatures ?? dayDetail?.features ?? null;
              if (!feats || Object.keys(feats).length === 0) {
                return <Typography variant="body2" color="text.secondary">No hay registros guardados para ese día.</Typography>;
              }

              const visibleEntries = Object.entries(feats).filter(
                ([k]) => !HIDE_KEYS.has(String(k).toLowerCase())
              );

              if (visibleEntries.length === 0) {
                return <Typography variant="body2" color="text.secondary">No hay registros visibles tras aplicar los filtros.</Typography>;
              }

              return (
                <Box sx={{ border: "1px solid #eee", borderRadius: 1, overflow: "hidden", maxHeight: 260, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead style={{ position: "sticky", top: 0, background: "#f9f9f9" }}>
                      <tr>
                        <th style={{ textAlign: "left", padding: "8px 10px", borderBottom: "1px solid #eee", width: "40%" }}>Registros</th>
                        <th style={{ textAlign: "left", padding: "8px 10px", borderBottom: "1px solid #eee" }}>Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleEntries.map(([k, v]) => (
                        <tr key={k}>
                          <td style={{ padding: "8px 10px", borderBottom: "1px solid #f1f1f1", fontFamily: "monospace" }}>
                            {labelFor(k)}
                          </td>
                          <td style={{ padding: "8px 10px", borderBottom: "1px solid #f1f1f1" }}>
                            {formatFeatureValue(k, v)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Box>
              );
            })()}
          </Box>
        )}

        {!dayErr && !dayDetail && (
          <Typography variant="body2" color="text.secondary">Selecciona una fecha para ver las mediciones y el consejo de la IA de ese día.</Typography>
        )}
      </Paper>

      <Divider />
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "flex-start", md: "center" }} sx={{ width: "100%", justifyContent: "space-between" }}>
          <Typography variant="caption" color="text.secondary">
            1 = Muy bajo · 3 = Medio · 5 = Muy alto. 
          </Typography>
          {mode === "absolute" && (
            <Typography variant="caption" color="text.secondary">
              Intervalo seleccionado: {fmtLabel(absFrom.toISOString())} — {fmtLabel(absTo.toISOString())} · {` ${minutesBetween(absFrom, absTo)} min`}
            </Typography>
          )}
        </Stack>
      </CardActions>
    </Card>
  );
}
