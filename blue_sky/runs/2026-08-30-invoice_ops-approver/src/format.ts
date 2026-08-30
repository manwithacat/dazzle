import type { Invoice, InvoiceStatus, LineItem, PoMatch } from "./types";

export const TODAY = "30 August 2026";
export const TODAY_ISO = "2026-08-30";
export const NOW_STAMP = "30 Aug 2026 · 16:12";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function usd(n: number): string {
  return money.format(n);
}

export function statusLabel(status: InvoiceStatus): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "submitted":
      return "Submitted";
    case "approved":
      return "Approved";
    case "partially_paid":
      return "Partially paid";
    case "rejected":
      return "Rejected";
    case "disputed":
      return "Disputed";
    case "paid":
      return "Paid";
  }
}

export function statusBand(status: InvoiceStatus): string {
  switch (status) {
    case "submitted":
      return "Submitted · awaiting stamp";
    case "approved":
      return "Approved · released for settlement";
    case "rejected":
      return "Rejected · returned to sender";
    case "draft":
      return "Draft · still with the submitter";
    case "partially_paid":
      return "Partially paid · settlement underway";
    case "disputed":
      return "Disputed · held off the desk";
    case "paid":
      return "Paid · left the desk";
  }
}

export function matchLabel(match: PoMatch): string {
  switch (match) {
    case "matched":
      return "Matched";
    case "partial":
      return "Partial";
    case "unmatched":
      return "Unmatched";
    case "not_applicable":
      return "No PO";
  }
}

export function matchHint(match: PoMatch): string {
  switch (match) {
    case "matched":
      return "Agrees with the purchase order";
    case "partial":
      return "Agrees in part — amount or quantity differs";
    case "unmatched":
      return "No purchase order on file for this line";
    case "not_applicable":
      return "This vendor is not purchased against a PO";
  }
}

export function lineTally(lines: LineItem[]): {
  matched: number;
  partial: number;
  unmatched: number;
  none: number;
} {
  return lines.reduce(
    (acc, line) => {
      if (line.po_match === "matched") acc.matched += 1;
      if (line.po_match === "partial") acc.partial += 1;
      if (line.po_match === "unmatched") acc.unmatched += 1;
      if (line.po_match === "not_applicable") acc.none += 1;
      return acc;
    },
    { matched: 0, partial: 0, unmatched: 0, none: 0 },
  );
}

export function riskOf(invoice: Invoice): "clean" | "watch" | "halt" {
  const t = lineTally(invoice.lines);
  if (t.unmatched > 0) return "halt";
  if (t.partial > 0) return "watch";
  return "clean";
}

export function riskLine(invoice: Invoice): string {
  const t = lineTally(invoice.lines);
  const n = invoice.lines.length;
  const parts: string[] = [`${n} line${n === 1 ? "" : "s"}`];
  if (t.unmatched) parts.push(`${t.unmatched} unmatched`);
  if (t.partial) parts.push(`${t.partial} partial`);
  if (t.none && !t.unmatched && !t.partial) parts.push("no PO required");
  if (t.matched === n) parts.push("all matched");
  return parts.join(" · ");
}

export function awaiting(invoices: Invoice[]): Invoice[] {
  return invoices
    .filter((i) => i.status === "submitted")
    .sort((a, b) => b.amount - a.amount);
}

export function stampedToday(invoices: Invoice[]): Invoice[] {
  return invoices
    .filter((i) => i.decision !== null && i.decision.at.includes("30 Aug 2026"))
    .sort((a, b) => (a.decision!.at < b.decision!.at ? 1 : -1));
}

export function sumAmount(invoices: Invoice[]): number {
  return invoices.reduce((s, i) => s + i.amount, 0);
}
