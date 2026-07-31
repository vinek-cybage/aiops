import Chip from "@mui/material/Chip";

const COLOR_MAP: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  warning: "warning",
  info: "info",
};

export function SeverityChip({ severity }: { severity: string }) {
  return <Chip label={severity} color={COLOR_MAP[severity] ?? "default"} size="small" variant="outlined" />;
}
