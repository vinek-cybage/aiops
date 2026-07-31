import { createTheme, type ThemeOptions } from "@mui/material/styles";

// Brand tokens lifted 1:1 from the retired web/style.css so the rebuilt app
// looks near-identical to the original demo on day one.
const brand = {
  indigo: "#6366f1",
  purple: "#8b5cf6",
  purpleLight: "#a78bfa",
};

const shared: ThemeOptions = {
  typography: {
    fontFamily: "Inter, system-ui, sans-serif",
  },
  shape: {
    borderRadius: 8,
  },
};

const darkOptions: ThemeOptions = {
  ...shared,
  palette: {
    mode: "dark",
    background: { default: "#0f1117", paper: "#1a1d27" },
    divider: "#1e2130",
    primary: { main: brand.indigo },
    secondary: { main: brand.purple },
    text: { primary: "#e2e8f0", secondary: "#9ca3af", disabled: "#4b5563" },
  },
};

const lightOptions: ThemeOptions = {
  ...shared,
  palette: {
    mode: "light",
    background: { default: "#f8fafc", paper: "#ffffff" },
    divider: "#e2e8f0",
    primary: { main: brand.indigo },
    secondary: { main: brand.purple },
    text: { primary: "#0f172a", secondary: "#475569" },
  },
};

export const brandGradient = `linear-gradient(135deg, ${brand.indigo}, ${brand.purple})`;

export function getTheme(mode: "light" | "dark") {
  return createTheme(mode === "dark" ? darkOptions : lightOptions);
}
