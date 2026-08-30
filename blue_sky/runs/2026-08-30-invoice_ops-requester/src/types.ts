export type InvoiceStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "partially_paid"
  | "rejected"
  | "disputed"
  | "paid";

export type PoMatch = "matched" | "partial" | "unmatched" | "not_applicable";

export type Person = {
  id: "mara";
  name: string;
  role: "Requester";
  title: string;
  press: string;
};

export type Supplier = {
  id: string;
  name: string;
  city: string;
  typical: string;
};

export type PurchaseOrder = {
  id: string;
  number: string;
  supplierId: string;
  description: string;
  remainingQty: number;
  unitAmountCents: number;
  remainingCents: number;
  kind: "unit" | "budget";
};

export type LineItem = {
  id: string;
  description: string;
  quantity: number;
  unitAmountCents: number;
  poId: string | null;
  poMatch: PoMatch;
  received: boolean;
};

export type Invoice = {
  id: string;
  invoiceNumber: string;
  supplierId: string;
  amountCents: number;
  status: InvoiceStatus;
  issuedOn: string;
  lines: LineItem[];
  note: string;
  rejectedReason: string | null;
  disputeNote: string | null;
  settledAt: string | null;
  settledBy: string | null;
  settlementNote: string | null;
  paidCents: number;
  createdAt: string;
};

export type Toast = {
  id: string;
  text: string;
};
