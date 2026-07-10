# Slider (`slider`)

Native <input type=range> — styled track + thumb, both themes, with a live value readout via a tiny delegated controller.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-stack hm-measure">
  <label class="form-label" for="hm-slider-vol">Volume</label>
  <div class="form-slider-group"><input id="hm-slider-vol" type="range" data-slider class="form-slider" min="0" max="100" step="1" value="70"><span data-range-value class="form-slider-value" aria-hidden="true">70</span></div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The track + thumb are styled for both themes with a focus ring; the native range already announces its value to assistive tech, so the visible readout is <code>aria-hidden</code>. <code>dz-slider.js</code> writes the value into <code>[data-dz-range-value]</code> on input, scoped to each slider's own group so many coexist.

## Controller files

- `controllers/dz-slider.js`
