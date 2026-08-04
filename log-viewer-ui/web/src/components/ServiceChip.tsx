import { Chip, useTheme } from "@mui/material";
import { serviceColor } from "../theme/serviceColors";

export function ServiceChip({ service }: { service: string }) {
  const { palette } = useTheme();
  const color = serviceColor(service, palette.mode);
  return (
    <Chip
      label={service}
      size="small"
      sx={{
        color,
        borderColor: color,
        bgcolor: `${color}1a`,
      }}
      variant="outlined"
    />
  );
}
