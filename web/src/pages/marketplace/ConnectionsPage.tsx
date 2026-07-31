import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import DeleteIcon from "@mui/icons-material/Delete";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import { listTeamMcpInstances, createTeamMcpInstance, deleteTeamMcpInstance, testMcpInstanceConnection } from "../../api/endpoints/mcp";
import { TeamTabs } from "../team/TeamTabs";

const STATUS_COLOR: Record<string, "success" | "error" | "default"> = {
  connected: "success",
  error: "error",
  pending: "default",
};

export function ConnectionsPage() {
  const { teamId: teamIdParam } = useParams<{ teamId: string }>();
  const teamId = Number(teamIdParam);
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");

  const { data: instances } = useQuery({ queryKey: ["team-mcp-instances", teamId], queryFn: () => listTeamMcpInstances(teamId) });

  const createMutation = useMutation({
    mutationFn: () =>
      createTeamMcpInstance(teamId, {
        source: "custom",
        display_name: displayName,
        connection_type: "streamable_http",
        endpoint_url: endpointUrl,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-mcp-instances", teamId] });
      setAddOpen(false);
      setDisplayName("");
      setEndpointUrl("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteTeamMcpInstance(teamId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-mcp-instances", teamId] }),
  });

  const testMutation = useMutation({
    mutationFn: (id: string) => testMcpInstanceConnection(teamId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-mcp-instances", teamId] }),
  });

  return (
    <>
      <TeamTabs />
      <Paper>
        <Box sx={{ p: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">MCP Connections</Typography>
            <Button variant="contained" size="small" onClick={() => setAddOpen(true)}>
              Add custom/remote MCP
            </Button>
          </Stack>
        </Box>
        <List>
          {(instances ?? []).map((inst) => (
            <ListItem
              key={inst.id}
              secondaryAction={
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip size="small" label={inst.status} color={STATUS_COLOR[inst.status] ?? "default"} />
                  <Button size="small" onClick={() => testMutation.mutate(inst.id)}>Test</Button>
                  <IconButton size="small" onClick={() => deleteMutation.mutate(inst.id)}><DeleteIcon fontSize="small" /></IconButton>
                </Stack>
              }
            >
              <ListItemText
                primary={inst.display_name}
                secondary={`${inst.endpoint_url ?? "no endpoint"}${inst.credential_masked ? ` · ${inst.credential_masked}` : ""}${inst.last_error ? ` · ${inst.last_error}` : ""}`}
              />
            </ListItem>
          ))}
          {(instances ?? []).length === 0 && (
            <Typography color="text.secondary" sx={{ p: 2 }}>No MCP servers configured for this team yet.</Typography>
          )}
        </List>
      </Paper>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Add a custom/remote MCP server</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {createMutation.isError && <Alert severity="error">{(createMutation.error as Error).message}</Alert>}
            <TextField label="Name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoFocus />
            <TextField label="Endpoint URL" value={endpointUrl} onChange={(e) => setEndpointUrl(e.target.value)} placeholder="https://..." />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!displayName || !endpointUrl || createMutation.isPending} onClick={() => createMutation.mutate()}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
