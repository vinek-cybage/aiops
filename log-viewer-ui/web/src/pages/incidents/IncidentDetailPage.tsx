import { useQuery } from "@tanstack/react-query";
import { Box, CircularProgress, Divider, List, ListItem, ListItemText, Paper, Stack, Typography } from "@mui/material";
import { useParams } from "react-router-dom";
import { getIncident } from "../../api/endpoints";
import { SeverityChip, StatusChip } from "../../components/Chips";
import { ServiceChip } from "../../components/ServiceChip";

export function IncidentDetailPage() {
  const { incId } = useParams<{ incId: string }>();
  const { data, isLoading } = useQuery({
    queryKey: ["incident", incId],
    queryFn: () => getIncident(incId!),
    enabled: !!incId,
  });

  if (isLoading || !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 3 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="h5">{data.inc_id}</Typography>
          <SeverityChip severity={data.severity} />
          <StatusChip status={data.status} />
        </Stack>
        <Typography variant="h6" sx={{ mt: 1 }}>
          {data.title}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          {data.services.map((s) => (
            <ServiceChip key={s} service={s} />
          ))}
        </Stack>
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          {data.occurrences} occurrence{data.occurrences === 1 ? "" : "s"} · first seen{" "}
          {new Date(data.first_seen).toLocaleString()} · last seen {new Date(data.last_seen).toLocaleString()}
        </Typography>
      </Paper>

      {data.latest_logs && data.latest_logs.length > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>
            Recent logs
          </Typography>
          <Stack spacing={0.5}>
            {data.latest_logs.map((log) => (
              <Box
                key={log.id}
                sx={{
                  borderLeft: "3px solid",
                  borderColor: "error.main",
                  bgcolor: "action.hover",
                  px: 1.5,
                  py: 0.75,
                  borderRadius: "0 4px 4px 0",
                }}
              >
                <Typography component="span" variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", mr: 1.5 }}>
                  {new Date(log.ts).toLocaleString()}
                </Typography>
                <Typography component="span" variant="body2">
                  {log.message}
                </Typography>
              </Box>
            ))}
          </Stack>
        </Paper>
      )}

      {data.timeline && data.timeline.length > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>
            Timeline
          </Typography>
          <List dense>
            {data.timeline.map((entry, i) => (
              <Box key={i}>
                <ListItem disableGutters>
                  <ListItemText primary={entry.event} secondary={entry.time} />
                </ListItem>
                {i < data.timeline!.length - 1 && <Divider component="li" />}
              </Box>
            ))}
          </List>
        </Paper>
      )}
    </Stack>
  );
}
