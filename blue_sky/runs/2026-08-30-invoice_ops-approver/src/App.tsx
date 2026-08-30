import { useMemo, useState } from "react";
import { CHECKER, seedInvoices } from "./seed";
import { awaiting, NOW_STAMP, stampedToday } from "./format";
import type { Invoice } from "./types";
import { Arrival } from "./views/Arrival";
import { Stack } from "./views/Stack";
import { Record } from "./views/Record";
import { Quiet } from "./views/Quiet";

type View =
  | { name: "arrival" }
  | { name: "stack" }
  | { name: "record"; id: string }
  | { name: "quiet" };

export function App() {
  const [seated, setSeated] = useState(false);
  const [invoices, setInvoices] = useState<Invoice[]>(seedInvoices);
  const [view, setView] = useState<View>({ name: "arrival" });

  const queue = useMemo(() => awaiting(invoices), [invoices]);
  const today = useMemo(() => stampedToday(invoices), [invoices]);

  function sitDown() {
    setSeated(true);
    setView(queue.length ? { name: "stack" } : { name: "quiet" });
  }

  function standUp() {
    setSeated(false);
    setView({ name: "arrival" });
  }

  function openInvoice(id: string) {
    setView({ name: "record", id });
  }

  function putBack() {
    setView(queue.length ? { name: "stack" } : { name: "quiet" });
  }

  function stamp(
    id: string,
    action: "approved" | "rejected",
    reason: string,
  ): string | null {
    setInvoices((prev) =>
      prev.map((inv) =>
        inv.id === id
          ? {
              ...inv,
              status: action,
              decision: {
                by: CHECKER.name,
                at: NOW_STAMP,
                action,
                reason,
              },
            }
          : inv,
      ),
    );
    const rest = queue.filter((i) => i.id !== id);
    return rest[0]?.id ?? null;
  }

  function afterStamp(nextId: string | null) {
    if (nextId) setView({ name: "record", id: nextId });
    else setView({ name: "quiet" });
  }

  const current =
    view.name === "record"
      ? (invoices.find((i) => i.id === view.id) ?? null)
      : null;

  return (
    <div className="desk">
      <div className="grain" aria-hidden />
      <header className="topbar">
        <div className="mark">On the Desk</div>
        {seated ? (
          <button className="ghost" onClick={standUp}>
            {CHECKER.name} · stand up
          </button>
        ) : (
          <span>Afternoon light · 30 August 2026</span>
        )}
      </header>

      {view.name === "arrival" && <Arrival queue={queue} onSit={sitDown} />}

      {view.name === "stack" && (
        <Stack
          queue={queue}
          stamped={today}
          onPick={openInvoice}
          onQuiet={() => setView({ name: "quiet" })}
        />
      )}

      {view.name === "record" && current && (
        <Record
          key={current.id}
          invoice={current}
          remaining={queue.filter((i) => i.id !== current.id).length}
          onPutBack={putBack}
          onStamp={stamp}
          onAdvance={afterStamp}
        />
      )}

      {view.name === "quiet" && (
        <Quiet
          stamped={today}
          waiting={queue.length}
          onPick={openInvoice}
          onStack={() => setView({ name: "stack" })}
        />
      )}
    </div>
  );
}
