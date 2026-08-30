# Daybook

A requester's desk at **Kestrel Press**. Supplier invoices arrive as slips. You raise them, match the lines, send them to the books, and settle what finance already approved.

No warehouse of lists. Three surfaces: the door, the blotter, the slip.

## Run

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`).

## Who you are

There is one person in this slice.

| Button | Role | What they do |
| --- | --- | --- |
| **Mara Ellison** | Requester | Raises supplier invoices, reviews her own slips and their line items, submits them, and attests receipt on approved ones |

Click **Requester**. There is no password.

## What works

- **Raise a slip** from the blotter. Name the supplier (known or new), enter their invoice number, add lines, match each line to a purchase order or mark it as having none, send it to the books.
- **Review own invoices via the record.** Open any slip. The paper is the invoice; the notepad is related work on its line items (match, split, receipt, dispute).
- **Finish a draft.** Helios Bindery is waiting. The notepad offers PO-311.
- **Fix a rejection.** Northline Paper was sent back because the quantity overruns PO-204. Split across open orders, then send it back.
- **Settle an approved invoice.** Calder Freight is approved. Check that the cartons arrived. Release it for payment.
- **Answer a dispute.** Harbor Type billed last year's rate. Stand by the slip or withdraw it to draft.

Statuses on a slip: draft, submitted, approved, partially paid, rejected, disputed, paid.

## How to walk it (five minutes)

1. Open as Mara.
2. Click **Raise a slip**. Pick **Wick & Twine**, number `WT-1102`, describe `Forest buckram, 20 yards`, qty `20`, unit `18.50`, link **PO-502**. Send to the books.
3. Back on the blotter, open **Helios Bindery**. On the notepad, use **PO-311**. Send.
4. Open **Northline Paper Co.** Split the rejected line. Send it back.
5. Open **Calder Freight**. Check the line received. **I received this.**

See `JOURNEYS.md` for stranger paths and `ASSUMPTIONS.md` for invented domain facts.
