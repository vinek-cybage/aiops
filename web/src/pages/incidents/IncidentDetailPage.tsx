import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import { getIncident, resolveIncident, applyAction } from "../../api/endpoints/incidents";
import { SeverityChip } from "../../components/incidents/SeverityChip";

export function IncidentDetailPage() {
  const { incId } = useParams<{ incId: string }>();
  const queryClient = useQueryClient();

  const { data: incident, isLoading } = useQuery({
    queryKey: ["incidents", incId],
    queryFn: () => getIncident(incId!),
    enabled: !!incId,
    refetchInterval: 10_000,
  });

  const resolveMutation = useMutation({
    mutationFn: () => resolveIncident(incId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const applyActionMutation = useMutation({
    mutationFn: (actionId: number) => applyAction(incId!, actionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  if (isLoading || !incident) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 3 }}>
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
          <Typography variant="h5">{incident.inc_id}</Typography>
          <SeverityChip severity={incident.severity} />
          {incident.status === "open" && (
            <Button size="small" variant="outlined" onClick={() => resolveMutation.mutate()} disabled={resolveMutation.isPending}>
              Mark resolved
            </Button>
          )}
        </Stack>
        <Typography variant="h6">{incident.title}</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          Team: {incident.team} · Services: {incident.services.join(", ") || "—"}
        </Typography>
        {incident.ai_summary && <Typography sx={{ whiteSpace: "pre-wrap" }}>{incident.ai_summary}</Typography>}
      </Paper>

      {incident.hypotheses.length > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>Hypotheses</Typography>
          <List dense>
            {incident.hypotheses.map((h, i) => (
              <ListItem key={i}>
                <ListItemText primary={`${h.rank}. ${h.text}`} secondary={`Confidence: ${h.confidence}%`} />
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {incident.actions && incident.actions.length > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>Suggested actions</Typography>
          <List dense>
            {incident.actions.map((a) => (
              <ListItem
                key={a.id}
                secondaryAction={
                  a.status === "applied" ? (
                    <Typography variant="body2" color="text.secondary">Applied</Typography>
                  ) : (
                    <Button size="small" onClick={() => applyActionMutation.mutate(a.action_id)} disabled={applyActionMutation.isPending}>
                      Apply
                    </Button>
                  )
                }
              >
                <ListItemText primary={a.name} secondary={a.description} />
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {incident.timeline.length > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>Timeline</Typography>
          <List dense>
            {incident.timeline.map((t, i) => (
              <div key={i}>
                <ListItem>
                  <ListItemText primary={t.event} secondary={t.time} />
                </ListItem>
                {i < incident.timeline.length - 1 && <Divider component="li" />}
              </div>
            ))}
          </List>
        </Paper>
      )}
    </Stack>
  );
}
