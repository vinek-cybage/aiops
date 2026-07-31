import { useState } from "react";
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
import {
  listDataSources, createDataSource, deleteDataSource, testDataSourceConnection,
  listIngestionKeys, createIngestionKey, revokeIngestionKey,
} from "../../api/endpoints/dataSources";

const STATUS_COLOR: Record<string, "success" | "error" | "default"> = { connected: "success", error: "error", pending: "default" };

export function DataSourcesPanel({ teamId }: { teamId: number }) {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [keyLabel, setKeyLabel] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  const { data: sources } = useQuery({ queryKey: ["team-data-sources", teamId], queryFn: () => listDataSources(teamId) });
  const { data: keys } = useQuery({ queryKey: ["team-ingestion-keys", teamId], queryFn: () => listIngestionKeys(teamId) });

  const createSourceMutation = useMutation({
    mutationFn: () => createDataSource(teamId, { type: "custom_webhook", display_name: displayName, connection_config: { base_url: baseUrl } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-data-sources", teamId] });
      setAddOpen(false); setDisplayName(""); setBaseUrl("");
    },
  });
  const deleteSourceMutation = useMutation({
    mutationFn: (id: string) => deleteDataSource(teamId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-data-sources", teamId] }),
  });
  const testSourceMutation = useMutation({
    mutationFn: (id: string) => testDataSourceConnection(teamId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-data-sources", teamId] }),
  });

  const createKeyMutation = useMutation({
    mutationFn: () => createIngestionKey(teamId, keyLabel),
    onSuccess: (res) => {
      setNewKey(res.key);
      setKeyLabel("");
      queryClient.invalidateQueries({ queryKey: ["team-ingestion-keys", teamId] });
    },
  });
  const revokeKeyMutation = useMutation({
    mutationFn: (id: string) => revokeIngestionKey(teamId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-ingestion-keys", teamId] }),
  });

  return (
    <Stack spacing={2}>
      <Paper>
        <Box sx={{ p: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">Data Sources</Typography>
            <Button size="small" variant="contained" onClick={() => setAddOpen(true)}>Add data source</Button>
          </Stack>
        </Box>
        <List>
          {(sources ?? []).map((ds) => (
            <ListItem
              key={ds.id}
              secondaryAction={
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip size="small" label={ds.status} color={STATUS_COLOR[ds.status] ?? "default"} />
                  <Button size="small" onClick={() => testSourceMutation.mutate(ds.id)}>Test</Button>
                  <IconButton size="small" onClick={() => deleteSourceMutation.mutate(ds.id)}><DeleteIcon fontSize="small" /></IconButton>
                </Stack>
              }
            >
              <ListItemText primary={ds.display_name} secondary={String(ds.connection_config.base_url ?? ds.type)} />
            </ListItem>
          ))}
          {(sources ?? []).length === 0 && <Typography color="text.secondary" sx={{ p: 2 }}>No data sources configured.</Typography>}
        </List>
      </Paper>

      <Paper>
        <Box sx={{ p: 2 }}>
          <Typography variant="h6">Ingestion Keys</Typography>
          <Typography variant="body2" color="text.secondary">
            Configure your monitoring stack to send telemetry with an <code>X-Ingestion-Key</code> header so it's tagged to this team.
          </Typography>
        </Box>
        <List>
          {(keys ?? []).map((k) => (
            <ListItem
              key={k.id}
              secondaryAction={<Button size="small" onClick={() => revokeKeyMutation.mutate(k.id)}>Revoke</Button>}
            >
              <ListItemText primary={k.label || k.key_prefix} secondary={`${k.key_prefix}...`} />
            </ListItem>
          ))}
        </List>
        <Box sx={{ p: 2, display: "flex", gap: 1 }}>
          <TextField size="small" label="Label" value={keyLabel} onChange={(e) => setKeyLabel(e.target.value)} />
          <Button variant="outlined" onClick={() => createKeyMutation.mutate()} disabled={createKeyMutation.isPending}>
            Issue key
          </Button>
        </Box>
      </Paper>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Add a data source</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {createSourceMutation.isError && <Alert severity="error">{(createSourceMutation.error as Error).message}</Alert>}
            <TextField label="Name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoFocus />
            <TextField label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://..." />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!displayName || createSourceMutation.isPending} onClick={() => createSourceMutation.mutate()}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!newKey} onClose={() => setNewKey(null)} fullWidth maxWidth="sm">
        <DialogTitle>Ingestion key created</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>This key is shown only once — copy it now.</Alert>
          <TextField fullWidth value={newKey ?? ""} InputProps={{ readOnly: true }} onFocus={(e) => e.target.select()} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewKey(null)}>Done</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
