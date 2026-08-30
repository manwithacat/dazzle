# On the Desk

A checker’s afternoon desk. Submitted invoices wait in one stack, largest amount on top. You pick a sheet up, inspect the lines, and stamp it. There is no dashboard and no second list of everything.

## Run

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

Refresh the browser to reset the in-memory seed.

## Who to sit as

There is one person in this slice.

| Button | Person | Job |
| --- | --- | --- |
| **Sit down as Checker** | Mara Chen, Checker | Work the awaiting-approval queue. Open a submitted invoice before approving or rejecting it. |

Stand up from the top-right once you are seated. Work from this session stays on the desk until you refresh.

## What works

- The queue shows only **submitted** invoices, **sorted by amount**, largest first.
- You cannot stamp from the stack. **Pick up** a sheet to open the record.
- The record shows a **status strip**, **supplier**, **amount**, and **line items as related work** (with purchase-order match).
- **Approve** or **Reject**, with a reason. Reject always needs a reason. Approving a file that does not fully match a PO needs an exception note.
- After a stamp, the next largest sheet comes up the stack. When the stack is empty, the desk goes quiet.
- Approved files are **released for settlement**. Payment is not made here.

## Four places, one object

1. Arrival — sit down as Checker
2. The stack — awaiting stamp
3. The invoice record — inspect, then stamp
4. The quiet desk — today’s stamps, including a re-read
