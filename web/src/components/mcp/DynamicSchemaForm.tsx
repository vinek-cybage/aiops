import TextField from "@mui/material/TextField";
import Stack from "@mui/material/Stack";
import type { CredentialField } from "../../api/endpoints/mcp";

interface Props {
  schema: CredentialField[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}

// Renders a form from a catalog entry's credential_schema/config_schema — the
// mechanism that lets new MCP listings get a working "configure" form without
// any frontend code change.
export function DynamicSchemaForm({ schema, values, onChange }: Props) {
  if (schema.length === 0) return null;
  return (
    <Stack spacing={2}>
      {schema.map((field) => (
        <TextField
          key={field.key}
          label={field.label}
          type={field.type === "secret" ? "password" : field.type === "number" ? "number" : "text"}
          required={field.required}
          helperText={field.help_text}
          value={values[field.key] ?? ""}
          onChange={(e) => onChange({ ...values, [field.key]: e.target.value })}
          fullWidth
        />
      ))}
    </Stack>
  );
}
