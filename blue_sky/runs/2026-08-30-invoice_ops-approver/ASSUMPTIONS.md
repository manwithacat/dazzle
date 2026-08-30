# Assumptions

Facts invented for this prototype. The brief did not state them.

## Who and where

- The checker is **Mara Chen**. She sits the **afternoon desk** in finance operations on **30 August 2026**.
- Submitters exist only as names on the record: **Priya Nair** (freight and hardware) and **Eli Vargas** (studio and bindery). They do not have a login in this slice.
- The organisation is unnamed. It buys freight, architectural glass, stair hardware, and board-book binding.

## What sits on the desk

- Only invoices with status **submitted** appear in the awaiting-approval queue.
- The queue is sorted by **amount descending**. Largest exposure is the top sheet. That is the default working order, not a filter the checker sets.
- **Draft** invoices stay with the submitter (INV-4422 is in the seed and never appears).
- **Paid**, **partially_paid**, and **disputed** files have already left this desk. They are in the seed so the lifecycle is true; the checker does not browse them.
- Last week’s approved and rejected files (INV-4370, INV-4361) are also off today’s desk.

## The record

- Opening the record is the only way to approve or reject. The stack has no stamp.
- **Line `unit_amount` is the billed amount for that line** (quantity already applied). The lines on a seeded invoice sum to the invoice amount.
- **PO match is the inspection work.** Tags mean:
  - `matched` — agrees with a purchase order
  - `partial` — same PO, amount or quantity differs
  - `unmatched` — no PO on file for that line
  - `not_applicable` — this vendor is not purchased against a PO (standing retainer)
- A file with unmatched lines is still stampable. Reject is the usual move. Approve requires an **exception note**.
- A file with only partial matches also requires an exception note to approve.
- A fully matched file can be approved with no note; the default reason is that the lines agree.

## After the stamp

- **Approve** sets status to `approved` and **releases the invoice for settlement**. That is the human procedure “Settle Approved Invoice”: accounts payable will pay it later. The checker does not pay, schedule, or see a payment screen.
- **Reject** sets status to `rejected` and returns the file to the submitter with the reason.
- After a stamp, the **next largest submitted invoice** is placed in the checker’s hands. The point of the desk is to get through the work, not to return to a list after every decision.
- The checker may put a sheet back unstamped and pick another.

## Session

- Auth is a button. There is no password.
- All data lives in memory. Refresh restores the seed.
- Standing up does not reset stamps from this sitting.
