# Profile card (`profile-card`)

The identity panel: avatar or initials beside name and meta, an optional 3-up stats grid, and a bulleted facts list.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="profile-card-region hm-measure">
  <div class="profile-card">
    <div class="profile-identity">
      <span class="profile-initials" aria-hidden="true">MR</span>
      <div class="profile-text">
        <h3 class="profile-primary">Maya Reyes</h3>
        <p class="profile-secondary">Operations lead · North grid</p>
      </div>
    </div>
    <dl class="profile-stats">
      <div class="profile-stat">
        <dt class="profile-stat-label">Open work orders</dt>
        <dd class="profile-stat-value">7</dd>
      </div>
      <div class="profile-stat">
        <dt class="profile-stat-label">Sites</dt>
        <dd class="profile-stat-value">3</dd>
      </div>
      <div class="profile-stat">
        <dt class="profile-stat-label">On call</dt>
        <dd class="profile-stat-value">—</dd>
      </div>
    </dl>
    <ul class="profile-facts">
      <li class="profile-fact"><span class="profile-fact-bullet" aria-hidden="true">·</span><span class="profile-fact-text">Certified for HV switching</span></li>
      <li class="profile-fact"><span class="profile-fact-bullet" aria-hidden="true">·</span><span class="profile-fact-text">Joined March 2024</span></li>
    </ul>
  </div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The avatar slot prefers an <code>&lt;img class=&quot;dz-profile-avatar&quot;&gt;</code> and falls back to an initials chip; empty stat values render an em-dash (absence is data). Stats are a real <code>&lt;dl&gt;</code>; the facts bullet is decorative markup, hidden from assistive tech.
