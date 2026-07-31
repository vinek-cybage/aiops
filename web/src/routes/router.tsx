import { createBrowserRouter, Navigate } from "react-router-dom";
import { RequireAuth } from "./guards/RequireAuth";
import { RequireRole } from "./guards/RequireRole";
import { AppLayout } from "./AppLayout";
import { LoginPage } from "../pages/auth/LoginPage";
import { RegisterOrgPage } from "../pages/auth/RegisterOrgPage";
import { InviteAcceptPage } from "../pages/auth/InviteAcceptPage";
import { DashboardPage } from "../pages/dashboard/DashboardPage";
import { IncidentsListPage } from "../pages/incidents/IncidentsListPage";
import { IncidentDetailPage } from "../pages/incidents/IncidentDetailPage";
import { LogUploadPage } from "../pages/uploads/LogUploadPage";
import { TeamsListPage } from "../pages/team/TeamsListPage";
import { TeamMembersPage } from "../pages/team/TeamMembersPage";
import { OrgsOverviewPage } from "../pages/admin/OrgsOverviewPage";
import { MarketplaceGridPage } from "../pages/marketplace/MarketplaceGridPage";
import { ConnectionsPage } from "../pages/marketplace/ConnectionsPage";
import { IntegrationsPage } from "../pages/integrations/IntegrationsPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/app/dashboard" replace /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterOrgPage /> },
  { path: "/invite/:token", element: <InviteAcceptPage /> },
  {
    path: "/app",
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="dashboard" replace /> },
          { path: "dashboard", element: <DashboardPage /> },
          { path: "incidents", element: <IncidentsListPage /> },
          { path: "incidents/:incId", element: <IncidentDetailPage /> },
          { path: "upload", element: <LogUploadPage /> },
          { path: "team", element: <TeamsListPage /> },
          { path: "team/:teamId", element: <TeamMembersPage /> },
          { path: "team/:teamId/connections", element: <ConnectionsPage /> },
          { path: "team/:teamId/integrations", element: <IntegrationsPage /> },
          { path: "marketplace", element: <MarketplaceGridPage /> },
          {
            path: "admin",
            element: <RequireRole roles={["platform_admin"]} />,
            children: [{ index: true, element: <OrgsOverviewPage /> }],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
