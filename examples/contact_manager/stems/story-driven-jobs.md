# Stem: Story-driven job workspaces (contact_manager)

## Claim

Home and Contacts use favourites queues and directory metrics, not list-only CRM.

## Reconstruct

- User default: home = metrics + favourites queue + sample list.
- Contacts: search + favourites queue + dual-pane list/detail.
- Engagement letters: list dual-opens letter hub **and** parent Contact
  (`EngagementLetter via id | Contact via contact`); display_field=scope_summary
  (document title; party remains a list column); Home open-letters queue
  (draft|sent) + contact hub related letters are **pull queues** with status
  scannable.

## Not this

- Persona lands on a bare entity list when the job is triage, review, or oversight.
- Story `given:` workspace names that disagree with `default_workspace`.
- Engagement letters only as orphan warehouse rows with no Contact hop.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
