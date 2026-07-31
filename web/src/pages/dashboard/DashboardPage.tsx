import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import { useAuthStore } from "../../auth/authStore";

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 1 }}>
        Welcome{user ? `, ${user.name}` : ""}
      </Typography>
      <Typography color="text.secondary">
        This is the new authenticated shell. Incidents, catalog, and log-upload pages are ported here next.
      </Typography>
    </Paper>
  );
}
