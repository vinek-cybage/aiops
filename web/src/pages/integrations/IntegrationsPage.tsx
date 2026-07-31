import { useState } from "react";
import { useParams } from "react-router-dom";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";
import { TeamTabs } from "../team/TeamTabs";
import { DataSourcesPanel } from "./DataSourcesPanel";
import { GitHubIntegrationPanel } from "./GitHubIntegrationPanel";

export function IntegrationsPage() {
  const { teamId: teamIdParam } = useParams<{ teamId: string }>();
  const teamId = Number(teamIdParam);
  const [tab, setTab] = useState(0);

  return (
    <>
      <TeamTabs />
      <Box sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Data Sources" />
          <Tab label="GitHub" />
        </Tabs>
      </Box>
      {tab === 0 && <DataSourcesPanel teamId={teamId} />}
      {tab === 1 && <GitHubIntegrationPanel teamId={teamId} />}
    </>
  );
}
