import { Outlet, useNavigate } from "react-router-dom";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import { ThemeToggle } from "../theme/ThemeToggle";
import { brandGradient } from "../theme/theme";
import { useAuthStore } from "../auth/authStore";
import { logout as apiLogout } from "../api/endpoints/auth";

const DRAWER_WIDTH = 220;

const NAV_ITEMS = [
  { label: "Dashboard", path: "/app/dashboard" },
  { label: "Incidents", path: "/app/incidents" },
  { label: "Upload logs", path: "/app/upload" },
  { label: "Teams", path: "/app/team" },
  { label: "Marketplace", path: "/app/marketplace" },
];

const PLATFORM_ADMIN_NAV_ITEM = { label: "Admin", path: "/app/admin" };

export function AppLayout() {
  const { user, clearSession } = useAuthStore();
  const navigate = useNavigate();
  const navItems = user?.role === "platform_admin" ? [...NAV_ITEMS, PLATFORM_ADMIN_NAV_ITEM] : NAV_ITEMS;

  async function handleLogout() {
    try {
      await apiLogout();
    } finally {
      clearSession();
      navigate("/login");
    }
  }

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1, background: brandGradient }} elevation={0}>
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 700 }}>
            AIOps
          </Typography>
          <ThemeToggle />
          {user && (
            <Typography variant="body2" sx={{ opacity: 0.9 }}>
              {user.name}
            </Typography>
          )}
          <Button color="inherit" size="small" onClick={handleLogout}>
            Log out
          </Button>
        </Toolbar>
      </AppBar>
      <Drawer
        variant="permanent"
        sx={{ width: DRAWER_WIDTH, flexShrink: 0, [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: "border-box" } }}
      >
        <Toolbar />
        <List>
          {navItems.map((item) => (
            <ListItemButton key={item.path} onClick={() => navigate(item.path)}>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
