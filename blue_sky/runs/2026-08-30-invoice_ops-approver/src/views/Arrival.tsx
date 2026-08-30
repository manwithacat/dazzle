import type { Invoice } from "../types";
import { CHECKER } from "../seed";
import { sumAmount, TODAY, usd } from "../format";

type Props = {
  queue: Invoice[];
  onSit: () => void;
};

export function Arrival({ queue, onSit }: Props) {
  const n = queue.length;
  const exposure = usd(sumAmount(queue));

  return (
    <main className="arrival">
      <div className="arrival-card">
        <div className="kicker">
          {CHECKER.name} · {CHECKER.role} · {CHECKER.desk}
        </div>
        <h1>The work is on the desk.</h1>
        <p className="lede">
          Sit down as Checker. Submitted invoices wait in a single stack,
          largest amount on top. You pick one up before you stamp it.
        </p>
        <div className="meta-row">
          <span>
            Waiting <b>{n}</b>
          </span>
          <span>
            At risk <b>{exposure}</b>
          </span>
          <span>
            Today <b>{TODAY}</b>
          </span>
        </div>
        <button className="sit" onClick={onSit}>
          Sit down as Checker <span>→</span>
        </button>
        <p className="footnote">
          Drafts stay with the submitter. Paid and disputed files have already
          left. You only work what is submitted, and you only stamp after
          opening the record.
        </p>
      </div>
    </main>
  );
}
