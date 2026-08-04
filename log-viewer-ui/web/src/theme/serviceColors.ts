// Categorical colors for "service" identity — the first three slots of the
// dataviz skill's validated palette (they pass every CVD/contrast check
// all-pairs, in both modes; see references/palette.md). Fixed assignment
// order, never reassigned/cycled as services come and go.
const SLOTS: { light: string; dark: string }[] = [
  { light: "#2a78d6", dark: "#3987e5" }, // blue
  { light: "#eb6834", dark: "#d95926" }, // orange
  { light: "#1baf7a", dark: "#199e70" }, // aqua
];

const KNOWN_ORDER = ["orders-service", "payments-service", "inventory-service"];

export function serviceColor(service: string, mode: "light" | "dark"): string {
  let index = KNOWN_ORDER.indexOf(service);
  if (index === -1) index = KNOWN_ORDER.length; // unknown service -> falls past the validated slots
  const slot = SLOTS[index % SLOTS.length];
  return mode === "dark" ? slot.dark : slot.light;
}

export function knownServices(): string[] {
  return KNOWN_ORDER;
}
