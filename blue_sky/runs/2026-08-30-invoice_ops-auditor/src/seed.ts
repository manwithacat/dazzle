import type {
  Invoice,
  PaymentAttempt,
  ProcedureStep,
  Tenant,
  Auditor,
} from "./types";

export const TODAY = "2026-08-30";
export const TODAY_LABEL = "30 August 2026";

export const AUDITOR: Auditor = {
  initials: "A.O.",
  name: "A. Okada",
  role: "Auditor",
};

export const tenants: Tenant[] = [
  {
    id: "T-ORCH",
    name: "Orchard & Co.",
    legalName: "Orchard & Company Operating LLC",
    jurisdiction: "Delaware",
    books: "USD · fiscal year closes 31 January",
    apDesk: "Mara Chen, AP lead",
    bankLast4: "4412",
    notes:
      "Seasonal cash around harvest. NSF on ACH is common in late August; treasury retries the same day before disputing.",
  },
  {
    id: "T-HALC",
    name: "Halcyon Labs",
    legalName: "Halcyon Laboratories Inc.",
    jurisdiction: "Massachusetts",
    books: "USD · fiscal year closes 30 June",
    apDesk: "R. Voss, controller",
    bankLast4: "9021",
    notes:
      "Card for anything under $5,000. Non-retryable declines go to dispute the same day — they do not sit in approved.",
  },
  {
    id: "T-KITE",
    name: "Kite Harbor Logistics",
    legalName: "Kite Harbor Logistics Ltd.",
    jurisdiction: "Singapore, books via Delaware holdco",
    books: "USD · fiscal year closes 31 December",
    apDesk: "Priya Nair, treasury",
    bankLast4: "1178",
    notes:
      "Fuel invoices split on purpose: wire the contracted floor, ACH the remainder once the terminal ticket posts.",
  },
];

export const invoices: Invoice[] = [
  {
    id: "INV-2044",
    tenantId: "T-ORCH",
    invoiceNumber: "INV-2044",
    supplier: "Barrow Cold Storage",
    amount: 12400,
    currency: "USD",
    status: "approved",
    issuedOn: "2026-08-12",
    submittedOn: "2026-08-28T11:10:00",
    approvedBy: "Mara Chen",
    approvedOn: "2026-08-29T16:40:00",
    dueOn: "2026-09-11",
    memo: "August warehousing, Concord lot. Net 14. Settlement opened the evening of approval.",
  },
  {
    id: "INV-2051",
    tenantId: "T-ORCH",
    invoiceNumber: "INV-2051",
    supplier: "Linnet Print",
    amount: 1120,
    currency: "USD",
    status: "paid",
    issuedOn: "2026-08-18",
    submittedOn: "2026-08-20T09:02:00",
    approvedBy: "Mara Chen",
    approvedOn: "2026-08-29T10:15:00",
    dueOn: "2026-09-01",
    memo: "Private-label jam collars, run of 8,000. Card, one try.",
  },
  {
    id: "INV-2030",
    tenantId: "T-ORCH",
    invoiceNumber: "INV-2030",
    supplier: "Linnet Print",
    amount: 440,
    currency: "USD",
    status: "draft",
    issuedOn: "2026-08-27",
    dueOn: "2026-09-20",
    memo: "Color proof for autumn labels. Not yet submitted.",
  },
  {
    id: "INV-2021",
    tenantId: "T-ORCH",
    invoiceNumber: "INV-2021",
    supplier: "Barrow Cold Storage",
    amount: 2010,
    currency: "USD",
    status: "submitted",
    issuedOn: "2026-08-22",
    submittedOn: "2026-08-29T15:44:00",
    dueOn: "2026-09-12",
    memo: "Addendum: extra pallet weeks. Waiting on Mara.",
  },
  {
    id: "INV-1980",
    tenantId: "T-ORCH",
    invoiceNumber: "INV-1980",
    supplier: "Westwell Flowers",
    amount: 600,
    currency: "USD",
    status: "rejected",
    issuedOn: "2026-08-04",
    submittedOn: "2026-08-06T08:30:00",
    dueOn: "2026-08-20",
    memo: "Wrong operating company. Rejected — belongs on the holdco entertaining book, not Orchard.",
  },
  {
    id: "INV-1988",
    tenantId: "T-HALC",
    invoiceNumber: "INV-1988",
    supplier: "Pellucid Glass",
    amount: 3250,
    currency: "USD",
    status: "paid",
    issuedOn: "2026-08-08",
    submittedOn: "2026-08-10T14:12:00",
    approvedBy: "R. Voss",
    approvedOn: "2026-08-28T17:05:00",
    dueOn: "2026-09-07",
    memo: "Borosilicate flasks, lot 44. Under the $5k card rule.",
  },
  {
    id: "INV-1991",
    tenantId: "T-HALC",
    invoiceNumber: "INV-1991",
    supplier: "Nightshift Couriers",
    amount: 8900,
    currency: "USD",
    status: "disputed",
    issuedOn: "2026-07-30",
    submittedOn: "2026-08-01T09:40:00",
    approvedBy: "R. Voss",
    approvedOn: "2026-08-27T11:18:00",
    dueOn: "2026-08-29",
    memo: "July specimen runs. ACH returned account-closed. Moved to dispute rather than retry.",
  },
  {
    id: "INV-1966",
    tenantId: "T-HALC",
    invoiceNumber: "INV-1966",
    supplier: "Pellucid Glass",
    amount: 480,
    currency: "USD",
    status: "submitted",
    issuedOn: "2026-08-25",
    submittedOn: "2026-08-26T16:01:00",
    dueOn: "2026-09-24",
    memo: "Replacement stoppers. In Voss's queue.",
  },
  {
    id: "INV-2010",
    tenantId: "T-KITE",
    invoiceNumber: "INV-2010",
    supplier: "Harbor Fuel Co.",
    amount: 48000,
    currency: "USD",
    status: "partially_paid",
    issuedOn: "2026-08-15",
    submittedOn: "2026-08-16T10:00:00",
    approvedBy: "Priya Nair",
    approvedOn: "2026-08-28T13:22:00",
    dueOn: "2026-09-05",
    memo: "August bunker, Oakland. Split on purpose: $30,000 wire floor, $18,000 ACH once tickets posted.",
  },
];

