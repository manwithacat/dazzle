import type { Invoice } from "../types";
import { riskLine, riskOf, sumAmount, usd } from "../format";

type Props = {
  queue: Invoice[];
  stamped: Invoice[];
  onPick: (id: string) => void;
  onQuiet: () => void;
};

export function Stack({ queue, stamped, onPick, onQuiet }: Props) {
  if (queue.length === 0) {
    return (
      <main className="stage">
        <div className="stage-head">
          <div>
            <h1>Awaiting stamp</h1>
            <p>The stack is empty. Nothing submitted is waiting.</p>
          </div>
        </div>
        <button className="sit" onClick={onQuiet}>
          See the quiet desk <span>→</span>
        </button>
      </main>
    );
  }

  return (
    <main className="stage">
      <div className="stage-head">
        <div>
          <h1>Awaiting stamp</h1>
          <p>Largest amount first. Pick a sheet up to inspect it.</p>
          {stamped.length > 0 && (
            <div>
              <button className="ghost" onClick={onQuiet}>
                Today’s stamps →
              </button>
            </div>
          )}
        </div>
        <div className="tally">
          <div className="fig">{usd(sumAmount(queue))}</div>
          <small>
            {queue.length} waiting
            {stamped.length ? ` · ${stamped.length} stamped today` : ""}
          </small>
        </div>
      </div>

      <div className="stack">
        {queue.map((inv, i) => {
          const risk = riskOf(inv);
          return (
            <button
              key={inv.id}
              className={i === 0 ? "sheet top" : "sheet"}
              onClick={() => onPick(inv.id)}
            >
              <div className="supplier">{inv.supplier}</div>
              <div className="amt">{usd(inv.amount)}</div>
              <div className="sub">
                {i === 0 && <span className="pill top">On top</span>}
                <span className={`pill ${risk}`}>
                  {risk === "halt"
                    ? "Unmatched lines"
                    : risk === "watch"
                      ? "Partial match"
                      : "Matched"}
                </span>
                {inv.invoice_number} · {riskLine(inv)}
              </div>
              <div className="pick">
                {i === 0 ? "Pick up the top sheet →" : "Pick up →"}
              </div>
            </button>
          );
        })}
      </div>
    </main>
  );
}
