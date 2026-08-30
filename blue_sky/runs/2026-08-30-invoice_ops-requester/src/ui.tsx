import { useEffect, useState } from "react";
import { matchLabel, stampLabel } from "./domain";
import { parseMoney } from "./money";
import type { InvoiceStatus, PoMatch } from "./types";

export function Stamp({ status }: { status: InvoiceStatus }) {
  return <span className={`stamp ${status}`}>{stampLabel(status)}</span>;
}

export function MatchChip({ match }: { match: PoMatch }) {
  return <span className={`chip ${match}`}>{matchLabel(match)}</span>;
}

export function MoneyInput({
  cents,
  onChange,
  disabled,
  className,
}: {
  cents: number;
  onChange: (cents: number) => void;
  disabled?: boolean;
  className?: string;
}) {
  const [text, setText] = useState(() => (cents / 100).toFixed(2));
  useEffect(() => {
    setText((cents / 100).toFixed(2));
  }, [cents]);
  return (
    <input
      className={className}
      inputMode="decimal"
      disabled={disabled}
      value={text}
      aria-label="Unit amount"
      onChange={(e) => setText(e.target.value)}
      onBlur={() => onChange(parseMoney(text))}
    />
  );
}
