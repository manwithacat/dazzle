import { useEffect, useState } from "react";
import { money, moneyPlain, parseMoney, RAIL_LABEL } from "./money";
import { remainder, useDesk } from "./state";
import type { Invoice, Rail } from "./types";

function RemitPad({ inv }: { inv: Invoice }) {
  const { state, dispatch } = useDesk();
  const left = remainder(inv, state.attempts);
  const [text, setText] = useState(moneyPlain(left));
  const [rail, setRail] = useState<Rail>(
    inv.bankOnFile.toLowerCase().includes("wire") ? "wire" : "ach",
  );
  const [reference, setReference] = useState(inv.invoiceNumber);
  const [err, setErr] = useState("");

  useEffect(() => {
    setText(moneyPlain(left));
  }, [inv.id, left]);

  useEffect(() => {
    setReference(inv.invoiceNumber);
    setErr("");
    setRail(inv.bankOnFile.toLowerCase().includes("wire") ? "wire" : "ach");
  }, [inv.id, inv.invoiceNumber, inv.bankOnFile]);

  const cents = parseMoney(text);

  function send(outcome: "succeeded" | "failed") {
    if (cents === null) {
      setErr("Enter a dollar amount.");
      return;
    }
    if (cents <= 0 || cents > left) {
      setErr(`Must be between $0.01 and ${money(left)}.`);
      return;
    }
    setErr("");
    dispatch({
      type: "startRemit",
      amount: cents,
      rail,
      reference: reference.trim() || inv.invoiceNumber,
      outcome,
    });
  }

  const busy = Boolean(state.posting);

  return (
    <section className="pad">
      <h2>Remit</h2>
      <p className="hint">
        Record what actually left the house. The till does not talk to a bank —
        you do.
      </p>
      <p className="due-call">Remainder {money(left)}</p>

      <label className="field">
        <span>Amount</span>
        <input
          className="mono"
          inputMode="decimal"
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      {err && <p className="error">{err}</p>}

      <div className="field">
        <span>Rail</span>
        <div className="rails">
          {(["ach", "wire", "check"] as Rail[]).map((r) => (
            <button
              key={r}
              type="button"
              className={rail === r ? "on" : ""}
              disabled={busy}
              onClick={() => setRail(r)}
            >
              {RAIL_LABEL[r]}
            </button>
          ))}
        </div>
      </div>

      <p className="bank">{inv.bankOnFile}</p>

      <label className="field">
        <span>Reference</span>
        <input
          value={reference}
          disabled={busy}
          onChange={(e) => setReference(e.target.value)}
        />
      </label>

      <div className="actions">
        <button
          className="primary"
          disabled={busy}
          onClick={() => send("succeeded")}
        >
          Record remittance
        </button>
        <button
          className="danger"
          disabled={busy}
          onClick={() => send("failed")}
        >
          Bank returned this attempt
        </button>
      </div>
    </section>
  );
}

function DisputePad({ inv }: { inv: Invoice }) {
  const { state, dispatch } = useDesk();
  const contended =
    inv.dispute?.contendedAmount ?? remainder(inv, state.attempts);
  const left = remainder(inv, state.attempts);
  const [note, setNote] = useState("");
  const [creditText, setCreditText] = useState(moneyPlain(contended));
  const [err, setErr] = useState("");

  useEffect(() => {
    const c = inv.dispute?.contendedAmount ?? remainder(inv, state.attempts);
    setCreditText(moneyPlain(c));
    setNote("");
    setErr("");
  }, [inv.id, inv.dispute, state.attempts, inv]);

  function applyCredit() {
    const cents = parseMoney(creditText);
    if (cents === null || cents <= 0) {
      setErr("Enter a credit amount.");
      return;
    }
    if (cents > left) {
      setErr(`Credit cannot exceed remainder ${money(left)}.`);
      return;
    }
    dispatch({
      type: "credit",
      amount: cents,
      note: note.trim() || "Credit accepted against the open dispute.",
    });
  }

  return (
    <section className="pad">
      <h2>Resolve</h2>
      <p className="hint">
        The shop has stopped this invoice. Either the claim stands, a credit
        comes off, or the whole bill is stood down.
      </p>

      <label className="field">
        <span>Note on the book</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What did you decide, and why?"
        />
      </label>

      <label className="field">
        <span>Credit amount</span>
        <input
          className="mono"
          inputMode="decimal"
          value={creditText}
          onChange={(e) => setCreditText(e.target.value)}
        />
      </label>
      {err && <p className="error">{err}</p>}

      <div className="actions">
        <button className="primary" onClick={applyCredit}>
          Accept credit, return to ready
        </button>
        <button
          className="ghost"
          onClick={() =>
            dispatch({
              type: "unfounded",
              note: note.trim() || "Dispute unfounded — returned to ready.",
            })
          }
        >
          Unfounded — pay as approved
        </button>
        <button
          className="danger"
          onClick={() =>
            dispatch({
              type: "standDown",
              note: note.trim() || "Invoice stood down — will not pay.",
            })
          }
        >
          Stand the invoice down
        </button>
      </div>
    </section>
  );
}

function ClosedPad({ inv }: { inv: Invoice }) {
  return (
    <section className="pad">
      <h2>{inv.status === "rejected" ? "Stood down" : "Closed"}</h2>
      <p className="hint">
        This one is off the till. The paper stays for the sitting.
      </p>
      <p className="closed-note">
        {inv.resolutionNote ||
          (inv.status === "paid"
            ? "Remittance succeeded. Nothing left to do."
            : "Will not pay.")}
      </p>
    </section>
  );
}

export default function Pad() {
  const { state } = useDesk();
  const inv = state.invoices.find((i) => i.id === state.selectedId);

  if (!inv) {
    return (
      <section className="pad">
        <h2>The blotter</h2>
        <p className="hint">
          Pick a paper from a tray, or wait — the desk may already be clear.
        </p>
      </section>
    );
  }

  if (inv.status === "disputed") return <DisputePad inv={inv} />;
  if (inv.status === "paid" || inv.status === "rejected")
    return <ClosedPad inv={inv} />;
  return <RemitPad inv={inv} />;
}
