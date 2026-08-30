export type InvoiceStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "partially_paid"
  | "rejected"
  | "disputed"
  | "paid";

export type PaymentStatus = "pending" | "succeeded" | "failed";

export type Rail = "ach" | "wire" | "check";

export type Tray = "ready" | "disputes" | "cleared";

export type Credit = {
  id: string;
  amount: number;
  note: string;
  at: string;
};

export type Dispute = {
  openedOn: string;
  openedBy: string;
  claim: string;
  contendedAmount: number;
};

export type Invoice = {
  id: string;
  invoiceNumber: string;
  supplier: string;
  forWhat: string;
  detail: string;
  amount: number;
  dueDate: string;
  terms: string;
  status: InvoiceStatus;
  bankOnFile: string;
  dispute?: Dispute;
  credits: Credit[];
  closedAt?: string;
  resolutionNote?: string;
};

export type PaymentAttempt = {
  id: string;
  invoiceId: string;
  amount: number;
  rail: Rail;
  reference: string;
  status: PaymentStatus;
  at: string;
  returnReason?: string;
};

export type StampKind =
  "paid" | "partial" | "returned" | "refused" | "credited" | "unfounded";

export type Posting = {
  attemptId: string;
  invoiceId: string;
  outcome: "succeeded" | "failed";
  returnReason?: string;
};
