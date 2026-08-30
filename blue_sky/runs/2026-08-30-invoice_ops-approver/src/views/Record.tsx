import { useEffect, useMemo, useRef, useState } from "react";
import type { Invoice } from "../types";
import {
  matchHint,
  matchLabel,
  riskOf,
  riskLine,
  statusBand,
  usd,
} from "../format";

type Phase = "inspect" | "approve" | "reject" | "pressed";

const REJECT_REASONS = [
  "Unmatched to purchase order",
  "Amount does not agree",
  "Duplicate of an earlier invoice",
  "Wrong job or wrong supplier",
  "Other",
];

type Props = {
  invoice: Invoice;
  remaining: number;
  onPutBack: () => void;
  onStamp: (
    id: string,
    action: "approved" | "rejected",
    reason: string,
  ) => string | null;
  onAdvance: (nextId: string | null) => void;
};

export function Record({
  invoice,
  remaining,
  onPutBack,
  onStamp,
  onAdvance,
}: Props) {
  const [phase, setPhase] = useState<Phase>("inspect");
  const [chip, setChip] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [nextId, setNextId] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      timers.current.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  const risk = riskOf(invoice);
  const canStamp = invoice.status === "submitted";
  const reasonText = useMemo(() => {
    if (chip && chip !== "Other") {
      return note.trim() ? `${chip}. ${note.trim()}` : chip;
    }
    return note.trim();
  }, [chip, note]);

  function confirm(action: "approved" | "rejected") {
    if (action === "rejected" && !reasonText) {
      setError("A reason is required to return this invoice.");
      return;
    }
    if (action === "approved" && risk !== "clean" && !note.trim()) {
      setError("Note why you are releasing a file that does not fully match.");
      return;
    }
    const reason =
      action === "approved"
        ? note.trim() ||
          (risk === "clean"
            ? "Lines agree with the purchase order."
            : "Released with exception.")
        : reasonText;
    const nxt = onStamp(invoice.id, action, reason);
    setNextId(nxt);
    setPhase("pressed");
    timers.current.push(window.setTimeout(() => setLeaving(true), 520));
    timers.current.push(window.setTimeout(() => onAdvance(nxt), 980));
  }

  return (
    <main className="stage">
      <article className={leaving ? "paper leaving" : "paper"}>
        <div className={`band ${invoice.status}`}>
          <span>{statusBand(invoice.status)}</span>
          <span>{invoice.invoice_number}</span>
        </div>

        {phase === "pressed" && invoice.decision && (
          <div className={`impression ${invoice.decision.action}`}>
            {invoice.decision.action === "approved" ? "Approved" : "Rejected"}
          </div>
        )}

        <div className="doc">
          <div className="doc-top">
            <span>Received {invoice.received_on}</span>
            <span>
              {invoice.submitted_by
                ? `Submitted by ${invoice.submitted_by} · ${invoice.submitted_at}`
                : "Not submitted"}
            </span>
          </div>
          <h1 className="supplier-lg">{invoice.supplier}</h1>
          <div className="amount-lg">{usd(invoice.amount)}</div>
          <p className="memo">{invoice.memo}</p>

          <dl className="facts">
            <div>
              <dt>Invoice</dt>
              <dd>{invoice.invoice_number}</dd>
            </div>
            <div>
              <dt>Lines</dt>
              <dd>{riskLine(invoice)}</dd>
            </div>
            <div>
              <dt>Next if you stamp</dt>
              <dd>
                {canStamp
                  ? remaining
                    ? `${remaining} still on the desk`
                    : "Desk goes quiet"
                  : "Already stamped"}
              </dd>
            </div>
          </dl>

          <section className="related">
            <h2>Related work</h2>
            <p className="hint">
              Inspect the lines before you stamp. Purchase-order match is the
              check.
            </p>
            <div className="lines">
              {invoice.lines.map((line) => (
                <div key={line.id} className={`line ${line.po_match}`}>
                  <div className="desc">{line.description}</div>
                  <div className="ua">{usd(line.unit_amount)}</div>
                  <div className="po">
                    {line.po_number
                      ? line.po_number
                      : line.po_match === "not_applicable"
                        ? "No PO on this vendor"
                        : "No PO"}
                    {" · "}
                    {matchHint(line.po_match)}
                  </div>
                  <div className={`tag ${line.po_match}`}>
                    {matchLabel(line.po_match)}
                  </div>
                  {line.note && <div className="line-note">{line.note}</div>}
                </div>
              ))}
            </div>
            {canStamp && risk === "halt" && (
              <div className="callout halt">
                A line has no purchase order. Reject it, or approve with an
                exception note.
              </div>
            )}
            {canStamp && risk === "watch" && (
              <div className="callout">
                Some lines only partially agree with the PO. Check the
                quantities before you release it.
              </div>
            )}
          </section>

          {invoice.decision && phase !== "pressed" && (
            <div className="decision">
              <b>
                {invoice.decision.action === "approved"
                  ? "Released by"
                  : "Returned by"}{" "}
                {invoice.decision.by}
              </b>
              {" · "}
              {invoice.decision.at}
              <div style={{ marginTop: 6 }}>{invoice.decision.reason}</div>
              {invoice.decision.action === "approved" && (
                <div style={{ marginTop: 8 }}>
                  Settlement is the next human step. Payment is not made at this
                  desk.
                </div>
              )}
            </div>
          )}
        </div>

        {canStamp && phase === "inspect" && (
          <div className="stamps">
            <button className="stamp no" onClick={() => setPhase("reject")}>
              Reject
            </button>
            <button className="stamp yes" onClick={() => setPhase("approve")}>
              Approve
            </button>
          </div>
        )}

        {canStamp && phase === "reject" && (
          <div className="sheet-panel">
            <h3>Return it with a reason</h3>
            <p>
              The submitter will see this. Choose a cause, then add anything
              they must fix.
            </p>
            <div className="reasons">
              {REJECT_REASONS.map((r) => (
                <button
                  key={r}
                  className={chip === r ? "on" : ""}
                  onClick={() => {
                    setChip(r);
                    setError(null);
                  }}
                >
                  {r}
                </button>
              ))}
            </div>
            <textarea
              value={note}
              onChange={(e) => {
                setNote(e.target.value);
                setError(null);
              }}
              placeholder="What must change before this can come back…"
            />
            {error && <p className="err">{error}</p>}
            <div className="stamps" style={{ padding: "16px 0 0" }}>
              <button className="stamp no" onClick={() => setPhase("inspect")}>
                Cancel
              </button>
              <button
                className="stamp no solid"
                onClick={() => confirm("rejected")}
              >
                Stamp reject
              </button>
            </div>
          </div>
        )}

        {canStamp && phase === "approve" && (
          <div className="sheet-panel">
            <h3>
              {risk === "clean"
                ? "Release for settlement"
                : "Release with an exception"}
            </h3>
            <p>
              {risk === "clean"
                ? "Lines agree with the purchase order. Stamping approves the invoice. Accounts payable will settle it later — not you."
                : "This file does not fully match a purchase order. If you still release it, say why. Settlement is the next human’s job."}
            </p>
            <textarea
              value={note}
              onChange={(e) => {
                setNote(e.target.value);
                setError(null);
              }}
              placeholder={
                risk === "clean"
                  ? "Optional note (the default is that the lines agree)…"
                  : "Why this exception is acceptable…"
              }
            />
            {error && <p className="err">{error}</p>}
            <div className="stamps" style={{ padding: "16px 0 0" }}>
              <button className="stamp no" onClick={() => setPhase("inspect")}>
                Cancel
              </button>
              <button className="stamp yes" onClick={() => confirm("approved")}>
                Stamp approve
              </button>
            </div>
          </div>
        )}
      </article>

      {phase !== "pressed" && (
        <button className="put-back" onClick={onPutBack}>
          {canStamp
            ? remaining
              ? "Put it back · return to the stack"
              : "Put it back"
            : "Back to the desk"}
        </button>
      )}

      {phase === "pressed" && (
        <p className="footnote" style={{ marginTop: 18 }}>
          {nextId
            ? "Next sheet is coming up the stack…"
            : "That was the last one. The desk goes quiet."}
        </p>
      )}
    </main>
  );
}
