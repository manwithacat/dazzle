# Activity feed (`activity-feed`)

Who-did-what rows on a dotted spine — actor, time, and a message bubble.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-measure-lg">
  <ul class="activity-feed">
    <li class="activity-row">
      <span class="activity-dot"><svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="activity-row-inner">
        <div class="activity-time">09:41</div>
        <div class="activity-bubble"><span class="activity-actor">Ada</span> approved the refund.</div>
      </div>
    </li>
    <li class="activity-row">
      <span class="activity-dot"><svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="activity-row-inner">
        <div class="activity-time">09:12</div>
        <div class="activity-bubble"><span class="activity-actor">System</span> flagged the account for review.</div>
      </div>
    </li>
  </ul>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Rows are server-rendered newest-first; an empty feed renders <code>dz-activity-empty</code>. The dot column and bubble keep alignment without a grid — the row is the flex unit.
