# Till

A finance operator’s desk for **today’s outlays**. One sitting. One blotter. Two trays of work.

There is no portal, no vendor directory, no report catalog. You sit down, you remit what is approved, you work what is disputed.

## Run

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`).

Refresh the browser to reset the seed. State lives in memory only.

## Who you are

On the gate, press **Sit as Finance Operator**. That is Mara Chen. She is the only person in this slice.

## What works

1. **Settle an approved invoice.** Helion Glass is already on the blotter. Amount, rail, and reference are filled. Press **Record remittance**. The paper is stamped. The next ready invoice comes forward.
2. **Work an open dispute.** Open the **Open disputes** tray. Meridian Steel is waiting with a shop-floor claim. Accept the heat-treat credit (the contended amount is filled), return it to ready, then remit the remainder — or stand a duplicate down.

## How to walk it (two minutes)

1. Sit as Finance Operator.
2. Record remittance on **INV-8841 Helion Glass Works** ($18,440.00, due this sitting). Watch the carmine **PAID** stamp, then Northwind come onto the blotter.
3. Click **Open disputes**.
4. On **INV-8712 Meridian Steel**, press **Accept credit, return to ready**. The $6,400 heat-treat premium comes off. The invoice is now in **Ready to remit**.
5. Record remittance for the new remainder.
6. Back in disputes, stand **INV-8690 Osprey Inks** down as a duplicate.

Optional: on any ready invoice, press **Bank returned this attempt** to log a failed payment, then remit again.

**Stamped this sitting** holds what you closed, plus Bramble Hardware from this morning.

## Screens (two)

- **Gate** — sit down.
- **Desk** — trays, the invoice on the blotter, the action pad.

That is the whole house.
