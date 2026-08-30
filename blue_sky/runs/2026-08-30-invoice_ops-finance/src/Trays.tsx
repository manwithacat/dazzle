import { formatDue, money } from "./money";
import { remainder, trayItems, useDesk } from "./state";
import type { Invoice, Tray } from "./types";

const LABELS: Record<Tray, string> = {
  ready: "Ready to remit",
  disputes: "Open disputes",
  cleared: "Stamped this sitting",
};

function Slip({ inv, on }: { inv: Invoice; on: boolean }) {
  const { state, dispatch } = useDesk();
  const left = remainder(inv, state.attempts);
  const due =
    inv.status === "disputed"
      ? "in dispute"
      : inv.status === "paid"
        ? "paid"
        : inv.status === "rejected"
          ? "stood down"
          : formatDue(inv.dueDate);

  return (
    <button
      className={`slip${on ? " on" : ""}`}
      onClick={() => dispatch({ type: "select", id: inv.id })}
    >
      <span className="who">{inv.supplier}</span>
      <span className="amt">
        <span>{inv.invoiceNumber}</span>
        <span>{money(inv.status === "paid" ? inv.amount : left)}</span>
      </span>
      <span className="amt">
        <span>{due}</span>
        <span />
      </span>
    </button>
  );
}

function TrayBlock({ tray }: { tray: Tray }) {
  const { state, dispatch } = useDesk();
  const items = trayItems(state, tray);
  const active = state.tray === tray;

  return (
    <section className="tray">
      <button
        className={`tray-head${active ? " active" : ""}`}
        onClick={() => dispatch({ type: "selectTray", tray })}
      >
        <span className="label">{LABELS[tray]}</span>
        <span className="count">{items.length}</span>
      </button>
      <div className="tray-list">
        {items.length === 0 && (
          <p className="tray-empty">Nothing in this tray.</p>
        )}
        {items.map((inv) => (
          <Slip key={inv.id} inv={inv} on={inv.id === state.selectedId} />
        ))}
      </div>
    </section>
  );
}

export default function Trays() {
  return (
    <aside className="trays">
      <TrayBlock tray="ready" />
      <TrayBlock tray="disputes" />
      <TrayBlock tray="cleared" />
    </aside>
  );
}
