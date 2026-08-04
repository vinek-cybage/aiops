import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import { DashboardPage } from "../pages/dashboard/DashboardPage";
import { IncidentsListPage } from "../pages/incidents/IncidentsListPage";
import { IncidentDetailPage } from "../pages/incidents/IncidentDetailPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "incidents", element: <IncidentsListPage /> },
      { path: "incidents/:incId", element: <IncidentDetailPage /> },
    ],
  },
]);
