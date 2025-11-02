import { useRef, useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Button, Alert, Stack, Typography, LinearProgress
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DescriptionIcon from "@mui/icons-material/Description";
import { useApiFetch } from "../lib/apiFetch";

export default function UploadFitbitSleep({ onImported }) {
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
      setMsg({ type: "warning", text: "Selecciona un archivo .csv" });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch("/import/sleep/csv", { method: "POST", body: fd });
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || "Error importando CSV");

      const bulk = await apiFetch("/ai/score/sleep/from_csv/bulk_llm", { method: "POST" });
      const bj = await bulk.json();
      if (!bulk.ok || bj.ok === false) throw new Error(bj.error || "Error valorando el sueño con IA");

      setMsg({
        type: "success",
        text:
          `Importado: ${json.summary.inserted} nuevos · ${json.summary.updated} actualizados · ` +
          `errores: ${json.summary.errors}. ` +
          `Valorados (IA): ${bj.summary?.written_measurements ?? 0}.`
      });

      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onImported?.();
    } catch (e) {
      setMsg({ type: "error", text: String(e.message || e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title="Importar datos de sueño"
        subheader="Se guardan todas las columnas y la IA valora 1–5 usando el conjunto completo de datos."
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
