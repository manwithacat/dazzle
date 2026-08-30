export type InvoiceStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "partially_paid"
  | "rejected"
  | "disputed"
  | "paid";

export type PoMatch = "matched" | "partial" | "unmatched" | "not_applicable";

export type LineItem = {
  id: string;
  description: string;
  unit_amount: number;
  po_match: PoMatch;
  po_number: string | null;
  note: string | null;
};

export type Decision = {
  by: string;
  at: string;
  action: "approved" | "rejected";
  reason: string;
};

export type Invoice = {
  id: string;
  invoice_number: string;
  supplier: string;
  amount: number;
  status: InvoiceStatus;
  received_on: string;
  submitted_by: string | null;
  submitted_at: string | null;
  memo: string;
  lines: LineItem[];
  decision: Decision | null;
};

export type Person = {
  name: string;
  role: string;
  desk: string;
};
