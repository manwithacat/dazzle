import { formatDue, formatWhen, money, RAIL_LABEL } from "./money";
import {
  creditedCents,
  paidCents,
  remainder,
  trayItems,
  useDesk,
} from "./state";
import type { Invoice, StampKind } from "./types";

const STAMP_COPY: Record<StampKind, string> = {
  paid: "Paid",
  partial: "Partial",
  returned: "Returned",
  refused: "Stood down",
  credited: "Credited",
  unfounded: "To ready",
};

function lifeLine(inv: Invoice): string {
  if (inv.status === "approved")
    return "submitted · approved · awaiting remittance";
  if (inv.status === "partially_paid")
    return "submitted · approved · partially remitted";
  if (inv.status === "disputed")
    return "submitted · approved · disputed · open";
  if (inv.status === "paid") return "submitted · approved · paid";
  if (inv.status === "rejected") return "submitted · approved · stood down";
  if (inv.status === "submitted") return "submitted";
  return "draft";
}

export default function Paper() {
  const { state } = useDesk();
  const inv = state.invoices.find((i) => i.id === state.selectedId);
  const readyN = trayItems(state, "ready").length;
  const dispN = trayItems(state, "disputes").length;

  if (!inv) {
    return (
      <div className="empty-blotter">
        <div>
          <h2>
            {readyN + dispN === 0
              ? "The desk is clear."
              : "Nothing in this tray."}
          </h2>
          <p>
            {readyN + dispN === 0
              ? "Nothing to remit. Nothing in dispute."
              : readyN > 0
                ? `${readyN} still ready to remit.`
                : `${dispN} still in dispute.`}
          </p>
        </div>
      </div>
    );
  }

  const paid = paidCents(inv, state.attempts);
  const credited = creditedCents(inv);
  const left = remainder(inv, state.attempts);
  const attempts = state.attempts.filter((a) => a.invoiceId === inv.id);
  const stamp =
    state.stamp && state.stamp.invoiceId === inv.id ? state.stamp : null;

  return (
    <div className="paper-wrap">
      <article className="paper">
        <header className="paper-head">
          <div>
            <p className="house">Harrow & Co. · accounts payable</p>
            <h2 className="inv-no">{inv.invoiceNumber}</h2>
          </div>
          <div className="folio">{inv.terms}</div>
        </header>

        <p className="supplier">{inv.supplier}</p>
        <p className="for-what">{inv.forWhat}</p>
        <p className="detail">{inv.detail}</p>

        {inv.dispute && (
          <aside className="pin">
            <p className="eyebrow">
              Open dispute · {money(inv.dispute.contendedAmount)} in contention
            </p>
            <p>{inv.dispute.claim}</p>
            <p className="by">
              {inv.dispute.openedBy} · {inv.dispute.openedOn.slice(8, 10)} Aug
            </p>
          </aside>
        )}

        <table className="figures">
          <tbody>
            <tr>
              <th>Original</th>
              <td>{money(inv.amount)}</td>
            </tr>
            {paid > 0 && (
              <tr>
                <th>Remitted</th>
                <td>{money(paid)}</td>
              </tr>
            )}
            {credited > 0 && (
              <tr>
                <th>Credited</th>
                <td>{money(credited)}</td>
              </tr>
            )}
            <tr className="due">
              <th>{left === 0 ? "Closed" : "Remainder due"}</th>
              <td>{money(left)}</td>
            </tr>
          </tbody>
        </table>

        <div className="meta-row">
          <span>
            <strong>{formatDue(inv.dueDate)}</strong>
          </span>
          <span>{inv.bankOnFile}</span>
        </div>

        <p className="life">
          <b>{inv.status.replace("_", " ")}</b>
          {"  ·  "}
          {lifeLine(inv)}
        </p>

        {(attempts.length > 0 || inv.credits.length > 0) && (
          <ul className="log">
            {attempts.map((a) => (
              <li key={a.id} className={a.status === "failed" ? "fail" : ""}>
                <span>
                  {RAIL_LABEL[a.rail]} {a.status}
                  {a.returnReason ? ` · ${a.returnReason}` : ""}
                </span>
                <span>
                  {money(a.amount)} · {formatWhen(a.at)}
                </span>
              </li>
            ))}
            {inv.credits.map((c) => (
              <li key={c.id} className="credit">
                <span>Credit · {c.note}</span>
                <span>
                  {money(c.amount)} · {formatWhen(c.at)}
                </span>
              </li>
            ))}
          </ul>
        )}

        {inv.resolutionNote && !inv.dispute && (
          <p className="detail" style={{ marginTop: 18 }}>
            {inv.resolutionNote}
          </p>
        )}

        {stamp && (
          <div className={`stamp ${stamp.kind}`}>{STAMP_COPY[stamp.kind]}</div>
        )}
        {state.posting && state.posting.invoiceId === inv.id && (
          <div className="posting-veil">Posting to the rail…</div>
        )}
      </article>
    </div>
  );
}
