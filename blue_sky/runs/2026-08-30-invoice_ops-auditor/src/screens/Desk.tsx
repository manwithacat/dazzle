import { useMemo, useState } from "react";
import { clock, money } from "../format";
import { invoiceById, tenantById, todayAttempts, tryOrdinal } from "../seed";
import type { AttemptStatus, Layer, PaymentAttempt } from "../types";

const filters: { id: "all" | AttemptStatus; label: string }[] = [
  { id: "all", label: "Today" },
  { id: "failed", label: "Failed" },
  { id: "pending", label: "Pending" },
  { id: "succeeded", label: "Succeeded" },
];

export function Desk({
  cutIds,
  onOpen,
}: {
  cutIds: Set<string>;
  onOpen: (attemptId: string, focus: Layer) => void;
}) {
  const [filter, setFilter] = useState<"all" | AttemptStatus>("all");
  const rows = useMemo(() => {
    const all = todayAttempts();
    return filter === "all" ? all : all.filter((a) => a.status === filter);
  }, [filter]);

  const unsettled = rows.filter((a) => a.status !== "succeeded");
  const posted = rows.filter((a) => a.status === "succeeded");

  return (
    <div>
      <div className="page-kicker">Audit review desk</div>
      <h1 className="page-title">Today’s settlement ribbon</h1>
      <p className="lede">
        Your list is <strong>Payment Attempt</strong>. Each slip{" "}
        <strong>triple-opens</strong> — attempt, invoice, or tenant. The trail
        always lays down in that order, so you can walk a charge back to the
        invoice without another browser.
      </p>

      <div
        className="toolbar"
        role="tablist"
        aria-label="Filter today’s attempts"
      >
        {filters.map((f) => (
          <button
            key={f.id}
            className={filter === f.id ? "chip on" : "chip"}
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
          >
            {f.label}
            {f.id === "all" ? ` · ${todayAttempts().length}` : ""}
          </button>
        ))}
      </div>

      <div className="slips">
        {unsettled.length > 0 && filter === "all" && (
          <div className="group-label">
            Unsettled — still live on an invoice
          </div>
        )}
        {unsettled.map((a) => (
          <Slip key={a.id} attempt={a} cut={cutIds.has(a.id)} onOpen={onOpen} />
        ))}
        {posted.length > 0 && filter === "all" && (
          <div className="group-label">Posted — invoice already moved</div>
        )}
        {posted.map((a) => (
          <Slip key={a.id} attempt={a} cut={cutIds.has(a.id)} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

function Slip({
  attempt,
  cut,
  onOpen,
}: {
  attempt: PaymentAttempt;
  cut: boolean;
  onOpen: (attemptId: string, focus: Layer) => void;
}) {
  const invoice = invoiceById[attempt.invoiceId];
  const tenant = tenantById[attempt.tenantId];
  const ordinal = tryOrdinal(attempt);

  return (
    <article className={cut ? "slip cut" : "slip"}>
      <div>
        <div className="slip-top">
          <span className="slip-time">{clock(attempt.at)}</span>
          {cut && <span className="cut-flag">Cut for the file</span>}
        </div>
        <p className="slip-copy">
          {money(attempt.amount, invoice.currency)} · {attempt.method}
          {attempt.declineCode ? ` · ${attempt.declineCode}` : ""}{" "}
          <em>
            · {invoice.supplier} on {tenant.name}
          </em>
        </p>
        <p className="slip-meta">
          Try {ordinal.n} of {ordinal.of} on {invoice.invoiceNumber}
          {invoice.status === "approved" && attempt.status !== "succeeded"
            ? " · invoice still approved"
            : ` · invoice ${invoice.status.replace("_", " ")}`}
        </p>
      </div>
      <span className={`stamp ${attempt.status}`}>{attempt.status}</span>
      <div className="triple">
        <button
          className="id-open"
          onClick={() => onOpen(attempt.id, "attempt")}
          title="Open payment attempt first"
        >
          <small>attempt</small>
          <b>{attempt.id}</b>
        </button>
        <button
          className="id-open"
          onClick={() => onOpen(attempt.id, "invoice")}
          title="Open the invoice this attempt belongs to"
        >
          <small>invoice</small>
          <b>{invoice.invoiceNumber}</b>
        </button>
        <button
          className="id-open"
          onClick={() => onOpen(attempt.id, "tenant")}
          title="Open the tenant on the books"
        >
          <small>tenant</small>
          <b>{tenant.id}</b>
        </button>
      </div>
    </article>
  );
}
