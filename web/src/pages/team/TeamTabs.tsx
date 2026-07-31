import { useNavigate, useLocation, useParams } from "react-router-dom";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";

const TABS = [
  { label: "Members", suffix: "" },
  { label: "MCP Connections", suffix: "/connections" },
  { label: "Integrations", suffix: "/integrations" },
];

export function TeamTabs() {
  const { teamId } = useParams<{ teamId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const base = `/app/team/${teamId}`;
  const current = TABS.findIndex((t) => location.pathname === `${base}${t.suffix}`);

  return (
    <Box sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
      <Tabs value={current === -1 ? 0 : current} onChange={(_, i) => navigate(`${base}${TABS[i].suffix}`)}>
        {TABS.map((t) => (
          <Tab key={t.label} label={t.label} />
        ))}
      </Tabs>
    </Box>
  );
}
