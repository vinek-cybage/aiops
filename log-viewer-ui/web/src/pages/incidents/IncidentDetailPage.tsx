import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Divider, List, ListItem, ListItemText, Paper, Stack, Typography } from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { confirmResolve, getIncident, previewResolve, RawLog } from "../../api/endpoints";
import { SeverityChip, StatusChip } from "../../components/Chips";
import { ServiceChip } from "../../components/ServiceChip";

function buildDistinctLogs(logs: RawLog[]): (RawLog & { count: number })[] {
  return Array.from(
    logs
      .reduce((map, log) => {
        if (!map.has(log.message)) map.set(log.message, { ...log, count: 1 });
        else map.get(log.message)!.count++;
        return map;
      }, new Map<string, RawLog & { count: number }>())
      .values()
  );
}

export function IncidentDetailPage() {
  const { incId } = useParams<{ incId: string }>();
  const queryClient = useQueryClient();
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["incident", incId],
    queryFn: () => getIncident(incId!),
    enabled: !!incId,
  });

  // Step 1: ask LLM what to do — opens confirmation dialog
  const { mutate: preview, isPending: previewing, error: previewError } = useMutation({
    mutationFn: () => previewResolve(incId!),
    onSuccess: (result) => setPendingAction(result.action),
  });

  // Step 2: human confirmed — execute and mark resolved
  const { mutate: confirm, isPending: confirming, isSuccess: confirmed, data: confirmData, error: confirmError } = useMutation({
    mutationFn: () => confirmResolve(incId!, pendingAction!),
    onSuccess: () => {
      setPendingAction(null);
      queryClient.invalidateQueries({ queryKey: ["incident", incId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  if (isLoading || !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  const logs = data.latest_logs ?? [];
  const distinctLogs = buildDistinctLogs(logs);

  return (
    <>
      {/* Human approval dialog */}
      <Dialog open={!!pendingAction} onClose={() => !confirming && setPendingAction(null)}>
        <DialogTitle>Confirm Resolution</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The AI recommends calling:
          </DialogContentText>
          <Typography
            variant="body1"
            sx={{ mt: 1, mb: 1, fontFamily: "monospace", fontWeight: 700, fontSize: "1rem" }}
          >
            POST {pendingAction}
          </Typography>
          <DialogContentText>
            This will execute the remediation action on the orders-service and mark the incident as resolved.
            Do you want to proceed?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingAction(null)} disabled={confirming}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="success"
            onClick={() => confirm()}
            disabled={confirming}
            startIcon={confirming ? <CircularProgress size={16} /> : <CheckCircleOutlineIcon />}
          >
            {confirming ? "Executing…" : "Confirm & Execute"}
          </Button>
        </DialogActions>
      </Dialog>

    <Stack spacing={2}>
      {/* Header */}
      <Paper sx={{ p: 3 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="h5">{data.inc_id}</Typography>
          <SeverityChip severity={data.severity} />
          <StatusChip status={data.status} />
          <Box sx={{ flexGrow: 1 }} />
          {data.status !== "resolved" && (
            previewing ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={18} />
                <Typography variant="caption" color="text.secondary">AI is choosing action…</Typography>
              </Stack>
            ) : (
              <Button
                variant="outlined"
                color="success"
                size="small"
                startIcon={<CheckCircleOutlineIcon />}
                onClick={() => preview()}
              >
                Resolve
              </Button>
            )
          )}
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
        {confirmed && confirmData && (
          <Alert severity="success" sx={{ mt: 1.5 }}>
            Resolved via <strong>{confirmData.action}</strong>
          </Alert>
        )}
        {(previewError || confirmError) && (
          <Alert severity="error" sx={{ mt: 1.5 }}>
            {((previewError || confirmError) as Error).message}
          </Alert>
        )}
      </Paper>

      {/* AI Summary */}
      {data.ai_summary && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>
            AI Summary
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
            {data.ai_summary}
          </Typography>
        </Paper>
      )}

      {/* Log Details */}
      {logs.length > 0 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
            Log Details
          </Typography>

          {/* Stats row */}
          <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Total occurrences
              </Typography>
              <Typography variant="h6">{data.occurrences}</Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="caption" color="text.secondary">
                Distinct error messages
              </Typography>
              <Typography variant="h6">{distinctLogs.length}</Typography>
            </Box>
          </Stack>

          {/* Deduplicated log list */}
          <Stack spacing={0.5}>
            {distinctLogs.map((log) => (
              <Box
                key={log.message}
                sx={{
                  borderLeft: "3px solid",
                  borderColor: "error.main",
                  bgcolor: "action.hover",
                  px: 1.5,
                  py: 0.75,
                  borderRadius: "0 4px 4px 0",
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Typography variant="body2" sx={{ flex: 1, mr: 1 }}>
                    {log.message}
                  </Typography>
                  {log.count > 1 && (
                    <Chip label={`×${log.count}`} size="small" color="error" variant="outlined" sx={{ fontSize: "0.7rem", height: 20 }} />
                  )}
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                  [{log.service}] · {log.event}
                </Typography>
              </Box>
            ))}
          </Stack>
        </Paper>
      )}

      {/* Timeline */}
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
    </>
  );
}
