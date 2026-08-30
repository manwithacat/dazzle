# Carbon Desk

A read-only audit desk for tracing a **payment attempt** back to its **invoice** and **tenant**. One object on the blotter: today’s settlement attempts. Invoice and tenant are carbon copies of that attempt, not separate browsers.

Frozen day: **30 August 2026**.

## Run

```bash
npm install
npm run dev
```

Open the URL Vite prints (http://localhost:5273).

## Who you are

There is one person. On the gate, press **Enter as Auditor**.

You are **A. Okada**. Read-only. List permission on Payment Attempt. The only action that leaves a mark is **Cut folio for the file** (an audit export).

## The job that works

Trace a payment attempt back to the invoice record.

1. You land on the **audit review desk** — today’s settlement ribbon.
2. Each slip **triple-opens**:
   - **attempt** id → payment attempt first
   - **invoice** number → the invoice that attempt belongs to
   - **tenant** id → the operating company on whose books it sits
3. The trail always lays down in that order: attempt, then invoice, then tenant.
4. On the invoice sheet, **Settle Approved Invoice** is the procedure as recorded — you witness it, you do not run it.
5. **Cut folio for the file** composes the trail as an audit packet (print or JSON).

Start with **PA-8841** (failed ACH, NSF). The invoice under it is still approved; yesterday’s try (**PA-8820**) is on the invoice, not on today’s desk.

## Screens (four)

1. Gate
2. Desk (today’s payment attempts)
3. Folio (the trail)
4. Export (the cut packet)
