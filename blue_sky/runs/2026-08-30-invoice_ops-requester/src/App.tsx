import { useMemo, useState } from "react";
import { Door, Desk, Folio } from "./screens";
import { PERSON, POS, SUPPLIERS, seedInvoices } from "./seed";
import { refreshInvoice, splitLine } from "./domain";
import { isoDate, uid } from "./money";
import type { Invoice, Supplier, Toast } from "./types";

type View =
  { screen: "door" } | { screen: "desk" } | { screen: "folio"; id: string };

function hydrateSupplier(
  invoice: Invoice,
  suppliers: Supplier[],
): { invoice: Invoice; suppliers: Supplier[] } {
  if (!invoice.supplierId.startsWith("new:")) return { invoice, suppliers };
  const name = invoice.supplierId.slice(4).trim();
  if (!name) return { invoice, suppliers };
  const existing = suppliers.find(
    (s) => s.name.toLowerCase() === name.toLowerCase(),
  );
  if (existing)
    return { invoice: { ...invoice, supplierId: existing.id }, suppliers };
  const id = `sup-${name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, 28)}`;
  const next: Supplier = {
    id,
    name,
    city: "",
    typical: "Added from the desk",
  };
  return {
    invoice: { ...invoice, supplierId: id },
    suppliers: [...suppliers, next],
  };
}

export function App() {
  const [view, setView] = useState<View>({ screen: "door" });
  const [suppliers, setSuppliers] = useState<Supplier[]>(SUPPLIERS);
  const [invoices, setInvoices] = useState<Invoice[]>(() =>
    seedInvoices().map((inv) => refreshInvoice(inv, POS)),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = (text: string) => {
    const id = uid("toast");
    setToasts((t) => [...t, { id, text }]);
    window.setTimeout(
      () => setToasts((t) => t.filter((x) => x.id !== id)),
      3200,
    );
  };

  const patch = (id: string, mut: (inv: Invoice) => Invoice) => {
    setInvoices((prev) =>
      prev.map((inv) => (inv.id === id ? refreshInvoice(mut(inv), POS) : inv)),
    );
  };

  const current = useMemo(
    () =>
      view.screen === "folio"
        ? invoices.find((i) => i.id === view.id)
        : undefined,
    [view, invoices],
  );

  const raise = () => {
    const id = uid("inv");
    const blank: Invoice = {
      id,
      invoiceNumber: "",
      supplierId: "",
      amountCents: 0,
      status: "draft",
      issuedOn: isoDate(),
      lines: [
        {
          id: uid("ln"),
          description: "",
          quantity: 1,
          unitAmountCents: 0,
          poId: null,
          poMatch: "unmatched",
          received: false,
        },
      ],
      note: "",
      rejectedReason: null,
      disputeNote: null,
      settledAt: null,
      settledBy: null,
      settlementNote: null,
      paidCents: 0,
      createdAt: new Date().toISOString(),
    };
    setInvoices((prev) => [blank, ...prev]);
    setView({ screen: "folio", id });
  };

  if (view.screen === "door") {
    return (
      <>
        <div className="grain" />
        <Door onEnter={() => setView({ screen: "desk" })} />
      </>
    );
  }

  if (view.screen === "desk") {
    return (
      <>
        <div className="grain" />
        <Desk
          person={PERSON}
          invoices={invoices}
          suppliers={suppliers}
          onRaise={raise}
          onOpen={(id) => setView({ screen: "folio", id })}
          onLeave={() => setView({ screen: "door" })}
        />
        <Toasts toasts={toasts} />
      </>
    );
  }

  if (!current) {
    return (
      <>
        <div className="grain" />
        <Desk
          person={PERSON}
          invoices={invoices}
          suppliers={suppliers}
          onRaise={raise}
          onOpen={(id) => setView({ screen: "folio", id })}
          onLeave={() => setView({ screen: "door" })}
        />
        <Toasts toasts={toasts} />
      </>
    );
  }

  return (
    <>
      <div className="grain" />
      <Folio
        person={PERSON}
        invoice={current}
        suppliers={suppliers}
        pos={POS}
        onChange={(next) => patch(current.id, () => next)}
        onBack={() => setView({ screen: "desk" })}
        onSubmit={() => {
          const { invoice, suppliers: nextSuppliers } = hydrateSupplier(
            current,
            suppliers,
          );
          setSuppliers(nextSuppliers);
          patch(current.id, () => ({
            ...invoice,
            supplierId: invoice.supplierId,
            status: "submitted",
            rejectedReason: null,
            disputeNote: null,
          }));
          toast("On its way to the books.");
        }}
        onSettle={(note) => {
          patch(current.id, (inv) => ({
            ...inv,
            settledAt: new Date().toISOString(),
            settledBy: PERSON.name,
            settlementNote: note.trim() || "Received in good order.",
          }));
          toast("Released for payment.");
        }}
        onStandBy={(note) => {
          patch(current.id, (inv) => ({
            ...inv,
            status: "submitted",
            note: [
              inv.note,
              note.trim()
                ? `Standing by: ${note.trim()}`
                : "Standing by the slip.",
            ]
              .filter(Boolean)
              .join(" "),
            disputeNote: inv.disputeNote,
          }));
          toast("Sent back to the books with your note.");
        }}
        onWithdraw={() => {
          patch(current.id, (inv) => ({ ...inv, status: "draft" }));
          toast("Withdrawn. It is a draft again.");
        }}
        onSplit={(lineId) => {
          patch(current.id, (inv) => splitLine(inv, lineId, POS));
          toast("Split across the open orders.");
        }}
      />
      <Toasts toasts={toasts} />
    </>
  );
}

function Toasts({ toasts }: { toasts: Toast[] }) {
  if (toasts.length === 0) return null;
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div className="toast" key={t.id}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
