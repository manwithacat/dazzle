# Project Tracker

A project management app demonstrating Dazzle's UX component expansion (Phases 1-4).

## Components Exercised

| Component | Where Used |
|-----------|-----------|
| Rich text (Quill) | Project/task descriptions, comments |
| Date picker (Flatpickr) | Due dates, milestone dates |
| Tags (Tom Select) | Task labels |
| Combobox (Tom Select) | Assignee, project, milestone selection |
| Toast notifications | Save confirmations |
| Server-loaded modal | New task from any context |
| Breadcrumbs | Project → Milestone → Task navigation |
| Accordion | Task detail sections |
| Skeleton loaders | Dashboard metrics |
| Kanban board | Task status board |
| Timeline | Milestone timeline |
| Status cards | Milestone overview |

## Running

```bash
cd examples/project_tracker
dazzle serve --local
```

- UI: http://localhost:3000
- API: http://localhost:8000/docs
