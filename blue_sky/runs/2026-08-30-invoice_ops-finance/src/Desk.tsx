import { useEffect } from "react";
import Pad from "./Pads";
import Paper from "./Paper";
import { OPERATOR, TODAY } from "./seed";
import { trayItems, useDesk } from "./state";
import Trays from "./Trays";

export default function Desk() {
  const { state, dispatch } = useDesk();
  const ready = trayItems(state, "ready").length;
  const disputes = trayItems(state, "disputes").length;

  useEffect(() => {
    if (!state.posting) return;
    const t = window.setTimeout(() => dispatch({ type: "finishRemit" }), 720);
    return () => window.clearTimeout(t);
  }, [state.posting, dispatch]);

  useEffect(() => {
    if (!state.stamp) return;
    const leaves =
      state.stamp.kind === "paid" || state.stamp.kind === "refused";
    if (!leaves) return;
    const fromId = state.stamp.invoiceId;
    const t = window.setTimeout(
      () => dispatch({ type: "advance", fromId }),
      1200,
    );
    return () => window.clearTimeout(t);
  }, [state.stamp, dispatch]);

  return (
    <div className="desk">
      <header className="mast">
        <h1 className="wordmark">Till</h1>
        <div className="mast-meta">
          <span>{TODAY}</span>
          <span>
            {ready} to remit · {disputes} in dispute
          </span>
          <strong>
            {OPERATOR.name} · {OPERATOR.role}
          </strong>
          <button className="leave" onClick={() => dispatch({ type: "leave" })}>
            Leave the desk
          </button>
        </div>
      </header>
      <div className="body">
        <Trays />
        <main className="blotter">
          <Paper />
        </main>
        <Pad key={state.selectedId ?? "empty"} />
      </div>
    </div>
  );
}
