import {
  Card, CardHeader, CardContent, CardActions,
  Avatar, Typography, Chip, Grid, Divider, Stack, Tooltip
} from "@mui/material";
import LocalHospitalIcon from "@mui/icons-material/LocalHospital";

function safeNum(n) {
  const x = Number(n);
  return Number.isFinite(x) ? x : null;
}

function calcBMI(height_cm, weight_kg) {
  const h = safeNum(height_cm);
  const w = safeNum(weight_kg);
  if (!h || !w) return null;
  const m = h / 100;
  const bmi = w / (m * m);
  return Math.round(bmi * 10) / 10;
}

function bmiLabel(bmi) {
  if (bmi == null) return "—";
  if (bmi < 18.5) return "Bajo peso";
  if (bmi < 25) return "Normal";
  if (bmi < 30) return "Sobrepeso";
  return "Obesidad";
}

export default function UserProfileCard({ doc }) {
  // doc viene de /api/me → { sub, email?, name?, picture?, profile, profileComplete, ... }
  const p = doc?.profile || {};
  const bmi = calcBMI(p.height_cm, p.weight_kg);

  return (
    <Card sx={{ overflow: "hidden" }}>
      <CardHeader
        avatar={
          <Avatar
            src={doc?.picture || undefined}
            sx={{ bgcolor: "primary.main" }}
            alt={doc?.name || "Usuario"}
          >
            <LocalHospitalIcon fontSize="small" />
          </Avatar>
        }
        title={<Typography variant="h6">{doc?.name || "Usuario"}</Typography>}
        subheader={doc?.email || doc?.sub}
      />

      <Divider />

      <CardContent>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <Typography variant="overline" color="text.secondary">Fecha de nacimiento</Typography>
            <Typography variant="body1">{p.birthdate || "—"}</Typography>
          </Grid>

          <Grid item xs={12} sm={6}>
            <Typography variant="overline" color="text.secondary">Sexo</Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
              <Chip
                label={
                  p.sex === "male" ? "Hombre" :
                  p.sex === "female" ? "Mujer" :
                  p.sex === "other" ? "Otro" :
                  p.sex === "prefer_not_say" ? "Prefiere no decir" : "—"
                }
                color="primary"
                variant="outlined"
                size="small"
              />
              {doc?.profileComplete && <Chip label="Perfil completo" color="success" size="small" />}
            </Stack>
          </Grid>

          <Grid item xs={6} sm={3}>
            <Typography variant="overline" color="text.secondary">Altura</Typography>
            <Typography variant="h6">{p.height_cm ? `${p.height_cm} cm` : "—"}</Typography>
          </Grid>

          <Grid item xs={6} sm={3}>
            <Typography variant="overline" color="text.secondary">Peso</Typography>
            <Typography variant="h6">{p.weight_kg ? `${p.weight_kg} kg` : "—"}</Typography>
          </Grid>

          <Grid item xs={12} sm={6}>
            <Typography variant="overline" color="text.secondary">IMC</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="h6">{bmi ?? "—"}</Typography>
              <Chip
                label={bmiLabel(bmi)}
                color={bmi == null ? "default" :
                       bmi < 25 ? "success" :
                       bmi < 30 ? "warning" : "error"}
                size="small"
              />
            </Stack>
            {bmi != null && (
              <Typography variant="caption" color="text.secondary">
                IMC = peso / (altura en m)²
              </Typography>
            )}
          </Grid>

          {p.notes && (
            <Grid item xs={12}>
              <Typography variant="overline" color="text.secondary">Notas</Typography>
              <Typography variant="body1">{p.notes}</Typography>
            </Grid>
          )}
        </Grid>
      </CardContent>

      <CardActions sx={{ px: 2, pb: 2 }}>
        <Tooltip title={doc?.sub}>
          <Chip label="ID externo" size="small" variant="outlined" />
        </Tooltip>
      </CardActions>
    </Card>
  );
}
