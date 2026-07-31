import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import { previewInvitation, acceptInvitation, type InvitationPreview } from "../../api/endpoints/teams";
import { useAuthStore } from "../../auth/authStore";
import { brandGradient } from "../../theme/theme";

export function InviteAcceptPage() {
  const { token } = useParams<{ token: string }>();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();

  useEffect(() => {
    if (!token) return;
    previewInvitation(token)
      .then(setPreview)
      .catch((err) => setPreviewError(err instanceof Error ? err.message : "This invitation is invalid or has expired"));
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setSubmitting(true);
    try {
      const { access_token, user } = await acceptInvitation(token, name, password);
      setSession(access_token, user);
      navigate("/app/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invitation");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
      <Paper elevation={3} sx={{ p: 4, width: 400 }}>
        <Typography variant="h5" sx={{ mb: 2, fontWeight: 700, background: brandGradient, backgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          Join your team
        </Typography>

        {previewError && <Alert severity="error">{previewError}</Alert>}
        {!preview && !previewError && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
            <CircularProgress size={24} />
          </Box>
        )}

        {preview && (
          <>
            <Typography color="text.secondary" sx={{ mb: 3 }}>
              You've been invited to join <strong>{preview.org_name}</strong>
              {preview.team_name ? <> on the <strong>{preview.team_name}</strong> team</> : null} as {preview.team_role.replace("_", " ")}.
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <TextField label="Email" value={preview.email} disabled />
              <TextField label="Your name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                helperText="At least 8 characters"
                required
              />
              <Button type="submit" variant="contained" disabled={submitting}>
                {submitting ? "Joining..." : "Accept & join"}
              </Button>
            </Box>
          </>
        )}
      </Paper>
    </Box>
  );
}
