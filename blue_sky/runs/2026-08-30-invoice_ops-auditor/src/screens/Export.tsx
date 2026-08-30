import {
  AUDITOR,
  attemptById,
  attemptsOnInvoice,
  buildSettleProcedure,
  invoiceById,
  tenantById,
} from "../seed";
import { money, packetId, when } from "../format";
import type { PaymentAttempt } from "../types";

export function ExportPacket({
  attemptId,
  cutAt,
  onTrail,
  onDesk,
}: {
  attemptId: string;
  cutAt: string;
  onTrail: () => void;
  onDesk: () => void;
}) {
  const attempt = attemptById[attemptId];
  const invoice = invoiceById[attempt.invoiceId];
  const tenant = tenantById[attempt.tenantId];
  const sibs = attemptsOnInvoice(invoice.id);
  const procedure = buildSettleProcedure(invoice, sibs);
  const id = packetId(attempt.id, cutAt);

  const packet = {
    packetId: id,
    cutAt,
    auditor: AUDITOR,
    chain: [attempt.id, invoice.invoiceNumber, tenant.id],
    attempt,
    invoice,
    attemptsOnInvoice: sibs,
    tenant,
    procedure,
  };

  function download() {
    const blob = new Blob([JSON.stringify(packet, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <button className="back" onClick={onTrail}>
        ← Trail
      </button>
      <div className="page-kicker" style={{ marginTop: 10 }}>
        Audit export
      </div>
      <h1 className="page-title" style={{ fontSize: 34, marginBottom: 20 }}>
        Folio cut for the file
      </h1>

      <article className="packet">
        <header className="packet-head">
          <div>
            <div className="page-kicker">Carbon Desk · Meridian Group</div>
            <h1>Audit folio</h1>
          </div>
          <div className="custody">
            {id}
            <br />
            Cut by {AUDITOR.name}, {AUDITOR.role}
            <br />
            {when(cutAt)}
            <br />
            Read-only copy of the trail
          </div>
        </header>

        <section className="exhibit">
          <h2>Chain</h2>
          <pre>
            {attempt.id} → {invoice.invoiceNumber} → {tenant.id}
            {"\n"}Payment attempt traces to invoice on tenant books.
          </pre>
        </section>

        <section className="exhibit">
          <h2>Exhibit A — Payment attempt</h2>
          <pre>{exhibitAttempt(attempt)}</pre>
        </section>

        <section className="exhibit">
          <h2>Exhibit B — Invoice</h2>
          <pre>
            {invoice.invoiceNumber}
            {"\n"}Supplier: {invoice.supplier}
            {"\n"}Amount: {money(invoice.amount, invoice.currency)}
            {"\n"}Status: {invoice.status}
            {"\n"}Approved: {invoice.approvedBy ?? "—"}
            {invoice.approvedOn ? ` · ${when(invoice.approvedOn)}` : ""}
            {"\n"}Memo: {invoice.memo}
            {"\n\n"}Settle Approved Invoice
            {procedure
              .map(
                (s) =>
                  `\n  ${s.n}. ${s.label}${s.at ? ` (${when(s.at)})` : ""} [${s.state}]`,
              )
              .join("")}
            {"\n\n"}Attempts on this invoice
            {sibs
              .map(
                (s) =>
                  `\n  ${s.id}  ${s.status.padEnd(10)}  ${money(s.amount)}  ${s.method}  ${when(s.at)}`,
              )
              .join("")}
          </pre>
        </section>

        <section className="exhibit">
          <h2>Exhibit C — Tenant</h2>
          <pre>
            {tenant.id} · {tenant.name}
            {"\n"}
            {tenant.legalName}
            {"\n"}Jurisdiction: {tenant.jurisdiction}
            {"\n"}
            {tenant.books}
            {"\n"}AP: {tenant.apDesk}
            {"\n"}Paying account ****{tenant.bankLast4}
            {"\n"}
            {tenant.notes}
          </pre>
        </section>

        <div className="packet-actions">
          <button className="cut" onClick={download}>
            Download JSON
          </button>
          <button className="ghost" onClick={() => window.print()}>
            Print folio
          </button>
          <button className="ghost" onClick={onDesk}>
            Back to the desk
          </button>
        </div>
      </article>
    </div>
  );
}

function exhibitAttempt(a: PaymentAttempt): string {
  const lines = [
    a.id,
    `Status: ${a.status}`,
    `Amount: ${money(a.amount)} ${a.method}`,
    `When: ${when(a.at)}`,
    `Processor: ${a.processor} · ${a.processorRef}`,
    `Batch: ${a.batchId}`,
    `Initiated by: ${a.initiatedBy}`,
  ];
  if (a.declineCode) {
    lines.push(`Decline: ${a.declineCode} — ${a.declineDetail}`);
    lines.push(`Retryable: ${a.retryable ? "yes" : "no"}`);
  }
  lines.push(a.note);
  return lines.join("\n");
}
