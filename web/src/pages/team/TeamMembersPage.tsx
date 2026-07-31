import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import IconButton from "@mui/material/IconButton";
import DeleteIcon from "@mui/icons-material/Delete";
import {
  listMembers,
  listInvitations,
  createInvitation,
  revokeInvitation,
  updateMemberRole,
  removeMember,
} from "../../api/endpoints/teams";
import { TeamTabs } from "./TeamTabs";

export function TeamMembersPage() {
  const { teamId: teamIdParam } = useParams<{ teamId: string }>();
  const teamId = Number(teamIdParam);
  const queryClient = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteLink, setInviteLink] = useState<string | null>(null);

  const { data: members } = useQuery({ queryKey: ["team-members", teamId], queryFn: () => listMembers(teamId) });
  const { data: invitations } = useQuery({ queryKey: ["team-invitations", teamId], queryFn: () => listInvitations(teamId) });

  const inviteMutation = useMutation({
    mutationFn: () => createInvitation(teamId, inviteEmail, inviteRole),
    onSuccess: (res) => {
      setInviteLink(`${window.location.origin}${res.invite_link}`);
      setInviteEmail("");
      queryClient.invalidateQueries({ queryKey: ["team-invitations", teamId] });
    },
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, teamRole }: { userId: number; teamRole: string }) => updateMemberRole(teamId, userId, teamRole),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-members", teamId] }),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: number) => removeMember(teamId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-members", teamId] }),
  });

  const revokeMutation = useMutation({
    mutationFn: (invitationId: string) => revokeInvitation(teamId, invitationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-invitations", teamId] }),
  });

  return (
    <>
      <TeamTabs />
      <Stack spacing={2}>
      <Paper sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">Members</Typography>
          <Button variant="contained" size="small" onClick={() => setInviteOpen(true)}>
            Invite member
          </Button>
        </Stack>
        <Table size="small" sx={{ mt: 1 }}>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Team role</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(members ?? []).map((m) => (
              <TableRow key={m.user_id}>
                <TableCell>{m.name}</TableCell>
                <TableCell>{m.email}</TableCell>
                <TableCell>
                  <Select
                    size="small"
                    value={m.team_role}
                    onChange={(e) => roleMutation.mutate({ userId: m.user_id, teamRole: e.target.value })}
                  >
                    <MenuItem value="member">Member</MenuItem>
                    <MenuItem value="team_admin">Team admin</MenuItem>
                  </Select>
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => removeMutation.mutate(m.user_id)} aria-label="Remove member">
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>Pending invitations</Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Email</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Expires</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(invitations ?? []).map((inv) => (
              <TableRow key={inv.id}>
                <TableCell>{inv.email}</TableCell>
                <TableCell><Chip size="small" label={inv.role} /></TableCell>
                <TableCell>{new Date(inv.expires_at).toLocaleDateString()}</TableCell>
                <TableCell align="right">
                  <Button size="small" onClick={() => revokeMutation.mutate(inv.id)}>Revoke</Button>
                </TableCell>
              </TableRow>
            ))}
            {(invitations ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>
                  <Typography color="text.secondary" sx={{ p: 1 }}>No pending invitations.</Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={inviteOpen} onClose={() => { setInviteOpen(false); setInviteLink(null); }} fullWidth maxWidth="xs">
        <DialogTitle>Invite a team member</DialogTitle>
        <DialogContent>
          {inviteLink ? (
            <>
              <Alert severity="success" sx={{ mb: 2 }}>Invitation created — share this link:</Alert>
              <TextField fullWidth value={inviteLink} InputProps={{ readOnly: true }} onFocus={(e) => e.target.select()} />
            </>
          ) : (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField label="Email" type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} autoFocus />
              <Select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} size="small">
                <MenuItem value="member">Member</MenuItem>
                <MenuItem value="team_admin">Team admin</MenuItem>
              </Select>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setInviteOpen(false); setInviteLink(null); }}>Close</Button>
          {!inviteLink && (
            <Button variant="contained" disabled={!inviteEmail || inviteMutation.isPending} onClick={() => inviteMutation.mutate()}>
              Send invite
            </Button>
          )}
        </DialogActions>
      </Dialog>
      </Stack>
    </>
  );
}
