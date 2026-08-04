import { AppBar, Box, Drawer, IconButton, List, ListItemButton, ListItemText, Toolbar, Typography } from "@mui/material";
import LightModeIcon from "@mui/icons-material/LightMode";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import { NavLink, Outlet } from "react-router-dom";
import { brandGradient } from "../theme/theme";
import { useThemeMode } from "../theme/ThemeModeProvider";

const DRAWER_WIDTH = 220;

const NAV_ITEMS = [
  { label: "Dashboard", to: "/dashboard" },
  { label: "Incidents", to: "/incidents" },
  { label: "Graph", to: "/graph" },
];

export function AppLayout() {
  const { mode, toggle } = useThemeMode();

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" elevation={0} sx={{ background: brandGradient, zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          <Typography variant="h6" sx={{ fontWeight: 700, flexGrow: 1 }}>
            Log Viewer
          </Typography>
          <IconButton color="inherit" onClick={toggle}>
            {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
          </IconButton>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <Toolbar />
        <List>
          {NAV_ITEMS.map((item) => (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              sx={{
                "&.active": {
                  bgcolor: "action.selected",
                  borderRight: "3px solid",
                  borderColor: "primary.main",
                },
              }}
            >
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
