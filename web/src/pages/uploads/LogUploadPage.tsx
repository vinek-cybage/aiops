import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { uploadLogFile } from "../../api/endpoints/incidents";

export function LogUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  async function handleUpload() {
    if (!file) return;
    setError(null);
    setSubmitting(true);
    try {
      const incident = await uploadLogFile(file);
      navigate(`/app/incidents/${incident.inc_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Paper sx={{ p: 4, maxWidth: 480 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>Analyze a log file</Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Upload a .log, .txt, or .out file and the AI pipeline will analyze it for incidents.
      </Typography>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Box
        sx={{
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: 1,
          p: 3,
          textAlign: "center",
          cursor: "pointer",
          mb: 2,
        }}
        onClick={() => inputRef.current?.click()}
      >
        <UploadFileIcon sx={{ fontSize: 32, color: "text.secondary" }} />
        <Typography>{file ? file.name : "Click to choose a file"}</Typography>
        <input
          ref={inputRef}
          type="file"
          accept=".log,.txt,.out"
          hidden
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </Box>
      <Button variant="contained" disabled={!file || submitting} onClick={handleUpload} fullWidth>
        {submitting ? <CircularProgress size={20} /> : "Analyze"}
      </Button>
    </Paper>
  );
}
