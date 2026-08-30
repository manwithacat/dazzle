import { useReducer } from "react";
import Desk from "./Desk";
import Gate from "./Gate";
import { DeskContext, initialState, reducer } from "./state";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);

  return (
    <DeskContext.Provider value={{ state, dispatch }}>
      {state.seated ? <Desk /> : <Gate />}
    </DeskContext.Provider>
  );
}
