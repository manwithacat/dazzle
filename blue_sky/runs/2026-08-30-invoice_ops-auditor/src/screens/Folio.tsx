import { useEffect } from "react";
import { day, money, when } from "../format";
import {
  attemptById,
  attemptsOnInvoice,
  buildSettleProcedure,
  invoiceById,
  invoicesForTenant,
  tenantById,
  tryOrdinal,
} from "../seed";
import type { InvoiceStatus, Layer, PaymentAttempt } from "../types";

export function Folio({
  attemptId,
  focus,
  cut,
  onFocus,
  onSwitchAttempt,
  onDesk,
  onCut,
}: {
  attemptId: string;
  focus: Layer;
  cut: boolean;
  onFocus: (layer: Layer) => void;
  onSwitchAttempt: (id: string, focus: Layer) => void;
  onDesk: () => void;
  onCut: () => void;
}) {
  const attempt = attemptById[attemptId];
  const invoice = invoiceById[attempt.invoiceId];
  const tenant = tenantById[attempt.tenantId];
  const sibs = attemptsOnInvoice(invoice.id);
  const procedure = buildSettleProcedure(invoice, sibs);
  const ordinal = tryOrdinal(attempt);
  const book = invoicesForTenant(tenant.id);

  useEffect(() => {
    document.getElementById(`layer-${focus}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [focus, attemptId]);

  return (
    <div>
      <div className="folio-head">
        <div>
          <button className="back" onClick={onDesk}>
            ← Desk
          </button>
          <div className="page-kicker" style={{ marginTop: 10 }}>
            Trail · attempt first, then invoice, then tenant
          </div>
          <nav className="spine" aria-label="Trace spine">
            <button
              className={focus === "attempt" ? "on" : ""}
              onClick={() => onFocus("attempt")}
            >
              {attempt.id}
            </button>
            <span>traces to</span>
            <button
              className={focus === "invoice" ? "on" : ""}
              onClick={() => onFocus("invoice")}
            >
              {invoice.invoiceNumber}
            </button>
            <span>on</span>
            <button
              className={focus === "tenant" ? "on" : ""}
              onClick={() => onFocus("tenant")}
            >
              {tenant.id}
            </button>
          </nav>
        </div>
        <button className="cut" onClick={onCut}>
          {cut ? "Open the cut folio" : "Cut folio for the file"}
        </button>
      </div>

      <div className="trail">
        <section
          id="layer-attempt"
          className={focus === "attempt" ? "sheet is-focus" : "sheet"}
        >
          <p className="sheet-index">1 · Payment attempt</p>
          <div className="sheet-head">
            <h2>
              <span>{attempt.id}</span>
              {money(attempt.amount)} {attempt.method}
            </h2>
            <span className={`stamp lg ${attempt.status}`}>
              {attempt.status}
            </span>
          </div>
          <dl className="facts three">
            <div>
              <dt>When</dt>
              <dd>{when(attempt.at)}</dd>
            </div>
            <div>
              <dt>Processor</dt>
              <dd>
                {attempt.processor}
                <br />
                <span style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
                  {attempt.processorRef}
                </span>
              </dd>
            </div>
            <div>
              <dt>Settlement batch</dt>
              <dd>{attempt.batchId}</dd>
            </div>
            <div>
              <dt>Initiated by</dt>
              <dd>{attempt.initiatedBy}</dd>
            </div>
            <div>
              <dt>Try on this invoice</dt>
              <dd>
                {ordinal.n} of {ordinal.of}
              </dd>
            </div>
            <div>
              <dt>Traces to</dt>
              <dd>
                <button className="back" onClick={() => onFocus("invoice")}>
                  {invoice.invoiceNumber} →
                </button>
              </dd>
            </div>
          </dl>
          {attempt.declineCode && (
            <dl className="facts" style={{ marginTop: -6 }}>
              <div>
                <dt>Decline</dt>
                <dd>
                  <strong>{attempt.declineCode}</strong>
                  {attempt.retryable === false
                    ? " · not retryable"
                    : " · retryable"}
                </dd>
              </div>
              <div>
                <dt>Processor detail</dt>
                <dd>{attempt.declineDetail}</dd>
              </div>
            </dl>
          )}
          <p className="note">{attempt.note}</p>
        </section>

        <section
          id="layer-invoice"
          className={
            focus === "invoice" ? "sheet invoice is-focus" : "sheet invoice"
          }
        >
          <p className="sheet-index">2 · Invoice</p>
          <div className="sheet-head">
            <h2>
              <span>{invoice.invoiceNumber}</span>
              {invoice.supplier}
            </h2>
            <span className={`slug ${invoice.status}`}>
              {labelStatus(invoice.status)}
            </span>
          </div>
          <dl className="facts three">
            <div>
              <dt>Amount</dt>
              <dd>{money(invoice.amount, invoice.currency)}</dd>
            </div>
            <div>
              <dt>On the books of</dt>
              <dd>
                <button className="back" onClick={() => onFocus("tenant")}>
                  {tenant.name} · {tenant.id} →
                </button>
              </dd>
            </div>
            <div>
              <dt>Due</dt>
              <dd>{day(invoice.dueOn)}</dd>
            </div>
            <div>
              <dt>Issued</dt>
              <dd>{day(invoice.issuedOn)}</dd>
            </div>
            <div>
              <dt>Approved</dt>
              <dd>
                {invoice.approvedBy
                  ? `${invoice.approvedBy} · ${when(invoice.approvedOn!)}`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>This attempt</dt>
              <dd>
                {attempt.id} · {money(attempt.amount)} of{" "}
                {money(invoice.amount)}
              </dd>
            </div>
          </dl>
          <p className="note">{invoice.memo}</p>

          <div className="proc">
            <h3>Settle Approved Invoice</h3>
            <p className="proc-kicker">
              Human procedure as recorded on this invoice. You do not settle —
              you read whether settlement is still live, posted, or abandoned.
            </p>
            <ol className="steps">
              {procedure.map((s) => (
                <li key={s.n} className={s.state}>
                  <span className="n">{String(s.n).padStart(2, "0")}</span>
                  <div>
                    {s.attemptId ? (
                      <button
                        className="back"
                        onClick={() => onSwitchAttempt(s.attemptId!, "attempt")}
                      >
                        {s.label}
                      </button>
                    ) : (
                      s.label
                    )}
                    <span className="step-at">
                      {[
                        s.actor,
                        s.at
                          ? when(s.at)
                          : s.state === "now"
                            ? "now"
                            : s.state === "wait"
                              ? "not yet"
                              : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="proc">
            <h3>Attempts on this invoice</h3>
            <p className="proc-kicker">
              Switching try keeps the same invoice and tenant — you are still on
              one trail.
            </p>
            <div className="sibs">
              {sibs.map((s) => (
                <Sibling
                  key={s.id}
                  attempt={s}
                  current={s.id === attempt.id}
                  onOpen={() => onSwitchAttempt(s.id, "attempt")}
                />
              ))}
            </div>
          </div>
        </section>

        <section
          id="layer-tenant"
          className={
            focus === "tenant" ? "sheet tenant is-focus" : "sheet tenant"
          }
        >
          <p className="sheet-index">3 · Tenant</p>
          <div className="sheet-head">
            <h2>
              <span>{tenant.id}</span>
              {tenant.name}
            </h2>
          </div>
          <dl className="facts">
            <div>
              <dt>Legal</dt>
              <dd>{tenant.legalName}</dd>
            </div>
            <div>
              <dt>Jurisdiction</dt>
              <dd>{tenant.jurisdiction}</dd>
            </div>
            <div>
              <dt>Books</dt>
              <dd>{tenant.books}</dd>
            </div>
            <div>
              <dt>AP desk</dt>
              <dd>{tenant.apDesk}</dd>
            </div>
            <div>
              <dt>Paying account</dt>
              <dd>****{tenant.bankLast4}</dd>
            </div>
            <div>
              <dt>This invoice</dt>
              <dd>
                {invoice.invoiceNumber} · {labelStatus(invoice.status)}
              </dd>
            </div>
          </dl>
          <p className="note">{tenant.notes}</p>

          <div className="proc">
            <h3>Invoice book, this period</h3>
            <p className="proc-kicker">
              Snapshot only — the lifecycle of bills on these books. The
              highlighted row is the invoice this attempt traces to.
            </p>
            <table className="book">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Supplier</th>
                  <th>Status</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {book.map((inv) => (
                  <tr
                    key={inv.id}
                    className={inv.id === invoice.id ? "current" : undefined}
                  >
                    <td className="num">{inv.invoiceNumber}</td>
                    <td>{inv.supplier}</td>
                    <td>
                      <span className={`slug ${inv.status}`}>
                        {labelStatus(inv.status)}
                      </span>
                    </td>
                    <td>{money(inv.amount, inv.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

function Sibling({
  attempt,
  current,
  onOpen,
}: {
  attempt: PaymentAttempt;
  current: boolean;
  onOpen: () => void;
}) {
  return (
    <button className={current ? "sib this" : "sib"} onClick={onOpen}>
      <b>{attempt.id}</b>
      {attempt.status} · {money(attempt.amount)} · {day(attempt.at)}
      {current ? " · this try" : ""}
    </button>
  );
}

function labelStatus(status: InvoiceStatus): string {
  return status.replace("_", " ");
}
