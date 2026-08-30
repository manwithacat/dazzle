import { useMemo, useState } from "react";
import { AUDITOR, TODAY_LABEL, attemptById, todayAttempts } from "./seed";
import type { Layer, View } from "./types";
import { Desk } from "./screens/Desk";
import { ExportPacket } from "./screens/Export";
import { Folio } from "./screens/Folio";
import { Gate } from "./screens/Gate";

export function App() {
  const [view, setView] = useState<View>({ name: "gate" });
  const [cutIds, setCutIds] = useState<Set<string>>(() => new Set());
  const [cutAt, setCutAt] = useState<Record<string, string>>({});

  const desk = todayAttempts();
  const counts = useMemo(() => {
    return {
      all: desk.length,
      failed: desk.filter((a) => a.status === "failed").length,
      pending: desk.filter((a) => a.status === "pending").length,
      succeeded: desk.filter((a) => a.status === "succeeded").length,
      cut: cutIds.size,
    };
  }, [desk, cutIds]);

  function open(attemptId: string, focus: Layer) {
    setView({ name: "folio", attemptId, focus });
  }

  function cut(attemptId: string) {
    const at = new Date().toISOString();
    setCutIds((prev) => new Set(prev).add(attemptId));
    setCutAt((prev) => ({ ...prev, [attemptId]: prev[attemptId] ?? at }));
    setView({ name: "export", attemptId });
  }

  if (view.name === "gate") {
    return <Gate onEnter={() => setView({ name: "desk" })} />;
  }

  const trailAttempt =
    view.name === "folio" || view.name === "export"
      ? attemptById[view.attemptId]
      : undefined;

  return (
    <div className="shell">
      <aside className="rail">
        <button className="brand" onClick={() => setView({ name: "desk" })}>
          <span className="brand-kicker">Meridian</span>
          <span className="brand-title">
            Carbon <em>Desk</em>
          </span>
        </button>
        <div className="rail-who">
          <strong>{AUDITOR.name}</strong>
          {AUDITOR.role} · read-only
        </div>
        <dl>
          <div>
            <dt>On the blotter</dt>
            <dd>{TODAY_LABEL}</dd>
          </div>
          <div>
            <dt>Payment attempts</dt>
            <dd>
              {counts.all} today
              <br />
              {counts.failed} failed · {counts.pending} pending
            </dd>
          </div>
          <div>
            <dt>Cut for the file</dt>
            <dd>
              {counts.cut} of {counts.all}
            </dd>
          </div>
          {trailAttempt && (
            <div>
              <dt>Open trail</dt>
              <dd>
                {trailAttempt.id}
                <br />
                {trailAttempt.invoiceId}
                <br />
                {trailAttempt.tenantId}
              </dd>
            </div>
          )}
        </dl>
        <p className="rail-note">
          Work the ribbon. Open a slip. Read down the carbon. Cut the folio.
          That is the day.
        </p>
      </aside>
      <main className="stage">
        {view.name === "desk" && <Desk cutIds={cutIds} onOpen={open} />}
        {view.name === "folio" && (
          <Folio
            attemptId={view.attemptId}
            focus={view.focus}
            cut={cutIds.has(view.attemptId)}
            onFocus={(focus) =>
              setView({ name: "folio", attemptId: view.attemptId, focus })
            }
            onSwitchAttempt={(id, focus) =>
              setView({ name: "folio", attemptId: id, focus })
            }
            onDesk={() => setView({ name: "desk" })}
            onCut={() => cut(view.attemptId)}
          />
        )}
        {view.name === "export" && (
          <ExportPacket
            attemptId={view.attemptId}
            cutAt={cutAt[view.attemptId] ?? new Date().toISOString()}
            onTrail={() =>
              setView({
                name: "folio",
                attemptId: view.attemptId,
                focus: "attempt",
              })
            }
            onDesk={() => setView({ name: "desk" })}
          />
        )}
      </main>
    </div>
  );
}
