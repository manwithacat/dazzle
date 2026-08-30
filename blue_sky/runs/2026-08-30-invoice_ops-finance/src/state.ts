import { createContext, useContext } from "react";
import { attempts as seedAttempts, invoices as seedInvoices } from "./seed";
import { isoNow, RETURN_REASON } from "./money";
import type {
  Invoice,
  PaymentAttempt,
  Posting,
  Rail,
  StampKind,
  Tray,
} from "./types";

export type State = {
  seated: boolean;
  invoices: Invoice[];
  attempts: PaymentAttempt[];
  tray: Tray;
  selectedId: string | null;
  posting: Posting | null;
  stamp: { invoiceId: string; kind: StampKind } | null;
  seq: number;
};

export const initialState: State = {
  seated: false,
  invoices: seedInvoices,
  attempts: seedAttempts,
  tray: "ready",
  selectedId: "inv-helion",
  posting: null,
  stamp: null,
  seq: 1,
};

export type Action =
  | { type: "sit" }
  | { type: "leave" }
  | { type: "selectTray"; tray: Tray }
  | { type: "select"; id: string }
  | {
      type: "startRemit";
      amount: number;
      rail: Rail;
      reference: string;
      outcome: "succeeded" | "failed";
    }
  | { type: "finishRemit" }
  | { type: "clearStamp" }
  | { type: "unfounded"; note: string }
  | { type: "credit"; amount: number; note: string }
  | { type: "standDown"; note: string }
  | { type: "advance"; fromId: string };

export function paidCents(inv: Invoice, attempts: PaymentAttempt[]): number {
  return attempts
    .filter((a) => a.invoiceId === inv.id && a.status === "succeeded")
    .reduce((s, a) => s + a.amount, 0);
}

export function creditedCents(inv: Invoice): number {
  return inv.credits.reduce((s, c) => s + c.amount, 0);
}

export function remainder(inv: Invoice, attempts: PaymentAttempt[]): number {
  return Math.max(
    0,
    inv.amount - paidCents(inv, attempts) - creditedCents(inv),
  );
}

export function inTray(
  inv: Invoice,
  tray: Tray,
  attempts: PaymentAttempt[],
): boolean {
  if (tray === "ready") {
    return (
      (inv.status === "approved" || inv.status === "partially_paid") &&
      remainder(inv, attempts) > 0
    );
  }
  if (tray === "disputes") return inv.status === "disputed";
  return inv.status === "paid" || inv.status === "rejected";
}

export function trayItems(state: State, tray: Tray = state.tray): Invoice[] {
  const items = state.invoices.filter((inv) =>
    inTray(inv, tray, state.attempts),
  );
  if (tray === "cleared") {
    return [...items].sort((a, b) =>
      (b.closedAt ?? "").localeCompare(a.closedAt ?? ""),
    );
  }
  return items;
}

function nid(state: State, prefix: string): { id: string; seq: number } {
  return { id: `${prefix}-${state.seq}`, seq: state.seq + 1 };
}

function settleStatus(
  inv: Invoice,
  attempts: PaymentAttempt[],
): Invoice["status"] {
  const left = remainder(inv, attempts);
  const paid = paidCents(inv, attempts);
  const credited = creditedCents(inv);
  if (left <= 0) return "paid";
  if (paid > 0 || credited > 0) return "partially_paid";
  return "approved";
}

