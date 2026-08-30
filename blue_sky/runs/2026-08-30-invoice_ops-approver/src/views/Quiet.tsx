import type { Invoice } from "../types";
import { statusLabel, sumAmount, usd } from "../format";

type Props = {
  stamped: Invoice[];
  waiting: number;
  onPick: (id: string) => void;
  onStack: () => void;
};

export function Quiet({ stamped, waiting, onPick, onStack }: Props) {
  const released = stamped.filter((i) => i.status === "approved");
  const returned = stamped.filter((i) => i.status === "rejected");

  return (
    <main className="quiet-wrap">
      <div className="kicker">The desk is clear</div>
      <h1>{waiting === 0 ? "Nothing waiting." : "A pause in the work."}</h1>
      <p className="lede">
        {waiting === 0
          ? "Every submitted invoice has been stamped. Approved files are released for settlement — payment is not made here."
          : "You can return to the stack whenever you are ready."}
      </p>
      <div className="meta-row">
        <span>
          Released <b>{released.length}</b>
        </span>
        <span>
          Returned <b>{returned.length}</b>
        </span>
        <span>
          Amount stamped <b>{usd(sumAmount(stamped))}</b>
        </span>
      </div>
      {waiting > 0 && (
        <button className="sit" onClick={onStack}>
          Back to the stack <span>→</span>
        </button>
      )}

      {stamped.length > 0 && (
        <div className="ledger">
          <h2>Today’s stamps</h2>
          {stamped.map((inv) => (
            <button
              key={inv.id}
              className="ledger-row"
              onClick={() => onPick(inv.id)}
            >
              <div>
                <div className="who">{inv.supplier}</div>
                <div className="sub">
                  {inv.invoice_number} · {statusLabel(inv.status)}
                </div>
              </div>
              <div>
                <div className="fig">{usd(inv.amount)}</div>
                <div className="sub" style={{ textAlign: "right" }}>
                  Re-read →
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
