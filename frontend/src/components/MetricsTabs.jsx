import { useState } from "react";
import { Tabs, Tab, Box } from "@mui/material";
import MetricsChart from "./MetricsChart";
import UploadFitbitSleep from "./UploadFitbitSleep";
import UploadStressCSV from "./UploadStressCSV";
import UploadActivityCSV from "./UploadActivityCSV"; // ⬅️ nuevo

function TabPanel({ value, index, children }) {
  if (value !== index) return null;
  return (
    <Box
      role="tabpanel"
      sx={{
        p: 2,
        display: value === index ? "block" : "none",
        width: "100%",
      }}
    >
      {children}
    </Box>
  );
}

export default function MetricsTabs() {
  const [value, setValue] = useState(0);

  const handleChange = (_e, newValue) => {
    setValue(newValue);
  };

  return (
    <Box sx={{ width: "100%" }}>
      <Tabs
        value={value}
        onChange={handleChange}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}
      >
        <Tab label="Sueño" />
        <Tab label="Estrés" />
        <Tab label="Actividad física" />
      </Tabs>

      {/* -------- SUEÑO -------- */}
      <TabPanel value={value} index={0}>
        <MetricsChart metric="sleep" title="Evolución (Sueño)" />
        <UploadFitbitSleep />
      </TabPanel>

      {/* -------- ESTRÉS -------- */}
      <TabPanel value={value} index={1}>
        <MetricsChart metric="stress" title="Evolución (Estrés)" />
        <UploadStressCSV />
      </TabPanel>

      {/* -------- ACTIVIDAD -------- */}
      <TabPanel value={value} index={2}>
        <MetricsChart metric="activity" title="Evolución (Actividad física)" />
        <UploadActivityCSV />
      </TabPanel>
    </Box>
  );
}