function pickInTray(
  state: State,
  tray: Tray,
  prefer?: string | null,
): string | null {
  const items = trayItems({ ...state, tray }, tray);
  if (prefer && items.some((i) => i.id === prefer)) return prefer;
  return items[0]?.id ?? null;
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "sit":
      return { ...state, seated: true };
    case "leave":
      return { ...state, seated: false };
    case "selectTray": {
      const selectedId = pickInTray(state, action.tray, state.selectedId);
      return { ...state, tray: action.tray, selectedId, stamp: null };
    }
    case "select": {
      const inv = state.invoices.find((i) => i.id === action.id);
      if (!inv) return { ...state, selectedId: action.id, stamp: null };
      const tray: Tray = inTray(inv, "ready", state.attempts)
        ? "ready"
        : inTray(inv, "disputes", state.attempts)
          ? "disputes"
          : "cleared";
      return { ...state, selectedId: action.id, tray, stamp: null };
    }
    case "startRemit": {
      if (!state.selectedId || state.posting) return state;
      const inv = state.invoices.find((i) => i.id === state.selectedId);
      if (!inv) return state;
      const left = remainder(inv, state.attempts);
      if (action.amount <= 0 || action.amount > left) return state;
      const { id, seq } = nid(state, "pay");
      const attempt: PaymentAttempt = {
        id,
        invoiceId: inv.id,
        amount: action.amount,
        rail: action.rail,
        reference: action.reference,
        status: "pending",
        at: isoNow(),
        returnReason:
          action.outcome === "failed" ? RETURN_REASON[action.rail] : undefined,
      };
      return {
        ...state,
        seq,
        attempts: [...state.attempts, attempt],
        posting: {
          attemptId: id,
          invoiceId: inv.id,
          outcome: action.outcome,
          returnReason: attempt.returnReason,
        },
        stamp: null,
      };
    }
    case "finishRemit": {
      if (!state.posting) return state;
      const { attemptId, invoiceId, outcome, returnReason } = state.posting;
      const attempts = state.attempts.map((a) =>
        a.id === attemptId
          ? {
              ...a,
              status: outcome,
              returnReason: outcome === "failed" ? returnReason : undefined,
            }
          : a,
      );
      const invoices = state.invoices.map((inv) => {
        if (inv.id !== invoiceId) return inv;
        if (outcome !== "succeeded") return inv;
        const next = { ...inv };
        const status = settleStatus(next, attempts);
        next.status = status;
        if (status === "paid") next.closedAt = isoNow();
        return next;
      });
      const closed = invoices.find((i) => i.id === invoiceId);
      const kind: StampKind =
        outcome === "failed"
          ? "returned"
          : closed && remainder(closed, attempts) <= 0
            ? "paid"
            : "partial";
      return {
        ...state,
        attempts,
        invoices,
        posting: null,
        stamp: { invoiceId, kind },
      };
    }
    case "clearStamp":
      return { ...state, stamp: null };
    case "unfounded": {
      if (!state.selectedId) return state;
      const id = state.selectedId;
      const invoices = state.invoices.map((inv) => {
        if (inv.id !== id) return inv;
        const next: Invoice = {
          ...inv,
          status: settleStatus({ ...inv, status: "approved" }, state.attempts),
          resolutionNote:
            action.note || "Dispute unfounded — returned to ready.",
          dispute: undefined,
        };
        return next;
      });
      const nextState: State = {
        ...state,
        invoices,
        stamp: { invoiceId: id, kind: "unfounded" },
        tray: "ready",
      };
      nextState.selectedId = id;
      return nextState;
    }
    case "credit": {
      if (!state.selectedId) return state;
      const id = state.selectedId;
      const inv = state.invoices.find((i) => i.id === id);
      if (!inv) return state;
      const left = remainder(inv, state.attempts);
      const amount = Math.min(action.amount, left);
      if (amount <= 0) return state;
      const { id: cid, seq } = nid(state, "cr");
      const invoices = state.invoices.map((row) => {
        if (row.id !== id) return row;
        const next: Invoice = {
          ...row,
          credits: [
            ...row.credits,
            {
              id: cid,
              amount,
              note: action.note || "Credit accepted against dispute.",
              at: isoNow(),
            },
          ],
          resolutionNote: action.note || "Credit accepted against dispute.",
          dispute: undefined,
        };
        next.status = settleStatus(next, state.attempts);
        if (next.status === "paid") next.closedAt = isoNow();
        return next;
      });
      const credited = invoices.find((i) => i.id === id)!;
      const paidOff = credited.status === "paid";
      return {
        ...state,
        seq,
        invoices,
        stamp: { invoiceId: id, kind: paidOff ? "paid" : "credited" },
        tray: paidOff ? state.tray : "ready",
        selectedId: id,
      };
    }
    case "standDown": {
      if (!state.selectedId) return state;
      const id = state.selectedId;
      const invoices = state.invoices.map((inv) =>
        inv.id === id
          ? {
              ...inv,
              status: "rejected" as const,
              closedAt: isoNow(),
              resolutionNote:
                action.note || "Invoice stood down — will not pay.",
              dispute: undefined,
            }
          : inv,
      );
      return {
        ...state,
        invoices,
        stamp: { invoiceId: id, kind: "refused" },
        selectedId: id,
      };
    }
    case "advance": {
      if (state.selectedId !== action.fromId) return { ...state, stamp: null };
      const current = state.invoices.find((i) => i.id === action.fromId);
      const stillHere = current && inTray(current, state.tray, state.attempts);
      if (stillHere) return { ...state, stamp: null };
      return {
        ...state,
        stamp: null,
        selectedId: pickInTray(state, state.tray, null),
      };
    }
    default:
      return state;
  }
}

export const DeskContext = createContext<{
  state: State;
  dispatch: (a: Action) => void;
} | null>(null);

export function useDesk() {
  const ctx = useContext(DeskContext);
  if (!ctx) throw new Error("DeskContext missing");
  return ctx;
}
