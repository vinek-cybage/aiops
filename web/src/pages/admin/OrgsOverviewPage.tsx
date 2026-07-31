import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Chip from "@mui/material/Chip";
import Switch from "@mui/material/Switch";
import Alert from "@mui/material/Alert";
import { listOrganizations, setOrganizationActive } from "../../api/endpoints/platform";

export function OrgsOverviewPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["platform-orgs"], queryFn: listOrganizations });

  const toggleActive = useMutation({
    mutationFn: ({ orgId, isActive }: { orgId: string; isActive: boolean }) => setOrganizationActive(orgId, isActive),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["platform-orgs"] }),
  });

  return (
    <Box>
      <Alert severity="warning" sx={{ mb: 2 }}>
        Platform admin — this view spans every organization on the platform.
      </Alert>
      <Paper>
        <Box sx={{ p: 2 }}>
          <Typography variant="h6">Organizations</Typography>
        </Box>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Slug</TableCell>
                <TableCell align="right">Teams</TableCell>
                <TableCell align="right">Users</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="center">Active</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(data ?? []).map((org) => (
                <TableRow key={org.id} hover>
                  <TableCell>{org.name}</TableCell>
                  <TableCell><Chip size="small" label={org.slug} /></TableCell>
                  <TableCell align="right">{org.team_count}</TableCell>
                  <TableCell align="right">{org.user_count}</TableCell>
                  <TableCell>{new Date(org.created_at).toLocaleDateString()}</TableCell>
                  <TableCell align="center">
                    <Switch
                      size="small"
                      checked={org.is_active}
                      onChange={(e) => toggleActive.mutate({ orgId: org.id, isActive: e.target.checked })}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
}
