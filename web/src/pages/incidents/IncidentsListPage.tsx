import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { listIncidents } from "../../api/endpoints/incidents";
import { SeverityChip } from "../../components/incidents/SeverityChip";

export function IncidentsListPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["incidents"],
    queryFn: listIncidents,
    refetchInterval: 10_000,
  });

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Paper>
      <Box sx={{ p: 2 }}>
        <Typography variant="h6">Incidents</Typography>
      </Box>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Title</TableCell>
              <TableCell>Severity</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Team</TableCell>
              <TableCell>Last seen</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(data ?? []).map((inc) => (
              <TableRow key={inc.inc_id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/app/incidents/${inc.inc_id}`)}>
                <TableCell>{inc.inc_id}</TableCell>
                <TableCell>{inc.title}</TableCell>
                <TableCell><SeverityChip severity={inc.severity} /></TableCell>
                <TableCell>
                  <Chip
                    label={inc.status}
                    size="small"
                    color={inc.status === "resolved" ? "success" : "default"}
                  />
                </TableCell>
                <TableCell>{inc.team}</TableCell>
                <TableCell>{inc.last_seen ? new Date(inc.last_seen).toLocaleString() : "—"}</TableCell>
              </TableRow>
            ))}
            {(data ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" sx={{ p: 2 }}>
                    No incidents yet.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}
