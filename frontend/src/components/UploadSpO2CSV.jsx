import { useState, useMemo } from "react";
import { Card, CardHeader, CardContent, CardActions, Button, Typography, Stack, Alert, Chip } from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import { useApiFetch } from "../lib/apiFetch";

export default function UploadSpO2CSV() {
  const { apiFetch } = useApiFetch();
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const onChange = (e) => {
    const list = Array.from(e.target.files || []);
    setFiles(list);
    setMsg(null);
  };

  const namesPreview = useMemo(() => {
    if (!files?.length) return "Ningún archivo seleccionado";
    if (files.length <= 3) return files.map(f => f.name).join(" · ");
    return `${files.length} archivos seleccionados`;
  }, [files]);

  const onUpload = async () => {
    if (!files?.length) return;
    setBusy(true); setMsg(null);
    try {
      const form = new FormData();
      for (const f of files) {
        form.append("files", f); // 👈 clave múltiple compatible con backend
      }
      const res = await apiFetch("/import/spo2/csv", { method: "POST", body: form });
      const json = await res.json();
      if (!res.ok || json.ok === false) {
        throw new Error(json?.error || "Error al importar");
      }
      const s = json.summary || {};
      setMsg({
        type: "success",
        text: `SpO₂ importado: ${s.days_aggregated ?? 0} días · archivos=${s.files ?? files.length} · filas=${s.total_rows ?? 0} · errores=${s.errors ?? 0}`
      });
      setFiles([]);
    } catch (e) {
      setMsg({ type: "error", text: String(e.message || e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card sx={{ mt: 3, borderRadius: 3, boxShadow: "0 6px 20px rgba(0,0,0,0.06)" }}>
      <CardHeader
        title="Importar datos de oxígeno en sangre (SpO₂)"
        subheader="Sube uno o varios CSV por minuto; calcularemos la media diaria"
      />
      <CardContent>
        {msg && <Alert severity={msg.type} sx={{ mb: 1, whiteSpace: "pre-wrap" }}>{msg.text}</Alert>}

        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
          <Button component="label" variant="outlined" startIcon={<CloudUploadIcon />}>
            Elegir CSV
            <input
              type="file"
              accept=".csv,text/csv"
              hidden
              multiple
              onChange={onChange}
            />
          </Button>

          <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
            {namesPreview}
          </Typography>

          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              disabled={!files?.length || busy}
              onClick={onUpload}
              startIcon={<CloudUploadIcon />}
            >
              {busy ? "Subiendo…" : "Subir"}
            </Button>
          </Stack>
        </Stack>

        {!!files?.length && files.length <= 6 && (
          <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap", gap: 1 }}>
            {files.map((f, i) => <Chip key={i} label={f.name} size="small" />)}
          </Stack>
        )}
      </CardContent>
      <CardActions />
    </Card>
  );
}
