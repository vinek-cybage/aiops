import { useState } from "react";
import { useNavigate, Link as RouterLink } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import { registerOrg } from "../../api/endpoints/auth";
import { useAuthStore } from "../../auth/authStore";
import { brandGradient } from "../../theme/theme";

export function RegisterOrgPage() {
  const [step, setStep] = useState(0);
  const [orgName, setOrgName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { access_token, user } = await registerOrg(orgName, name, email, password);
      setSession(access_token, user);
      navigate("/app/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
      <Paper elevation={3} sx={{ p: 4, width: 420 }}>
        <Typography variant="h5" sx={{ mb: 1, fontWeight: 700, background: brandGradient, backgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          Create your organization
        </Typography>
        <Stepper activeStep={step} sx={{ my: 3 }}>
          <Step><StepLabel>Organization</StepLabel></Step>
          <Step><StepLabel>Your account</StepLabel></Step>
        </Stepper>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {step === 0 && (
            <>
              <TextField label="Organization name" value={orgName} onChange={(e) => setOrgName(e.target.value)} required autoFocus />
              <Button variant="contained" disabled={!orgName.trim()} onClick={() => setStep(1)}>
                Next
              </Button>
            </>
          )}
          {step === 1 && (
            <>
              <TextField label="Your name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
              <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                helperText="At least 8 characters"
                required
              />
              <Box sx={{ display: "flex", gap: 1 }}>
                <Button onClick={() => setStep(0)}>Back</Button>
                <Button type="submit" variant="contained" disabled={submitting} sx={{ flexGrow: 1 }}>
                  {submitting ? "Creating..." : "Create organization"}
                </Button>
              </Box>
            </>
          )}
        </Box>
        <Typography variant="body2" sx={{ mt: 2 }}>
          Already have an account? <Link component={RouterLink} to="/login">Sign in</Link>
        </Typography>
      </Paper>
    </Box>
  );
}
