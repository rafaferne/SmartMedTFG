import { useRef, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Button, Alert, Stack, Typography, LinearProgress
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DescriptionIcon from "@mui/icons-material/Description";
import { useApiFetch } from "../lib/apiFetch";

export default function UploadActivityCSV({ onImported }) {
  const { apiFetch } = useApiFetch();
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  const pick = (e) => {
    const f = e.target.files?.[0];
    setFile(f || null);
    setMsg(null);
  };

  const submit = async () => {
    if (!file) {
      setMsg({ type: "warning", text: "Selecciona un archivo .csv con datos de actividad" });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);

      // 1) Importar CSV (agrega por día -> activity_raw)
      const res = await apiFetch("/import/activity/csv", { method: "POST", body: fd });
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "Error importando CSV de actividad");

      // 2) Valorar IA en lote
      const bulk = await apiFetch("/ai/score/activity/from_csv/bulk_llm", { method: "POST" });
      const bj = await bulk.json();
      if (!bulk.ok || bj.ok === false) throw new Error(bj.error || "Error valorando la actividad con IA");

      setMsg({
        type: "success",
        text:
          `Importado: días=${json.summary?.days_aggregated ?? 0} ` +
          `· columnas=${(json.summary?.kept_columns || []).length} ` +
          `· IA escritos=${bj.summary?.written_measurements ?? 0} ` +
          `· errores LLM=${bj.summary?.llm_errors ?? 0}`
      });

      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onImported?.();
    } catch (e) {
      setMsg({ type: "error", text: String(e?.message || e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title="Importar datos de actividad física"
        subheader="Se agregan medias diarias y la IA valora la métrica 1–5."
      />
      <CardContent>
        {loading && <LinearProgress sx={{ mb: 2 }} />}
        {msg && <Alert severity={msg.type} sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{msg.text}</Alert>}

        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
          <Button variant="outlined" component="label" startIcon={<DescriptionIcon />} disabled={loading}>
            Elegir CSV
            <input ref={inputRef} type="file" accept=".csv" hidden onChange={pick} />
          </Button>
          <Typography variant="body2" sx={{ flexGrow: 1 }}>
            {file ? `Archivo: ${file.name}` : "Ningún archivo seleccionado"}
          </Typography>
          <Button variant="contained" startIcon={<CloudUploadIcon />} onClick={submit} disabled={loading || !file}>
            Subir
          </Button>
        </Stack>
      </CardContent>
      <CardActions />
    </Card>
  );
}
