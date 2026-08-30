import { AUDITOR, TODAY_LABEL } from "../seed";

export function Gate({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="gate">
      <article className="gate-card">
        <div className="gate-kicker">Meridian Group</div>
        <h1>
          Carbon <em>Desk</em>
        </h1>
        <p className="gate-sub">Audit review · payment attempts only</p>
        <div className="gate-meta">
          <span>{TODAY_LABEL}</span>
          <span>Session as {AUDITOR.name}</span>
        </div>
        <button className="enter" onClick={onEnter}>
          Enter as Auditor
        </button>
        <p className="gate-foot">
          Read-only reviewer. List permission on Payment Attempt. Invoice and
          tenant open only from a row. Export permitted.
        </p>
      </article>
    </div>
  );
}
