import { createTheme, type ThemeOptions } from "@mui/material/styles";

// Burnt orange & black — deliberately its own identity, not shared with
// web/src/theme/theme.ts (the main app's indigo/purple). Severity chips
// (Chips.tsx, MUI's error/warning/info defaults) and the service-identity
// palette (serviceColors.ts, accessibility-validated) are untouched by this —
// only the brand chrome (AppBar, login screen, active nav, primary buttons)
// uses these tokens. Deliberately a deep burnt orange rather than a bright
// amber, so it reads as distinct from the "warning" severity chip's color.
const brand = {
  orange: "#c2410c",
  black: "#0a0a0a",
};

const shared: ThemeOptions = {
  typography: { fontFamily: "Inter, system-ui, sans-serif" },
  shape: { borderRadius: 8 },
};

const darkOptions: ThemeOptions = {
  ...shared,
  palette: {
    mode: "dark",
    background: { default: "#0f1117", paper: "#1a1d27" },
    divider: "#1e2130",
    primary: { main: brand.orange },
    secondary: { main: brand.black },
    text: { primary: "#e2e8f0", secondary: "#9ca3af", disabled: "#4b5563" },
  },
};

const lightOptions: ThemeOptions = {
  ...shared,
  palette: {
    mode: "light",
    background: { default: "#f8fafc", paper: "#ffffff" },
    divider: "#e2e8f0",
    primary: { main: brand.orange },
    secondary: { main: brand.black },
    text: { primary: "#0f172a", secondary: "#475569" },
  },
};

export const brandGradient = `linear-gradient(135deg, ${brand.orange}, ${brand.black})`;

export function getTheme(mode: "light" | "dark") {
  return createTheme(mode === "dark" ? darkOptions : lightOptions);
}
