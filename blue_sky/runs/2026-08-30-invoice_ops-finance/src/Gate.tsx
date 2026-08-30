import { OPERATOR, TODAY } from "./seed";
import { useDesk, trayItems } from "./state";

export default function Gate() {
  const { state, dispatch } = useDesk();
  const ready = trayItems(state, "ready").length;
  const disputes = trayItems(state, "disputes").length;

  return (
    <main className="gate">
      <section className="gate-card">
        <p className="gate-mark">{OPERATOR.house}</p>
        <h1 className="gate-title">The day’s outlays are waiting.</h1>
        <p className="gate-lede">
          Sit the till. Remit what is approved. Work what is disputed. Nothing
          else belongs on this desk.
        </p>
        <ul className="gate-counts">
          <li>
            <strong>{ready}</strong>
            <span>Ready to remit</span>
          </li>
          <li>
            <strong>{disputes}</strong>
            <span>Open disputes</span>
          </li>
        </ul>
        <button className="sit" onClick={() => dispatch({ type: "sit" })}>
          Sit as Finance Operator
          <em>{OPERATOR.name}</em>
        </button>
        <p className="gate-foot">{TODAY} · one sitting, one desk</p>
      </section>
    </main>
  );
}
