import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Alert from "@mui/material/Alert";
import VerifiedIcon from "@mui/icons-material/Verified";
import { listMcpCatalog, createTeamMcpInstance, type McpCatalogEntry } from "../../api/endpoints/mcp";
import { listTeams } from "../../api/endpoints/teams";
import { DynamicSchemaForm } from "../../components/mcp/DynamicSchemaForm";

export function MarketplaceGridPage() {
  const { data: catalog } = useQuery({ queryKey: ["mcp-catalog"], queryFn: listMcpCatalog });
  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: listTeams });
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<McpCatalogEntry | null>(null);
  const [teamId, setTeamId] = useState<number | "">("");
  const [displayName, setDisplayName] = useState("");
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [credValues, setCredValues] = useState<Record<string, string>>({});

  const addMutation = useMutation({
    mutationFn: () =>
      createTeamMcpInstance(teamId as number, {
        catalog_entry_id: selected!.id,
        source: "catalog",
        display_name: displayName || selected!.name,
        connection_type: selected!.connection_type,
        endpoint_url: selected!.default_endpoint_url ?? (configValues.base_url || undefined),
        config: configValues,
        credentials: Object.keys(credValues).length ? credValues : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-mcp-instances"] });
      closeDialog();
    },
  });

  function openDialog(entry: McpCatalogEntry) {
    setSelected(entry);
    setDisplayName(entry.name);
    setConfigValues({});
    setCredValues({});
    setTeamId(teams?.[0]?.id ?? "");
  }

  function closeDialog() {
    setSelected(null);
    addMutation.reset();
  }

  return (
    <>
      <Typography variant="h5" sx={{ mb: 2 }}>MCP Marketplace</Typography>
      <Grid container spacing={2}>
        {(catalog ?? []).map((entry) => (
          <Grid item xs={12} sm={6} md={4} key={entry.id}>
            <Card variant="outlined" sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
              <CardContent sx={{ flexGrow: 1 }}>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                  <Typography variant="h6">{entry.name}</Typography>
                  {entry.is_verified && <VerifiedIcon color="primary" fontSize="small" />}
                </Stack>
                {entry.vendor && <Chip size="small" label={entry.vendor} sx={{ mb: 1 }} />}
                <Typography variant="body2" color="text.secondary">{entry.description}</Typography>
              </CardContent>
              <CardActions>
                <Button size="small" onClick={() => openDialog(entry)}>Add to team</Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={!!selected} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>Configure {selected?.name}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {addMutation.isError && <Alert severity="error">{(addMutation.error as Error).message}</Alert>}
            <Select value={teamId} onChange={(e) => setTeamId(Number(e.target.value))} displayEmpty size="small">
              <MenuItem value="" disabled>Select a team</MenuItem>
              {(teams ?? []).map((t) => (
                <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
              ))}
            </Select>
            {selected && selected.config_schema.length > 0 && (
              <DynamicSchemaForm schema={selected.config_schema} values={configValues} onChange={setConfigValues} />
            )}
            {selected && selected.credential_schema.length > 0 && (
              <DynamicSchemaForm schema={selected.credential_schema} values={credValues} onChange={setCredValues} />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button variant="contained" disabled={!teamId || addMutation.isPending} onClick={() => addMutation.mutate()}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
