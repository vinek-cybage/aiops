import { Chip } from "@mui/material";

const SEVERITY_COLOR: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  warning: "warning",
  info: "info",
};

export function SeverityChip({ severity }: { severity: string }) {
  return <Chip label={severity} color={SEVERITY_COLOR[severity] ?? "default"} size="small" variant="outlined" />;
}

export function StatusChip({ status }: { status: string }) {
  return <Chip label={status} color={status === "resolved" ? "success" : "default"} size="small" />;
}
