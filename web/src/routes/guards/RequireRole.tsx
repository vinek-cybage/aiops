import { Outlet } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useAuthStore } from "../../auth/authStore";
import type { AuthUser } from "../../auth/types";

export function RequireRole({ roles }: { roles: Array<AuthUser["role"]> }) {
  const { user } = useAuthStore();
  const allowed = !!user && (roles.includes(user.role) || user.role === "platform_admin");

  if (!allowed) {
    return (
      <Box sx={{ p: 4 }}>
        <Typography variant="h6">Not authorized</Typography>
        <Typography color="text.secondary">You don't have permission to view this page.</Typography>
      </Box>
    );
  }

  return <Outlet />;
}
