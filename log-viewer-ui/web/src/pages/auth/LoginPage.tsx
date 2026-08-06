import { useState, type FormEvent } from "react";
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { brandGradient } from "../../theme/theme";
import { useAuth } from "../../auth/AuthProvider";

export function LoginPage() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [code, setCode] = useState("");
  const [error, setError] = useState(false);

  if (isAuthenticated) {
    const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";
    return <Navigate to={from} replace />;
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (login(code)) {
      const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";
      navigate(from, { replace: true });
    } else {
      setError(true);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: brandGradient,
        p: 2,
      }}
    >
      <Paper elevation={6} sx={{ p: 4, width: 360, borderRadius: 3 }}>
        <Stack spacing={2} alignItems="center" sx={{ mb: 1 }}>
          <Box
            sx={{
              width: 56,
              height: 56,
              borderRadius: "50%",
              background: brandGradient,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <LockOutlinedIcon sx={{ color: "#fff" }} />
          </Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            AI-Ops
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center">
            Enter the access code to continue
          </Typography>
        </Stack>

        <Stack component="form" spacing={2} sx={{ mt: 2 }} onSubmit={handleSubmit}>
          {error && <Alert severity="error">Incorrect access code</Alert>}
          <TextField
            label="Access code"
            type="password"
            autoFocus
            fullWidth
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              setError(false);
            }}
          />
          <Button type="submit" variant="contained" size="large" fullWidth disabled={!code}>
            Sign in
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}
