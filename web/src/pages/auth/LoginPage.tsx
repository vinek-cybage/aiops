import { useState } from "react";
import { useLocation, useNavigate, Link as RouterLink } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import { login } from "../../api/endpoints/auth";
import { useAuthStore } from "../../auth/authStore";
import { brandGradient } from "../../theme/theme";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { access_token, user } = await login(email, password);
      setSession(access_token, user);
      const from = (location.state as { from?: string })?.from || "/app/dashboard";
      navigate(from, { replace: true });
    } catch (err) {
      setError("Invalid email or password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
      <Paper elevation={3} sx={{ p: 4, width: 380 }}>
        <Typography variant="h5" sx={{ mb: 1, fontWeight: 700, background: brandGradient, backgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          AIOps
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Sign in to your organization
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <Button type="submit" variant="contained" disabled={submitting}>
            {submitting ? "Signing in..." : "Sign in"}
          </Button>
        </Box>
        <Typography variant="body2" sx={{ mt: 2 }}>
          Don't have an organization yet? <Link component={RouterLink} to="/register">Register</Link>
        </Typography>
      </Paper>
    </Box>
  );
}
