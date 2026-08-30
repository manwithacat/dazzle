export function money(cents: number): string {
  const sign = cents < 0 ? "−" : "";
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}$${dollars.toLocaleString("en-US")}.${frac}`;
}

export function moneyPlain(cents: number): string {
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${dollars}.${frac}`;
}

export function parseMoney(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, "");
  if (!cleaned || !/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const [d, f = ""] = cleaned.split(".");
  return Number(d) * 100 + Number(f.padEnd(2, "0").slice(0, 2));
}

export function isoNow(): string {
  return "2026-08-30T14:22:00";
}

export function formatWhen(iso: string): string {
  const d = new Date(iso);
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const day = d.getDate();
  const mon = months[d.getMonth()];
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const today = iso.startsWith("2026-08-30");
  if (today) return `today ${hh}:${mm}`;
  return `${day} ${mon} ${hh}:${mm}`;
}

export function formatDue(isoDate: string): string {
  if (isoDate === "2026-08-30") return "due this sitting";
  if (isoDate < "2026-08-30") {
    const d = new Date(isoDate + "T00:00:00");
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    return `overdue · ${d.getDate()} ${months[d.getMonth()]}`;
  }
  const d = new Date(isoDate + "T00:00:00");
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return `due ${d.getDate()} ${months[d.getMonth()]}`;
}

export const RAIL_LABEL: Record<"ach" | "wire" | "check", string> = {
  ach: "ACH",
  wire: "Wire",
  check: "Check",
};

export const RETURN_REASON: Record<"ach" | "wire" | "check", string> = {
  ach: "ACH returned — unable to locate account",
  wire: "Wire rejected — beneficiary name mismatch",
  check: "Check stopped — payee protested",
};
