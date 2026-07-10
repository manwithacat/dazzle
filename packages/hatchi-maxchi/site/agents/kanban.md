# Kanban (`kanban`)

Status columns of cards — the flow view. Columns show a count; overflowing boards offer a server-rendered Load-all.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="kanban-board">
  <div class="kanban-column">
    <div class="kanban-column-head"><span class="badge" data-tone="neutral">Open</span><span class="kanban-column-count">2</span></div>
    <div class="kanban-stack">
      <div class="kanban-card">
        <div class="kanban-card-body">
          <h4 class="kanban-card-title">Refund request — Acme</h4>
          <p class="kanban-card-field">£1,250 · assigned to Ada</p>
          <p class="kanban-card-attn" data-attn="critical">SLA breaches at 16:00</p>
        </div>
      </div>
      <div class="kanban-card">
        <div class="kanban-card-body">
          <h4 class="kanban-card-title">KYC review — Globex</h4>
          <p class="kanban-card-field">due tomorrow</p>
        </div>
      </div>
    </div>
  </div>
  <div class="kanban-column">
    <div class="kanban-column-head"><span class="badge" data-tone="info">In progress</span><span class="kanban-column-count">1</span></div>
    <div class="kanban-stack">
      <div class="kanban-card">
        <div class="kanban-card-body">
          <h4 class="kanban-card-title">Chargeback — Initech</h4>
          <p class="kanban-card-field">evidence uploaded</p>
        </div>
      </div>
    </div>
  </div>
  <div class="kanban-column">
    <div class="kanban-column-head"><span class="badge" data-tone="success"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>Done</span><span class="kanban-column-count">0</span></div>
    <div class="kanban-stack">
      <p class="kanban-empty">Nothing here yet.</p>
    </div>
  </div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Cards are SERVER-rendered — a drag-and-drop extension is a future controller on these seams, not a client state graph. Attention text carries <code>data-dz-attn=&quot;&lt;level&gt;&quot;</code> (critical/warning/notice — the same attn contract the timeline's bullets and the queue's rows use). An overflowing board renders a <code>dz-kanban-load-all</code> button whose <code>hx-get</code> re-fetches the region at full page size.
