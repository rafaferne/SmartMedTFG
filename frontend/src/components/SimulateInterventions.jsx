import { useState } from "react";
import {
  Card, CardHeader, CardContent, CardActions,
  Button, TextField, Grid, Alert, List, ListItem, ListItemText, CircularProgress
} from "@mui/material";
import { useApiFetch } from "../lib/apiFetch";

export default function SimulateInterventions({ metric = "sleep", onSimulated }) {
  const { apiFetch } = useApiFetch();
  const [horizon, setHorizon] = useState(60);
  const [msg, setMsg] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    if (loading) return;
    setLoading(true);
    setMsg(null);

    try {
      const res = await apiFetch(`/ai/simulate/${metric}`, {
        method: "POST",
        body: JSON.stringify({ horizon }),
      });
      const data = await res.json();

      if (!res.ok || data.ok === false) {
        throw new Error(data.error || "Error simulando intervenciones");
      }

      setItems(data.interventions || []);
      setMsg({ type: "success", text: `Simulación creada (${metric})` });
      onSimulated?.();
    } catch (e) {
      setMsg({ type: "error", text: String(e.message || e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader title={`Simular intervenciones (${metric})`} />
      <CardContent>
        {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}
        <Grid container spacing={2}>
          <Grid item xs={12} sm={4}>
            <TextField
              label="Horizonte (min)"
              type="number"
              value={horizon}
              onChange={e => setHorizon(Math.max(30, Math.min(180, Number(e.target.value) || 60)))}
              fullWidth
              disabled={loading}
            />
          </Grid>
        </Grid>
        {items.length > 0 && (
          <>
            <h4 style={{ marginTop: 16 }}>Intervenciones propuestas</h4>
            <List dense>
              {items.map((it, i) => (
                <ListItem key={i}>
                  <ListItemText
                    primary={`${it.title || "(sin título)"}  ·  [${it.category || "general"} · esfuerzo ${it.effort ?? "?"}]`}
                    secondary={it.description}
                  />
                </ListItem>
              ))}
            </List>
          </>
        )}
      </CardContent>
      <CardActions sx={{ pb: 2, px: 2 }}>
        <Button
          variant="contained"
          onClick={run}
          disabled={loading}
          startIcon={loading ? <CircularProgress size={18} /> : null}
        >
          {loading ? "Simulando..." : "Simular ahora"}
        </Button>
      </CardActions>
    </Card>
  );
}
