import { Box, Stack, Typography, useTheme } from "@mui/material";
import type { ServiceMetric } from "../api/endpoints";
import { serviceColor } from "../theme/serviceColors";

// Plain-HTML horizontal bars (no chart library needed for 2-3 categories) —
// thin marks (16px), rounded data-end at the tip, square at the baseline,
// value labeled at the tip per the mark spec. Color = service identity, with
// the service name as a direct label so nothing relies on color-matching alone.
export function ServiceBarChart({ data }: { data: ServiceMetric[] }) {
  const { palette } = useTheme();
  const max = Math.max(1, ...data.map((d) => d.occurrence_count));

  return (
    <Stack spacing={1.5}>
      {data.map((d) => {
        const pct = (d.occurrence_count / max) * 100;
        const color = serviceColor(d.service, palette.mode);
        return (
          <Box key={d.service} sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" sx={{ width: 160, flexShrink: 0 }}>
              {d.service}
            </Typography>
            <Box sx={{ flex: 1, height: 16, bgcolor: "action.hover", borderRadius: "8px", overflow: "hidden" }}>
              <Box sx={{ width: `${pct}%`, height: "100%", bgcolor: color, borderRadius: "2px 8px 8px 2px" }} />
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ width: 32, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
              {d.occurrence_count}
            </Typography>
          </Box>
        );
      })}
    </Stack>
  );
}
