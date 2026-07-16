# Stem: Chrome cue opt-in (sound / haptic)

## Claim

**Sensory chrome cues** (sound, vibration) are **opt-in product policy**, never
Hyperpart defaults. Controllers expose a play/vibrate API; the **page** enables
them via meta tags or host attrs. Failures are silent so emit paths stay cold.

## Reconstruct

| Cue | Enable | API | Off when |
|-----|--------|-----|----------|
| Haptic | `meta[name=dz-haptic][content=on]` | `window.dzHaptic` | unsupported / reduced-motion |
| Sound | `meta[name=dz-sound][content=on]` **or** `[data-dz-cue-sound=on]` on a host | `window.dzCue.play(kind)` | reduced-motion / no AudioContext |

Kinds (sound): `tap` · `info` · `success` · `warning` · `error`.

### Rules

1. **Never default-on** for design-system demos or product shells.
2. **No CDN assets** required — Web Audio blips / Vibration API only.
3. Controllers **call** the API; they do not invent parallel AudioContexts.
4. Unit-level opt-in may still require page enablement (double gate is OK).

## Not this

- Playing a ding on every mutation toast by default.
- Shipping Cloudinary / external ding URLs as a hard dependency.
- Alpine “sound service” stores.

## Expressions

- `controllers/dz-cue.js` (HM) · `dz-utils.js` haptic (Dazzle)
- Toast host: enter cue when stack/unit opts in (decision 0011 phase F)
- Manifest: `[ui] haptic` today; sound meta can follow the same path later
