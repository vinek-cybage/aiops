import { Box, Stack, Typography, useTheme } from "@mui/material";

// Plain SVG (stroke-dasharray trick), no chart library — same convention as
// ServiceBarChart for a chart this simple (2 segments).
const SIZE = 140;
const STROKE = 16;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function StatusDonutChart({ open, total }: { open: number; total: number }) {
  const { palette } = useTheme();
  const resolved = Math.max(total - open, 0);
  const openPct = total > 0 ? open / total : 0;
  const openLength = openPct * CIRCUMFERENCE;

  const openColor = palette.primary.main;
  const resolvedColor = palette.success.main;
  const trackColor = palette.action.disabledBackground;

  return (
    <Stack direction="row" spacing={3} alignItems="center">
      <Box sx={{ position: "relative", width: SIZE, height: SIZE, flexShrink: 0 }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${open} of ${total} incidents open`}>
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={total === 0 ? trackColor : resolvedColor}
            strokeWidth={STROKE}
          />
          {total > 0 && (
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke={openColor}
              strokeWidth={STROKE}
              strokeDasharray={`${openLength} ${CIRCUMFERENCE - openLength}`}
              transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            />
          )}
        </svg>
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography sx={{ fontSize: 26, fontWeight: 700, lineHeight: 1 }}>{total}</Typography>
          <Typography variant="caption" color="text.secondary">
            incidents
          </Typography>
        </Box>
      </Box>

      <Stack spacing={1.25}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: openColor, flexShrink: 0 }} />
          <Typography variant="body2" sx={{ minWidth: 64 }}>
            Open
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
            {open}
          </Typography>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: resolvedColor, flexShrink: 0 }} />
          <Typography variant="body2" sx={{ minWidth: 64 }}>
            Resolved
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
            {resolved}
          </Typography>
        </Stack>
      </Stack>
    </Stack>
  );
}
