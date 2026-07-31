import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import { getGithubIntegration, upsertGithubIntegration, testGithubIntegration } from "../../api/endpoints/github";

const STATUS_COLOR: Record<string, "success" | "error" | "default"> = { connected: "success", error: "error", pending: "default" };

export function GitHubIntegrationPanel({ teamId }: { teamId: number }) {
  const queryClient = useQueryClient();
  const { data: integration } = useQuery({ queryKey: ["github-integration", teamId], queryFn: () => getGithubIntegration(teamId) });

  const [repo, setRepo] = useState("");
  const [baseBranch, setBaseBranch] = useState("main");
  const [token, setToken] = useState("");

  useEffect(() => {
    if (integration) {
      setRepo(integration.repo_full_name);
      setBaseBranch(integration.base_branch);
    }
  }, [integration]);

  const saveMutation = useMutation({
    mutationFn: () => upsertGithubIntegration(teamId, { repo_full_name: repo, base_branch: baseBranch, token: token || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["github-integration", teamId] });
      setToken("");
    },
  });

  const testMutation = useMutation({
    mutationFn: () => testGithubIntegration(teamId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["github-integration", teamId] }),
  });

  return (
    <Paper sx={{ p: 2, maxWidth: 480 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h6">GitHub Integration</Typography>
        {integration && <Chip size="small" label={integration.status} color={STATUS_COLOR[integration.status] ?? "default"} />}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Used for "Raise PR" remediation actions on this team's incidents — replaces the global GITHUB_TOKEN env var.
      </Typography>
      {saveMutation.isError && <Alert severity="error" sx={{ mb: 2 }}>{(saveMutation.error as Error).message}</Alert>}
      {integration?.last_error && <Alert severity="warning" sx={{ mb: 2 }}>{integration.last_error}</Alert>}
      <Stack spacing={2}>
        <TextField label="Repository (owner/repo)" value={repo} onChange={(e) => setRepo(e.target.value)} />
        <TextField label="Base branch" value={baseBranch} onChange={(e) => setBaseBranch(e.target.value)} />
        <TextField
          label="Personal Access Token"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={integration?.token_masked ? `Current: ${integration.token_masked} (leave blank to keep)` : ""}
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" disabled={!repo || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save
          </Button>
          {integration && (
            <Button variant="outlined" onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
              Test connection
            </Button>
          )}
        </Stack>
      </Stack>
    </Paper>
  );
}
