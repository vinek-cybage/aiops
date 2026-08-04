import { useQuery } from "@tanstack/react-query";
import { Box, CircularProgress, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { getMetrics } from "../../api/endpoints";
import { StatTile } from "../../components/StatTile";
import { ServiceBarChart } from "../../components/ServiceBarChart";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["metrics"], queryFn: getMetrics, refetchInterval: 10_000 });

  if (isLoading || !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} flexWrap="wrap">
        <StatTile label="Total incidents" value={data.total_incidents} />
        <StatTile label="Open incidents" value={data.open_incidents} />
        <StatTile label="Total occurrences" value={data.total_occurrences} />
        <StatTile label="Deduplicated" value={data.deduped_count} />
      </Stack>

      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Occurrences by service
        </Typography>
        {data.by_service.length === 0 ? (
          <Typography color="text.secondary">No incidents yet.</Typography>
        ) : (
          <ServiceBarChart data={data.by_service} />
        )}
      </Paper>

      <Paper sx={{ p: 0 }}>
        <Box sx={{ p: 2 }}>
          <Typography variant="h6">Recent incidents</Typography>
        </Box>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Title</TableCell>
              <TableCell>Services</TableCell>
              <TableCell align="right">Occurrences</TableCell>
              <TableCell>Last seen</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.recent_incidents.map((inc) => (
              <TableRow key={inc.inc_id} hover onClick={() => navigate(`/incidents/${inc.inc_id}`)} sx={{ cursor: "pointer" }}>
                <TableCell>{inc.inc_id}</TableCell>
                <TableCell>{inc.title}</TableCell>
                <TableCell>{inc.services.join(", ")}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                  {inc.occurrences}
                </TableCell>
                <TableCell>{new Date(inc.last_seen).toLocaleString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
