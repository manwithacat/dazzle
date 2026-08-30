export type AttemptStatus = "pending" | "succeeded" | "failed";

export type InvoiceStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "partially_paid"
  | "rejected"
  | "disputed"
  | "paid";

export type PayMethod = "ACH" | "wire" | "card";

export type Layer = "attempt" | "invoice" | "tenant";

export type Tenant = {
  id: string;
  name: string;
  legalName: string;
  jurisdiction: string;
  books: string;
  apDesk: string;
  bankLast4: string;
  notes: string;
};

export type Invoice = {
  id: string;
  tenantId: string;
  invoiceNumber: string;
  supplier: string;
  amount: number;
  currency: string;
  status: InvoiceStatus;
  issuedOn: string;
  submittedOn?: string;
  approvedBy?: string;
  approvedOn?: string;
  dueOn: string;
  memo: string;
};

export type PaymentAttempt = {
  id: string;
  invoiceId: string;
  tenantId: string;
  status: AttemptStatus;
  amount: number;
  method: PayMethod;
  at: string;
  processor: string;
  processorRef: string;
  declineCode?: string;
  declineDetail?: string;
  retryable?: boolean;
  batchId: string;
  initiatedBy: string;
  note: string;
  today: boolean;
};

export type ProcedureStep = {
  n: number;
  label: string;
  at?: string;
  actor?: string;
  state: "done" | "now" | "wait";
  attemptId?: string;
};

export type Auditor = {
  initials: string;
  name: string;
  role: string;
};

export type View =
  | { name: "gate" }
  | { name: "desk" }
  | { name: "folio"; attemptId: string; focus: Layer }
  | { name: "export"; attemptId: string };
