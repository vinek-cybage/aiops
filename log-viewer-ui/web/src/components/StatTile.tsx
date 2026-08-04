import { Paper, Typography } from "@mui/material";

function autoCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

export function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <Paper sx={{ p: 3, flex: 1, minWidth: 160 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography sx={{ fontSize: 40, fontWeight: 600, lineHeight: 1.2, mt: 0.5 }}>{autoCompact(value)}</Typography>
    </Paper>
  );
}
