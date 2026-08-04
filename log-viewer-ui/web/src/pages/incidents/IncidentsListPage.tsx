import { useQuery } from "@tanstack/react-query";
import { Box, CircularProgress, Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { listIncidents } from "../../api/endpoints";
import { SeverityChip, StatusChip } from "../../components/Chips";
import { ServiceChip } from "../../components/ServiceChip";

export function IncidentsListPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["incidents"], queryFn: listIncidents, refetchInterval: 10_000 });

  return (
    <Paper>
      <Box sx={{ p: 2 }}>
        <Typography variant="h6">Incidents</Typography>
      </Box>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>ID</TableCell>
            <TableCell>Title</TableCell>
            <TableCell>Severity</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Services</TableCell>
            <TableCell align="right">Occurrences</TableCell>
            <TableCell>Last seen</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {isLoading ? (
            <TableRow>
              <TableCell colSpan={7}>
                <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
                  <CircularProgress />
                </Box>
              </TableCell>
            </TableRow>
          ) : !data || data.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7}>
                <Typography color="text.secondary" sx={{ p: 2 }}>
                  No incidents yet.
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            data.map((inc) => (
              <TableRow key={inc.inc_id} hover onClick={() => navigate(`/incidents/${inc.inc_id}`)} sx={{ cursor: "pointer" }}>
                <TableCell>{inc.inc_id}</TableCell>
                <TableCell>{inc.title}</TableCell>
                <TableCell>
                  <SeverityChip severity={inc.severity} />
                </TableCell>
                <TableCell>
                  <StatusChip status={inc.status} />
                </TableCell>
                <TableCell>
                  {inc.services.map((s) => (
                    <ServiceChip key={s} service={s} />
                  ))}
                </TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                  {inc.occurrences}
                </TableCell>
                <TableCell>{new Date(inc.last_seen).toLocaleString()}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </Paper>
  );
}
