import { useState, type CSSProperties } from "react";
import { MatchChip, MoneyInput, Stamp } from "./ui";
import {
  blockers,
  canEditLines,
  matchHint,
  pileOf,
  posForSupplier,
  supplierOf,
  verbFor,
} from "./domain";
import { isoDate, lineTotal, money, prettyDate, todayLabel } from "./money";
import type {
  Invoice,
  LineItem,
  Person,
  PurchaseOrder,
  Supplier,
} from "./types";

export function Door({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="door">
      <div className="door-mark">Kestrel Press · Production</div>
      <div className="book">
        <p className="book-kicker">Cloth-bound · 2026</p>
        <h1>Daybook</h1>
        <p className="book-sub">The slips in front of you today.</p>
        <div className="book-rule" />
        <p>
          Supplier invoices arrive as paper in all but name. Raise them, match
          the lines, send them to the books — or settle what finance already
          approved.
        </p>
        <button className="person-btn" onClick={onEnter}>
          <span>
            <strong>Mara Ellison</strong>
            <span>Production coordinator</span>
          </span>
          <em>Requester</em>
        </button>
      </div>
      <div className="door-foot">No password. This is a studio desk.</div>
    </div>
  );
}

export function Desk({
  person,
  invoices,
  suppliers,
  onRaise,
  onOpen,
  onLeave,
}: {
  person: Person;
  invoices: Invoice[];
  suppliers: Supplier[];
  onRaise: () => void;
  onOpen: (id: string) => void;
  onLeave: () => void;
}) {
  const needs = invoices.filter((i) => pileOf(i) === "needs");
  const moving = invoices.filter((i) => pileOf(i) === "moving");
  const closed = invoices.filter((i) => pileOf(i) === "closed");
  const n = needs.length;
  const hero =
    n === 0
      ? "The blotter is clear."
      : n === 1
        ? "One slip is waiting on you."
        : `${["Two", "Three", "Four", "Five", "Six"][n - 2] ?? n} slips are waiting on you.`;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <h1>Daybook</h1>
          <span className="press">{person.press}</span>
        </div>
        <div className="who">
          <span>
            {person.name} · {person.title}
          </span>
          <button onClick={onLeave}>Close the book</button>
        </div>
      </header>
      <main className="desk">
        <div className="desk-hero">
          <div className="date">{todayLabel()}</div>
          <h2>{hero}</h2>
          <p>
            Raise a supplier invoice, finish what you started, answer a
            rejection, or attest that an approved shipment actually arrived.
          </p>
        </div>

        <button className="raise" onClick={onRaise}>
          <span>
            <kbd>New slip</kbd>
            <strong>A supplier billed the press.</strong>
            <span>
              Raise it onto the blotter, line by line, then send it to the
              books.
            </span>
          </span>
          <span className="raise-go">Raise a slip →</span>
        </button>

        <div className="section-label">On the blotter</div>
        {needs.length === 0 ? (
          <p className="empty-pile">
            Nothing needs your hand. Raise a slip, or let the books work.
          </p>
        ) : (
          <div className="stack">
            {needs.map((inv, i) => (
              <SlipCard
                key={inv.id}
                invoice={inv}
                supplier={supplierOf(suppliers, inv.supplierId)}
                tilt={[-1.4, 0.8, -0.6][i % 3] ?? 0}
                onOpen={() => onOpen(inv.id)}
              />
            ))}
          </div>
        )}

        <div className="section-label">Already moving</div>
        {moving.length === 0 ? (
          <p className="empty-pile">No slips in flight.</p>
        ) : (
          <div className="stack quiet">
            {moving.map((inv) => (
              <SlipCard
                key={inv.id}
                invoice={inv}
                supplier={supplierOf(suppliers, inv.supplierId)}
                tilt={0}
                onOpen={() => onOpen(inv.id)}
              />
            ))}
          </div>
        )}

        <div className="section-label">Closed</div>
        <div className="stack quiet">
          {closed.map((inv) => (
            <SlipCard
              key={inv.id}
              invoice={inv}
              supplier={supplierOf(suppliers, inv.supplierId)}
              tilt={0}
              onOpen={() => onOpen(inv.id)}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

function SlipCard({
  invoice,
  supplier,
  tilt,
  onOpen,
}: {
  invoice: Invoice;
  supplier?: Supplier;
  tilt: number;
  onOpen: () => void;
}) {
  return (
    <button
      className="slip-card"
      style={{ "--tilt": `${tilt}deg` } as CSSProperties}
      onClick={onOpen}
    >
      <div className="meta">
        <Stamp status={invoice.status} />
        <span className="num">{prettyDate(invoice.issuedOn)}</span>
      </div>
      <div className="supplier">{supplier?.name ?? "Unnamed supplier"}</div>
      <div className="num">{invoice.invoiceNumber || "No number yet"}</div>
      <div className="amt">
        <b>{money(invoice.amountCents)}</b>
        <span className="verb">{verbFor(invoice)}</span>
      </div>
    </button>
  );
}

export function Folio({
  person,
  invoice,
  suppliers,
  pos,
  onChange,
  onBack,
  onSubmit,
  onSettle,
  onStandBy,
  onWithdraw,
  onSplit,
}: {
  person: Person;
  invoice: Invoice;
  suppliers: Supplier[];
  pos: PurchaseOrder[];
  onChange: (next: Invoice) => void;
  onBack: () => void;
  onSubmit: () => void;
  onSettle: (note: string) => void;
  onStandBy: (note: string) => void;
  onWithdraw: () => void;
  onSplit: (lineId: string) => void;
}) {
  const supplier = supplierOf(suppliers, invoice.supplierId);
  const openPos = posForSupplier(pos, invoice.supplierId);
  const editable = canEditLines(invoice.status);
  const issues = blockers(invoice, suppliers);
  const isNew =
    !invoice.invoiceNumber &&
    invoice.lines.length === 0 &&
    invoice.status === "draft";

  return (
    <div className="folio-screen">
      <div className="folio-bar">
        <button className="back" onClick={onBack}>
          ← Back to the blotter
        </button>
        <div className="hint">
          {person.name} · {isNew ? "Raising a slip" : "Invoice record"}
        </div>
      </div>
      <div className="folio-layout">
        <article className="sheet">
          <header className="letterhead">
            <div>
              <p className="press-name">{person.press}</p>
              <p>Production desk · Portland</p>
            </div>
            <div style={{ textAlign: "right" }}>
              <Stamp status={invoice.status} />
              <h2 style={{ marginTop: 12 }}>Supplier invoice</h2>
            </div>
          </header>

          <div className="fields">
            <div className="field">
              <label htmlFor="supplier">Supplier</label>
              {editable ? (
                <SupplierField
                  suppliers={suppliers}
                  value={invoice.supplierId}
                  onPick={(supplierId) => onChange({ ...invoice, supplierId })}
                  onCreate={(name) =>
                    onChange({
                      ...invoice,
                      supplierId: `new:${name}`,
                    })
                  }
                />
              ) : (
                <div className="display">{supplier?.name ?? "—"}</div>
              )}
            </div>
            <div className="field">
              <label htmlFor="number">Their invoice number</label>
              {editable ? (
                <input
                  id="number"
                  value={invoice.invoiceNumber}
                  placeholder="e.g. HB-8891"
                  onChange={(e) =>
                    onChange({ ...invoice, invoiceNumber: e.target.value })
                  }
                />
              ) : (
                <div className="display">{invoice.invoiceNumber}</div>
              )}
            </div>
            <div className="field">
              <label htmlFor="issued">Issued</label>
              {editable ? (
                <input
                  id="issued"
                  type="date"
                  value={invoice.issuedOn}
                  max={isoDate()}
                  onChange={(e) =>
                    onChange({ ...invoice, issuedOn: e.target.value })
                  }
                />
              ) : (
                <div className="display">{prettyDate(invoice.issuedOn)}</div>
              )}
            </div>
          </div>

          <div className="field sheet-note">
            <label htmlFor="note">What this is for</label>
            {editable ? (
              <textarea
                id="note"
                value={invoice.note}
                placeholder="A line of context for the books — edition, job, or delivery."
                onChange={(e) => onChange({ ...invoice, note: e.target.value })}
              />
            ) : (
              <div className="display" style={{ fontSize: 16 }}>
                {invoice.note || "—"}
              </div>
            )}
          </div>

          <div className="lines-head">
            <h3>Lines</h3>
            <span className="muted">{invoice.lines.length} on this slip</span>
          </div>

          <table className="lines">
            <thead>
              <tr>
                <th>Qty</th>
                <th>Description</th>
                <th>Unit</th>
                <th>Amount</th>
                <th>Purchase order</th>
                {editable ? <th className="line-actions" /> : null}
              </tr>
            </thead>
            <tbody>
              {invoice.lines.length === 0 ? (
                <tr>
                  <td colSpan={editable ? 6 : 5}>
                    <p
                      className="muted"
                      style={{ fontStyle: "italic", padding: "12px 0" }}
                    >
                      No lines yet. Add what they charged — paper, binding,
                      freight, a license.
                    </p>
                  </td>
                </tr>
              ) : (
                invoice.lines.map((line) => (
                  <LineRow
                    key={line.id}
                    line={line}
                    openPos={openPos}
                    editable={editable}
                    onChange={(next) =>
                      onChange({
                        ...invoice,
                        lines: invoice.lines.map((l) =>
                          l.id === line.id ? next : l,
                        ),
                      })
                    }
                    onRemove={() =>
                      onChange({
                        ...invoice,
                        lines: invoice.lines.filter((l) => l.id !== line.id),
                      })
                    }
                  />
                ))
              )}
            </tbody>
          </table>

          {editable ? (
            <button
              className="add-line"
              onClick={() =>
                onChange({
                  ...invoice,
                  lines: [
                    ...invoice.lines,
                    {
                      id: `ln-${Math.random().toString(36).slice(2, 8)}`,
                      description: "",
                      quantity: 1,
                      unitAmountCents: 0,
                      poId: null,
                      poMatch: "unmatched",
                      received: false,
                    },
                  ],
                })
              }
            >
              + Add a line
            </button>
          ) : null}

          <div className="totals">
            <table>
              <tbody>
                {invoice.status === "partially_paid" ||
                invoice.status === "paid" ? (
                  <tr>
                    <td>Already paid</td>
                    <td>{money(invoice.paidCents)}</td>
                  </tr>
                ) : null}
                <tr className="grand">
                  <td>Slip total</td>
                  <td>{money(invoice.amountCents)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <footer className="sheet-foot">
            <ul className="blockers">
              {editable
                ? issues.map((b) => <li key={b.id}>{b.text}</li>)
                : invoice.status === "submitted"
                  ? [
                      <li key="wait">
                        The books have it. Nothing for you until they stamp it.
                      </li>,
                    ]
                  : []}
            </ul>
            <div className="row-btns">
              {editable && invoice.status !== "disputed" ? (
                <button className="secondary" onClick={onBack}>
                  Leave on the desk
                </button>
              ) : null}
              {editable && invoice.status !== "disputed" ? (
                <button
                  className="primary"
                  disabled={issues.length > 0}
                  onClick={onSubmit}
                >
                  Send to the books
                </button>
              ) : null}
            </div>
          </footer>
        </article>

        <Notepad
          invoice={invoice}
          supplier={supplier}
          openPos={openPos}
          person={person}
          onChange={onChange}
          onSettle={onSettle}
          onStandBy={onStandBy}
          onWithdraw={onWithdraw}
          onSplit={onSplit}
          onUsePo={(lineId, poId) =>
            onChange({
              ...invoice,
              lines: invoice.lines.map((l) =>
                l.id === lineId ? { ...l, poId, poMatch: "matched" } : l,
              ),
            })
          }
          onMarkNone={(lineId) =>
            onChange({
              ...invoice,
              lines: invoice.lines.map((l) =>
                l.id === lineId
                  ? { ...l, poId: null, poMatch: "not_applicable" }
                  : l,
              ),
            })
          }
        />
      </div>
    </div>
  );
}

function SupplierField({
  suppliers,
  value,
  onPick,
  onCreate,
}: {
  suppliers: Supplier[];
  value: string;
  onPick: (id: string) => void;
  onCreate: (name: string) => void;
}) {
  const isNew = value.startsWith("new:");
  const [fresh, setFresh] = useState(isNew ? value.slice(4) : "");
  return (
    <>
      <select
        id="supplier"
        value={isNew ? "new" : value}
        onChange={(e) => {
          if (e.target.value === "new") onCreate(fresh || "New supplier");
          else onPick(e.target.value);
        }}
      >
        <option value="">Choose who billed you…</option>
        {suppliers.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
        <option value="new">Someone new…</option>
      </select>
      {isNew ? (
        <div className="inline-new">
          <input
            value={fresh}
            placeholder="Supplier name"
            onChange={(e) => {
              setFresh(e.target.value);
              onCreate(e.target.value);
            }}
          />
        </div>
      ) : null}
    </>
  );
}

function LineRow({
  line,
  openPos,
  editable,
  onChange,
  onRemove,
}: {
  line: LineItem;
  openPos: PurchaseOrder[];
  editable: boolean;
  onChange: (line: LineItem) => void;
  onRemove: () => void;
}) {
  const ext = lineTotal(line.quantity, line.unitAmountCents);
  const po = openPos.find((p) => p.id === line.poId);
  return (
    <tr>
      <td className="qty">
        {editable ? (
          <input
            className="qty"
            type="number"
            min={0}
            step={1}
            value={line.quantity}
            onChange={(e) =>
              onChange({ ...line, quantity: Number(e.target.value) || 0 })
            }
          />
        ) : (
          <div className="read">{line.quantity}</div>
        )}
      </td>
      <td>
        {editable ? (
          <input
            value={line.description}
            placeholder="What they charged"
            onChange={(e) => onChange({ ...line, description: e.target.value })}
          />
        ) : (
          <div>{line.description}</div>
        )}
      </td>
      <td className="unit">
        {editable ? (
          <MoneyInput
            className="unit"
            cents={line.unitAmountCents}
            onChange={(unitAmountCents) =>
              onChange({ ...line, unitAmountCents })
            }
          />
        ) : (
          <div className="read">{money(line.unitAmountCents)}</div>
        )}
      </td>
      <td className="ext">{money(ext)}</td>
      <td className="po-cell">
        {editable ? (
          <>
            <select
              value={
                line.poMatch === "not_applicable" ? "na" : (line.poId ?? "")
              }
              onChange={(e) => {
                const v = e.target.value;
                if (v === "na")
                  onChange({ ...line, poId: null, poMatch: "not_applicable" });
                else if (v === "")
                  onChange({ ...line, poId: null, poMatch: "unmatched" });
                else onChange({ ...line, poId: v });
              }}
            >
              <option value="">Link a PO…</option>
              {openPos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.number} · {money(p.remainingCents)} left
                </option>
              ))}
              <option value="na">No purchase order</option>
            </select>
            <span className="hint">
              <MatchChip match={line.poMatch} /> {po ? po.number : null}
            </span>
          </>
        ) : (
          <div>
            <MatchChip match={line.poMatch} />
            <span className="hint">
              {po?.number ??
                (line.poMatch === "not_applicable" ? "None needed" : "—")}
            </span>
          </div>
        )}
      </td>
      {editable ? (
        <td className="line-actions">
          <button className="ghost" onClick={onRemove} aria-label="Remove line">
            ×
          </button>
        </td>
      ) : null}
    </tr>
  );
}

function Notepad({
  invoice,
  supplier,
  openPos,
  person,
  onChange,
  onSettle,
  onStandBy,
  onWithdraw,
  onSplit,
  onUsePo,
  onMarkNone,
}: {
  invoice: Invoice;
  supplier?: Supplier;
  openPos: PurchaseOrder[];
  person: Person;
  onChange: (next: Invoice) => void;
  onSettle: (note: string) => void;
  onStandBy: (note: string) => void;
  onWithdraw: () => void;
  onSplit: (lineId: string) => void;
  onUsePo: (lineId: string, poId: string) => void;
  onMarkNone: (lineId: string) => void;
}) {
  const [settleNote, setSettleNote] = useState("");
  const [disputeReply, setDisputeReply] = useState("");
  const unmatched = invoice.lines.filter((l) => l.poMatch === "unmatched");
  const partial = invoice.lines.filter((l) => l.poMatch === "partial");
  const allReceived =
    invoice.lines.length > 0 && invoice.lines.every((l) => l.received);

  let lede =
    "Line items live here as related work — matching, receipt, argument.";
  if (invoice.status === "draft")
    lede = "Finish the slip. Unmatched lines will not go to the books.";
  if (invoice.status === "rejected")
    lede = "The books refused this. Fix the lines, then send it back.";
  if (invoice.status === "approved" && !invoice.settledAt) {
    lede =
      "Finance approved it. Attest that the goods or work actually arrived.";
  }
  if (invoice.status === "approved" && invoice.settledAt)
    lede = "You released this for payment.";
  if (invoice.status === "submitted")
    lede = "Waiting. Related work is quiet until they stamp it.";
  if (invoice.status === "disputed")
    lede = "Someone is arguing the rate. Answer from this pad.";
  if (invoice.status === "partially_paid")
    lede = "Treasury is paying it down. Nothing for you.";
  if (invoice.status === "paid") lede = "Closed. The slip is a record now.";

  return (
    <aside className="notepad">
      <h3>Related work</h3>
      <p className="lede">{lede}</p>

      {invoice.status === "rejected" && invoice.rejectedReason ? (
        <div className="work-item">
          <h4>Rejection</h4>
          <div className="warn">{invoice.rejectedReason}</div>
          {invoice.lines
            .filter((l) => l.poMatch === "partial")
            .map((l) => (
              <button
                key={l.id}
                className="suggest"
                onClick={() => onSplit(l.id)}
              >
                <b>Split across open orders</b>
                Keep what the current order can still take, and put the rest on
                the next open order at the same rate.
              </button>
            ))}
        </div>
      ) : null}

      {invoice.status === "disputed" && invoice.disputeNote ? (
        <div className="work-item">
          <h4>The argument</h4>
          <div className="warn">{invoice.disputeNote}</div>
          <div className="field" style={{ marginTop: 10 }}>
            <label htmlFor="reply">Your note</label>
            <textarea
              id="reply"
              value={disputeReply}
              placeholder="Stand by a short-pay, or say you will wait for a reissue."
              onChange={(e) => setDisputeReply(e.target.value)}
            />
          </div>
          <div className="row-btns" style={{ marginTop: 10 }}>
            <button className="secondary" onClick={onWithdraw}>
              Withdraw to draft
            </button>
            <button className="primary" onClick={() => onStandBy(disputeReply)}>
              Stand by this slip
            </button>
          </div>
        </div>
      ) : null}

      {invoice.status === "approved" && !invoice.settledAt ? (
        <div className="work-item">
          <h4>Settle receipt</h4>
          <p>
            Check each line you actually received. That releases the slip for
            payment.
          </p>
          {invoice.lines.map((line) => (
            <label key={line.id} className="attest">
              <input
                type="checkbox"
                checked={line.received}
                onChange={(e) =>
                  onChange({
                    ...invoice,
                    lines: invoice.lines.map((l) =>
                      l.id === line.id
                        ? { ...l, received: e.target.checked }
                        : l,
                    ),
                  })
                }
              />
              <span>
                <b>{line.description}</b>
                <br />
                <span className="muted">
                  {line.quantity} × {money(line.unitAmountCents)}
                </span>
              </span>
            </label>
          ))}
          <div className="field">
            <label htmlFor="settle">Note for treasury</label>
            <textarea
              id="settle"
              value={settleNote}
              placeholder="Cartons on the dock, cloth on the shelf…"
              onChange={(e) => setSettleNote(e.target.value)}
            />
          </div>
          <div className="row-btns" style={{ marginTop: 10 }}>
            <button
              className="primary"
              disabled={!allReceived}
              onClick={() => onSettle(settleNote)}
            >
              I received this
            </button>
          </div>
        </div>
      ) : null}

      {invoice.settledAt ? (
        <div className="work-item">
          <h4>Settlement</h4>
          <div className="ok">
            {invoice.settledBy} attested receipt
            {invoice.settlementNote ? ` — ${invoice.settlementNote}` : "."}
          </div>
        </div>
      ) : null}

      {(invoice.status === "partially_paid" || invoice.status === "paid") && (
        <div className="work-item">
          <h4>Payment</h4>
          <p>
            {money(invoice.paidCents)} of {money(invoice.amountCents)}
          </p>
          <div className="paybar">
            <span
              style={{
                width: `${invoice.amountCents ? Math.min(100, (invoice.paidCents / invoice.amountCents) * 100) : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {unmatched.length > 0 && canEditLines(invoice.status) ? (
        <div className="work-item">
          <h4>Unmatched lines</h4>
          {unmatched.map((line) => {
            const guess = guessPo(line, openPos);
            return (
              <div key={line.id} style={{ marginTop: 8 }}>
                <p>
                  {line.description || "Untitled line"} ·{" "}
                  {money(lineTotal(line.quantity, line.unitAmountCents))}
                </p>
                {guess ? (
                  <button
                    className="suggest"
                    onClick={() => onUsePo(line.id, guess.id)}
                  >
                    <b>Use {guess.number}</b>
                    {guess.description}
                  </button>
                ) : supplier ? (
                  <p className="muted">
                    No open order for {supplier.name} looks like this line.
                  </p>
                ) : (
                  <p className="muted">
                    Name a supplier to see their open orders.
                  </p>
                )}
                <button className="suggest" onClick={() => onMarkNone(line.id)}>
                  <b>No purchase order</b>
                  Mark as not applicable — a one-off, rush fee, or license.
                </button>
              </div>
            );
          })}
        </div>
      ) : null}

      {partial.length > 0 && invoice.status !== "rejected" ? (
        <div className="work-item">
          <h4>Partial matches</h4>
          {partial.map((line) => (
            <p key={line.id} style={{ marginTop: 6 }}>
              {line.description || "Untitled"} — {matchHint(line.poMatch)} You
              can still send it; the books will see the gap.
            </p>
          ))}
        </div>
      ) : null}

      {invoice.lines.length > 0 &&
      unmatched.length === 0 &&
      invoice.status === "draft" ? (
        <div className="work-item">
          <h4>Ready</h4>
          <div className="ok">
            Every line is matched or marked as having no PO. Send it when the
            number and supplier are true.
          </div>
        </div>
      ) : null}

      {invoice.status === "submitted" ? (
        <div className="work-item">
          <h4>In the books</h4>
          <p className="muted">
            {person.name} sent this. Approval, rejection, or a dispute will put
            it back on the blotter.
          </p>
        </div>
      ) : null}

      {invoice.lines.map((line) => (
        <div key={`m-${line.id}`} className="work-item">
          <h4>
            Line · <MatchChip match={line.poMatch} />
          </h4>
          <p>
            {line.description || "Untitled"} — {line.quantity} ×{" "}
            {money(line.unitAmountCents)} ={" "}
            {money(lineTotal(line.quantity, line.unitAmountCents))}
          </p>
          <p className="muted">{matchHint(line.poMatch)}</p>
        </div>
      ))}
    </aside>
  );
}

function guessPo(
  line: LineItem,
  openPos: PurchaseOrder[],
): PurchaseOrder | undefined {
  if (openPos.length === 0) return undefined;
  const total = lineTotal(line.quantity, line.unitAmountCents);
  const unitHit = openPos.find(
    (p) =>
      p.unitAmountCents === line.unitAmountCents &&
      line.quantity <= p.remainingQty,
  );
  if (unitHit) return unitHit;
  const qtyHit = openPos.find(
    (p) => line.quantity === p.remainingQty && total <= p.remainingCents,
  );
  if (qtyHit) return qtyHit;
  const desc = line.description.toLowerCase();
  const wordHit = openPos.find((p) => {
    const hay = p.description.toLowerCase();
    return (
      (desc.includes("bind") && hay.includes("bind")) ||
      (desc.includes("freight") && hay.includes("freight")) ||
      (desc.includes("cover") && hay.includes("cover")) ||
      (desc.includes("cloth") && hay.includes("cloth")) ||
      (desc.includes("ink") && hay.includes("ink")) ||
      (desc.includes("license") && hay.includes("license"))
    );
  });
  if (wordHit) return wordHit;
  return openPos.length === 1 ? openPos[0] : undefined;
}
