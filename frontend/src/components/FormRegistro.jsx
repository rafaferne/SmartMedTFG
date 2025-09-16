import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  Card, CardContent, CardActions, Button, Grid,
  TextField, MenuItem, Typography, Alert
} from "@mui/material";

const API = import.meta.env.VITE_API_BASE;
const AUD = import.meta.env.VITE_AUTH0_AUDIENCE;

export default function OnboardingForm({ onDone }) {
  const { getAccessTokenSilently } = useAuth0();
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    setErr("");

    const form = new FormData(e.currentTarget);
    const payload = {
      birthdate: form.get("birthdate") || null,
      sex: form.get("sex") || "prefer_not_say",
      height_cm: form.get("height_cm") ? Number(form.get("height_cm")) : null,
      weight_kg: form.get("weight_kg") ? Number(form.get("weight_kg")) : null,
      notes: form.get("notes") || "",
    };

    try {
      const token = await getAccessTokenSilently({
        authorizationParams: { audience: AUD },
      });
      const res = await fetch(`${API}/me/profile`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "Error guardando perfil");
      onDone?.(data.user);
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  return (
    <Card sx={{ maxWidth: 720, mx: "auto", mt: 3 }}>
      <CardContent>
        <Typography variant="h5" gutterBottom>Completa tu perfil</Typography>
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        <form onSubmit={submit} id="onboardingForm">
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField name="birthdate" label="Fecha de nacimiento" type="date"
                InputLabelProps={{ shrink: true }} fullWidth />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField select name="sex" label="Sexo" defaultValue="prefer_not_say" required>
                <MenuItem value="male">Hombre</MenuItem>
                <MenuItem value="female">Mujer</MenuItem>
                <MenuItem value="other">Otro</MenuItem>
                <MenuItem value="prefer_not_say">Prefiero no decir</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField name="height_cm" label="Altura (cm)" type="number"
                inputProps={{ min: 40, max: 300, step: 0.1 }} required />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField name="weight_kg" label="Peso (kg)" type="number"
                inputProps={{ min: 1, max: 600, step: 0.1 }} required />
            </Grid>
            <Grid item xs={12}>
              <TextField name="notes" label="Notas (opcional)" multiline minRows={3} />
            </Grid>
          </Grid>
        </form>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Button type="submit" form="onboardingForm" variant="contained">Guardar</Button>
      </CardActions>
    </Card>
  );
}
