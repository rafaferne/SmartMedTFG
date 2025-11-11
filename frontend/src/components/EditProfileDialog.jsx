import { useState, useEffect } from "react";
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Grid, TextField, MenuItem, Button, Alert
} from "@mui/material";
import { useApiFetch } from "../lib/apiFetch";

const SEX_OPTIONS = [
  { value: "male", label: "Hombre" },
  { value: "female", label: "Mujer" },
  { value: "other", label: "Otro" },
  { value: "prefer_not_say", label: "Prefiero no decir" },
];

export default function EditProfileDialog({ open, onClose, profileDoc, onSaved }) {
  const { apiFetch } = useApiFetch();
  const p = profileDoc?.profile || {};

  // estado local del formulario (pre-cargado con el perfil actual)
  const [form, setForm] = useState({
    birthdate: p.birthdate || "",
    sex: p.sex || "prefer_not_say",
    height_cm: p.height_cm ?? "",
    weight_kg: p.weight_kg ?? "",
    notes: p.notes || "",
  });
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // resetea cuando se abre con datos nuevos
    if (open) {
      setForm({
        birthdate: p.birthdate || "",
        sex: p.sex || "prefer_not_say",
        height_cm: p.height_cm ?? "",
        weight_kg: p.weight_kg ?? "",
        notes: p.notes || "",
      });
      setErr("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, profileDoc]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  };

  async function handleSave() {
    setErr("");
    setSaving(true);
    try {
      const payload = {
        birthdate: form.birthdate || null,
        sex: form.sex || "prefer_not_say",
        height_cm: form.height_cm !== "" ? Number(form.height_cm) : null,
        weight_kg: form.weight_kg !== "" ? Number(form.weight_kg) : null,
        notes: form.notes || "",
      };

      const res = await apiFetch("/me/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "Error guardando");

      onSaved?.(data.user);  // devuelve el doc actualizado al padre
      onClose?.();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Editar perfil</DialogTitle>
      <DialogContent dividers>
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <TextField
              name="birthdate"
              label="Fecha de nacimiento"
              type="date"
              InputLabelProps={{ shrink: true }}
              fullWidth
              value={form.birthdate}
              onChange={handleChange}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              select
              name="sex"
              label="Sexo"
              fullWidth
              value={form.sex}
              onChange={handleChange}
            >
              {SEX_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </TextField>
          </Grid>

          <Grid item xs={12} sm={6}>
            <TextField
              name="height_cm"
              label="Altura (cm)"
              type="number"
              helperText="40 a 300 cm"
              inputProps={{ min: 40, max: 300, step: 0.1 }}
              fullWidth
              value={form.height_cm}
              onChange={handleChange}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              name="weight_kg"
              label="Peso (kg)"
              type="number"
              helperText="1 a 600 kg"
              inputProps={{ min: 1, max: 600, step: 0.1 }}
              fullWidth
              value={form.weight_kg}
              onChange={handleChange}
            />
          </Grid>

          <Grid item xs={12}>
            <TextField
              name="notes"
              label="Notas (opcional)"
              fullWidth
              multiline
              minRows={3}
              value={form.notes}
              onChange={handleChange}
            />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancelar</Button>
        <Button onClick={handleSave} variant="contained" disabled={saving}>
          {saving ? "Guardando..." : "Guardar"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
