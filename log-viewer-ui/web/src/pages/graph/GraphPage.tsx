import { useQuery } from "@tanstack/react-query";
import { Box, CircularProgress, Paper, Stack, Typography, useTheme } from "@mui/material";
import { getGraph } from "../../api/endpoints";
import { serviceColor } from "../../theme/serviceColors";

const SIZE = 640;
const CENTER = SIZE / 2;
const RADIUS = 240;
const NODE_R = 12;

const REASON_LABEL: Record<string, string> = {
  same_fault_family: "Same fault family (semantic match)",
  correlated_in_time: "Correlated in time",
};

export function GraphPage() {
  const { palette } = useTheme();
  const { data, isLoading } = useQuery({ queryKey: ["graph"], queryFn: getGraph, refetchInterval: 10_000 });

  if (isLoading || !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  const { nodes, edges } = data;

  if (nodes.length === 0) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography color="text.secondary">No incidents yet — the graph will populate as errors are clustered.</Typography>
      </Paper>
    );
  }

  // Sort by service so same-service incidents land next to each other on the
  // circle — a cheap, deterministic layout that needs no physics simulation
  // given how few nodes/edges this design produces (see neo4j_store.py).
  const sorted = [...nodes].sort((a, b) => a.service.localeCompare(b.service) || a.incident_id.localeCompare(b.incident_id));
  const positions = new Map<string, { x: number; y: number }>();
  sorted.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / sorted.length - Math.PI / 2;
    positions.set(n.incident_id, {
      x: CENTER + RADIUS * Math.cos(angle),
      y: CENTER + RADIUS * Math.sin(angle),
    });
  });

  const surface = palette.background.paper;
  const servicesPresent = Array.from(new Set(nodes.map((n) => n.service)));

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Incident graph
        </Typography>

        <Stack direction="row" spacing={3} sx={{ mb: 2 }} flexWrap="wrap">
          {servicesPresent.map((s) => (
            <Stack key={s} direction="row" spacing={1} alignItems="center">
              <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: serviceColor(s, palette.mode) }} />
              <Typography variant="body2">{s}</Typography>
            </Stack>
          ))}
          {edges.length > 0 && (
            <Stack direction="row" spacing={1} alignItems="center">
              <Box sx={{ width: 20, height: 2, bgcolor: "text.secondary" }} />
              <Typography variant="body2" color="text.secondary">
                related (hover for why)
              </Typography>
            </Stack>
          )}
        </Stack>

        <Box sx={{ width: "100%", overflowX: "auto" }}>
          <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="Incident relationship graph">
            {edges.map((e, i) => {
              const from = positions.get(e.source);
              const to = positions.get(e.target);
              if (!from || !to) return null;
              const detail =
                e.reason === "same_fault_family"
                  ? `${REASON_LABEL[e.reason]} — similarity ${e.similarity?.toFixed(2)}`
                  : `${REASON_LABEL[e.reason] ?? e.reason}${e.seconds_apart != null ? ` — ${e.seconds_apart}s apart` : ""}`;
              return (
                <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={palette.text.secondary} strokeWidth={2} strokeLinecap="round">
                  <title>{`${e.source} ↔ ${e.target}: ${detail}`}</title>
                </line>
              );
            })}

            {sorted.map((n) => {
              const pos = positions.get(n.incident_id)!;
              const color = serviceColor(n.service, palette.mode);
              return (
                <g key={n.incident_id}>
                  <circle cx={pos.x} cy={pos.y} r={NODE_R} fill={color} stroke={surface} strokeWidth={2}>
                    <title>{`${n.incident_id} (${n.service})\n${n.title}\n${n.occurrences} occurrence(s)`}</title>
                  </circle>
                  <text
                    x={pos.x}
                    y={pos.y + NODE_R + 14}
                    textAnchor="middle"
                    fontSize={11}
                    fill={palette.text.secondary}
                    fontFamily="Inter, system-ui, sans-serif"
                  >
                    {n.incident_id}
                  </text>
                </g>
              );
            })}
          </svg>
        </Box>
      </Paper>
    </Stack>
  );
}
