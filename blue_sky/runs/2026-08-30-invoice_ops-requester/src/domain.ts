import { lineTotal, uid } from "./money";
import type {
  Invoice,
  InvoiceStatus,
  LineItem,
  PoMatch,
  PurchaseOrder,
  Supplier,
} from "./types";

export function sumLines(lines: LineItem[]): number {
  return lines.reduce(
    (sum, line) => sum + lineTotal(line.quantity, line.unitAmountCents),
    0,
  );
}

export function computeMatch(line: LineItem, pos: PurchaseOrder[]): PoMatch {
  if (!line.poId) {
    return line.poMatch === "not_applicable" ? "not_applicable" : "unmatched";
  }
  const po = pos.find((p) => p.id === line.poId);
  if (!po) return "unmatched";
  const total = lineTotal(line.quantity, line.unitAmountCents);
  if (line.quantity <= 0 || total <= 0) return "unmatched";
  const qtyFits = line.quantity <= po.remainingQty;
  const totalFits = total <= po.remainingCents;
  const unitMatches = line.unitAmountCents === po.unitAmountCents;
  if (!qtyFits || !totalFits) return "partial";
  if (po.kind === "budget") return "matched";
  if (unitMatches) return "matched";
  return "partial";
}

export function withMatches(
  lines: LineItem[],
  pos: PurchaseOrder[],
): LineItem[] {
  return lines.map((line) => ({ ...line, poMatch: computeMatch(line, pos) }));
}

export function refreshInvoice(
  invoice: Invoice,
  pos: PurchaseOrder[],
): Invoice {
  const lines = withMatches(invoice.lines, pos);
  return { ...invoice, lines, amountCents: sumLines(lines) };
}

export function posForSupplier(
  pos: PurchaseOrder[],
  supplierId: string,
): PurchaseOrder[] {
  return pos.filter((p) => p.supplierId === supplierId);
}

export function supplierOf(
  suppliers: Supplier[],
  id: string,
): Supplier | undefined {
  return suppliers.find((s) => s.id === id);
}

export type DeskPile = "needs" | "moving" | "closed";

export function pileOf(invoice: Invoice): DeskPile {
  if (invoice.status === "paid") return "closed";
  if (invoice.status === "draft" || invoice.status === "rejected")
    return "needs";
  if (invoice.status === "disputed") return "needs";
  if (invoice.status === "approved" && !invoice.settledAt) return "needs";
  return "moving";
}

export function canEditLines(status: InvoiceStatus): boolean {
  return status === "draft" || status === "rejected" || status === "disputed";
}

export type Blocker = { id: string; text: string };

export function blockers(invoice: Invoice, suppliers: Supplier[]): Blocker[] {
  const out: Blocker[] = [];
  const namedNew =
    invoice.supplierId.startsWith("new:") &&
    invoice.supplierId.slice(4).trim().length > 0;
  if (
    !invoice.supplierId ||
    (!namedNew && !supplierOf(suppliers, invoice.supplierId))
  ) {
    out.push({ id: "supplier", text: "Name the supplier who billed you." });
  }
  if (!invoice.invoiceNumber.trim()) {
    out.push({ id: "number", text: "Enter their invoice number." });
  }
  if (invoice.lines.length === 0) {
    out.push({ id: "lines", text: "Add at least one line." });
  }
  if (invoice.lines.some((l) => !l.description.trim())) {
    out.push({ id: "desc", text: "Every line needs a description." });
  }
  if (
    invoice.lines.some((l) => lineTotal(l.quantity, l.unitAmountCents) <= 0)
  ) {
    out.push({ id: "amt", text: "Every line needs a quantity and amount." });
  }
  if (invoice.lines.some((l) => l.poMatch === "unmatched")) {
    out.push({
      id: "po",
      text: "Match each line to a purchase order, or mark it as having none.",
    });
  }
  return out;
}

export function verbFor(invoice: Invoice): string {
  switch (invoice.status) {
    case "draft":
      return "Finish this slip";
    case "rejected":
      return "The books sent it back";
    case "approved":
      return invoice.settledAt ? "Released for payment" : "Attest receipt";
    case "submitted":
      return "Waiting on the books";
    case "disputed":
      return "Answer the dispute";
    case "partially_paid":
      return "Treasury is paying it down";
    case "paid":
      return "Closed";
  }
}

export function stampLabel(status: InvoiceStatus): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "submitted":
      return "Submitted";
    case "approved":
      return "Approved";
    case "partially_paid":
      return "Partial pay";
    case "rejected":
      return "Rejected";
    case "disputed":
      return "Disputed";
    case "paid":
      return "Paid";
  }
}

export function matchLabel(match: PoMatch): string {
  switch (match) {
    case "matched":
      return "Matched";
    case "partial":
      return "Partial";
    case "unmatched":
      return "No PO";
    case "not_applicable":
      return "No PO needed";
  }
}

export function splitLine(
  invoice: Invoice,
  lineId: string,
  pos: PurchaseOrder[],
): Invoice {
  const line = invoice.lines.find((l) => l.id === lineId);
  if (!line) return invoice;
  const current = pos.find((p) => p.id === line.poId);
  if (!current) return invoice;
  const others = pos.filter(
    (p) =>
      p.supplierId === invoice.supplierId &&
      p.id !== current.id &&
      p.unitAmountCents === line.unitAmountCents,
  );
  const buckets = [current, ...others];
  let remaining = line.quantity;
  const created: LineItem[] = [];
  for (const po of buckets) {
    if (remaining <= 0) break;
    const take = Math.min(remaining, po.remainingQty);
    if (take <= 0) continue;
    const description = line.description.replace(
      /—\s*\d+\s*reams/i,
      `— ${take} reams`,
    );
    created.push({
      ...line,
      id: uid("ln"),
      quantity: take,
      poId: po.id,
      description,
    });
    remaining -= take;
  }
  if (remaining > 0) {
    created.push({
      ...line,
      id: uid("ln"),
      quantity: remaining,
      poId: null,
      poMatch: "unmatched",
      description: line.description.replace(
        /—\s*\d+\s*reams/i,
        `— ${remaining} reams`,
      ),
    });
  }
  if (created.length === 0) return invoice;
  return {
    ...invoice,
    lines: invoice.lines.flatMap((l) => (l.id === lineId ? created : [l])),
  };
}

export function matchHint(match: PoMatch): string {
  switch (match) {
    case "matched":
      return "This line sits cleanly on an open purchase order.";
    case "partial":
      return "A purchase order is linked, but quantity or rate does not fully agree.";
    case "unmatched":
      return "Unmatched lines cannot go to the books.";
    case "not_applicable":
      return "You attested this line has no purchase order — rush fees, licenses, one-offs.";
  }
}