export const attempts: PaymentAttempt[] = [
  {
    id: "PA-8820",
    invoiceId: "INV-2044",
    tenantId: "T-ORCH",
    status: "failed",
    amount: 12400,
    method: "ACH",
    at: "2026-08-29T17:02:00",
    processor: "Northrail Pay",
    processorRef: "NR-7C11-8820",
    declineCode: "NSF",
    declineDetail: "Insufficient funds on ****4412. Retryable.",
    retryable: true,
    batchId: "SET-0829-NIGHT",
    initiatedBy: "Settle Approved Invoice · night queue",
    note: "First try, evening of approval. Returned NSF. Left in approved for a next-day retry.",
    today: false,
  },
  {
    id: "PA-8841",
    invoiceId: "INV-2044",
    tenantId: "T-ORCH",
    status: "failed",
    amount: 12400,
    method: "ACH",
    at: "2026-08-30T14:22:00",
    processor: "Northrail Pay",
    processorRef: "NR-9F2A-8841",
    declineCode: "NSF",
    declineDetail:
      "Insufficient funds on ****4412. Second consecutive NSF. Retryable.",
    retryable: true,
    batchId: "SET-0830-AFTERNOON",
    initiatedBy: "Settle Approved Invoice · afternoon queue",
    note: "Second try. Same account, same NSF. Mara Chen queued a third attempt twenty minutes later.",
    today: true,
  },
  {
    id: "PA-8842",
    invoiceId: "INV-2044",
    tenantId: "T-ORCH",
    status: "pending",
    amount: 12400,
    method: "ACH",
    at: "2026-08-30T14:41:00",
    processor: "Northrail Pay",
    processorRef: "NR-9F2A-8842",
    batchId: "SET-0830-RETRY",
    initiatedBy: "Mara Chen · manual retry",
    note: "Third try, still in flight at Northrail. Invoice remains approved — settlement has not posted and has not been disputed.",
    today: true,
  },
  {
    id: "PA-8790",
    invoiceId: "INV-1988",
    tenantId: "T-HALC",
    status: "succeeded",
    amount: 3250,
    method: "card",
    at: "2026-08-30T09:14:00",
    processor: "Northrail Pay",
    processorRef: "NR-44AA-8790",
    batchId: "SET-0830-MORNING",
    initiatedBy: "Settle Approved Invoice · morning queue",
    note: "Single card presentment. Invoice marked paid on success.",
    today: true,
  },
  {
    id: "PA-8801",
    invoiceId: "INV-2010",
    tenantId: "T-KITE",
    status: "succeeded",
    amount: 30000,
    method: "wire",
    at: "2026-08-30T09:18:00",
    processor: "Northrail Pay",
    processorRef: "NR-WIRE-8801",
    batchId: "SET-0830-MORNING",
    initiatedBy: "Settle Approved Invoice · morning queue",
    note: "Contracted floor. Posted. Remainder is a separate ACH still sitting with the processor.",
    today: true,
  },
  {
    id: "PA-8802",
    invoiceId: "INV-2010",
    tenantId: "T-KITE",
    status: "pending",
    amount: 18000,
    method: "ACH",
    at: "2026-08-30T09:18:00",
    processor: "Northrail Pay",
    processorRef: "NR-8B01-8802",
    batchId: "SET-0830-MORNING",
    initiatedBy: "Settle Approved Invoice · morning queue",
    note: "Remainder after the wire. Invoice is partially paid until this attempt settles.",
    today: true,
  },
  {
    id: "PA-8712",
    invoiceId: "INV-1991",
    tenantId: "T-HALC",
    status: "failed",
    amount: 8900,
    method: "ACH",
    at: "2026-08-30T11:02:00",
    processor: "Northrail Pay",
    processorRef: "NR-0D77-8712",
    declineCode: "ACCOUNT_CLOSED",
    declineDetail: "Receiving account closed. Not retryable.",
    retryable: false,
    batchId: "SET-0830-MORNING",
    initiatedBy: "Settle Approved Invoice · morning queue",
    note: "One try. Account closed. Invoice left approved overnight, then R. Voss moved it to disputed at 11:40.",
    today: true,
  },
  {
    id: "PA-8850",
    invoiceId: "INV-2051",
    tenantId: "T-ORCH",
    status: "succeeded",
    amount: 1120,
    method: "card",
    at: "2026-08-30T15:03:00",
    processor: "Northrail Pay",
    processorRef: "NR-C2E0-8850",
    batchId: "SET-0830-AFTERNOON",
    initiatedBy: "Settle Approved Invoice · afternoon queue",
    note: "Clean card capture. Invoice marked paid.",
    today: true,
  },
];

