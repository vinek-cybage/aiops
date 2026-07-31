import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Paper from "@mui/material/Paper";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import { createTeam, listTeams } from "../../api/endpoints/teams";
import { useAuthStore } from "../../auth/authStore";

export function TeamsListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canCreateTeam = user?.role === "org_admin" || user?.role === "platform_admin";

  const [createOpen, setCreateOpen] = useState(false);
  const [teamName, setTeamName] = useState("");

  const { data } = useQuery({ queryKey: ["teams"], queryFn: listTeams });

  const createMutation = useMutation({
    mutationFn: () => createTeam(teamName.trim()),
    onSuccess: (team) => {
      setCreateOpen(false);
      setTeamName("");
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      navigate(`/app/team/${team.id}`);
    },
  });

  function closeDialog() {
    setCreateOpen(false);
    setTeamName("");
    createMutation.reset();
  }

  return (
    <Paper>
      <Box sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">Teams</Typography>
          {canCreateTeam && (
            <Button variant="contained" size="small" onClick={() => setCreateOpen(true)}>
              Create team
            </Button>
          )}
        </Stack>
      </Box>
      <List>
        {(data ?? []).map((team) => (
          <ListItemButton key={team.id} onClick={() => navigate(`/app/team/${team.id}`)}>
            <ListItemText primary={team.name} secondary={team.services.join(", ") || "No services configured"} />
          </ListItemButton>
        ))}
        {(data ?? []).length === 0 && (
          <Typography color="text.secondary" sx={{ p: 2 }}>
            No teams yet.
          </Typography>
        )}
      </List>

      <Dialog open={createOpen} onClose={closeDialog} fullWidth maxWidth="xs">
        <DialogTitle>Create a team</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {createMutation.isError && <Alert severity="error">{(createMutation.error as Error).message}</Alert>}
            <TextField
              label="Team name"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && teamName.trim() && !createMutation.isPending) createMutation.mutate();
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!teamName.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