export const tenantById = Object.fromEntries(
  tenants.map((t) => [t.id, t]),
) as Record<string, Tenant>;
export const invoiceById = Object.fromEntries(
  invoices.map((i) => [i.id, i]),
) as Record<string, Invoice>;
export const attemptById = Object.fromEntries(
  attempts.map((a) => [a.id, a]),
) as Record<string, PaymentAttempt>;

export function todayAttempts(): PaymentAttempt[] {
  return attempts
    .filter((a) => a.today)
    .slice()
    .sort((a, b) => a.at.localeCompare(b.at));
}

export function attemptsOnInvoice(invoiceId: string): PaymentAttempt[] {
  return attempts
    .filter((a) => a.invoiceId === invoiceId)
    .slice()
    .sort((a, b) => a.at.localeCompare(b.at));
}

export function invoicesForTenant(tenantId: string): Invoice[] {
  const rank: Record<Invoice["status"], number> = {
    disputed: 0,
    approved: 1,
    partially_paid: 2,
    submitted: 3,
    draft: 4,
    paid: 5,
    rejected: 6,
  };
  return invoices
    .filter((i) => i.tenantId === tenantId)
    .slice()
    .sort(
      (a, b) =>
        rank[a.status] - rank[b.status] ||
        a.invoiceNumber.localeCompare(b.invoiceNumber),
    );
}

export function tryOrdinal(attempt: PaymentAttempt): { n: number; of: number } {
  const list = attemptsOnInvoice(attempt.invoiceId);
  return { n: list.findIndex((a) => a.id === attempt.id) + 1, of: list.length };
}

export function buildSettleProcedure(
  invoice: Invoice,
  onInvoice: PaymentAttempt[],
): ProcedureStep[] {
  const steps: ProcedureStep[] = [];
  let n = 1;

  steps.push({
    n: n++,
    label: "Invoice drafted on the tenant books",
    at: invoice.issuedOn,
    actor: invoice.supplier,
    state: "done",
  });

  if (invoice.submittedOn || invoice.status !== "draft") {
    steps.push({
      n: n++,
      label: "Submitted for approval",
      at: invoice.submittedOn,
      actor: tenantById[invoice.tenantId]?.apDesk,
      state: "done",
    });
  } else {
    steps.push({
      n: n++,
      label: "Submit for approval",
      state: "wait",
    });
    return steps;
  }

  if (invoice.status === "rejected") {
    steps.push({
      n: n++,
      label: "Rejected — settlement does not start",
      actor: invoice.approvedBy ?? "AP",
      state: "done",
    });
    return steps;
  }

  if (invoice.approvedOn) {
    steps.push({
      n: n++,
      label: "Approved — enter Settle Approved Invoice",
      at: invoice.approvedOn,
      actor: invoice.approvedBy,
      state: "done",
    });
  } else {
    steps.push({
      n: n++,
      label: "Await approval",
      state: invoice.status === "submitted" ? "now" : "wait",
    });
    return steps;
  }

  if (onInvoice.length === 0) {
    steps.push({
      n: n++,
      label: "Queue first payment attempt",
      state: "now",
    });
    return steps;
  }

  for (const a of onInvoice) {
    const verb =
      a.status === "succeeded"
        ? "posted"
        : a.status === "failed"
          ? `returned ${a.declineCode ?? "failed"}`
          : "in flight at Northrail";
    steps.push({
      n: n++,
      label: `Payment attempt ${a.id} · ${a.method} ${verb}`,
      at: a.at,
      actor: a.initiatedBy,
      state: a.status === "pending" ? "now" : "done",
      attemptId: a.id,
    });
  }

  if (invoice.status === "paid") {
    steps.push({
      n: n++,
      label: "Invoice marked paid",
      state: "done",
    });
  } else if (invoice.status === "partially_paid") {
    steps.push({
      n: n++,
      label: "Invoice marked partially paid — remainder still open",
      state: "now",
    });
  } else if (invoice.status === "disputed") {
    steps.push({
      n: n++,
      label: "Settlement abandoned — invoice moved to disputed",
      actor: tenantById[invoice.tenantId]?.apDesk,
      state: "done",
    });
  } else {
    steps.push({
      n: n++,
      label: "Mark paid, partially paid, or dispute",
      state: "wait",
    });
  }

  return steps;
}
