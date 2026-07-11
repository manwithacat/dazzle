/* HYPERPART: code */
/*
 * dz-code — copy control for the code Hyperpart.
 *
 * Contract (mirrors contracts/code.py DOM_CONTRACT):
 *   [data-dz-code] root
 *   [data-dz-code-copy] optional button — copies .dz-code__source textContent
 *   data-copied on the button while feedback is showing
 *
 * Document-delegated; no per-instance wiring. Clipboard API preferred;
 * falls back to a temporary textarea + execCommand when writeText rejects
 * (insecure origins, permission denials) so the control never fails silently.
 */
(function () {
  "use strict";

  function sourceFor(btn) {
    var root = btn.closest("[data-dz-code]");
    if (!root) return null;
    // Prefer the dedicated source node; never use a bare "code" match that
    // could collide with the unprefixed root class name `.code` in gallery CSS.
    return (
      root.querySelector(".dz-code__source") ||
      root.querySelector("[class$='code__source']") ||
      root.querySelector("pre code")
    );
  }

  function execCommandCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_err) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  function writeClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text).catch(function () {
        // Permission / insecure-context: fall through to legacy path.
        if (!execCommandCopy(text)) {
          return Promise.reject(new Error("copy failed"));
        }
      });
    }
    return execCommandCopy(text)
      ? Promise.resolve()
      : Promise.reject(new Error("copy failed"));
  }

  function flashCopied(btn) {
    btn.setAttribute("data-copied", "");
    try {
      btn.blur();
    } catch (_e) {
      /* ignore */
    }
    clearTimeout(btn._dzCodeCopyTimer);
    btn._dzCodeCopyTimer = setTimeout(function () {
      btn.removeAttribute("data-copied");
    }, 1600);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest("[data-dz-code-copy]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var src = sourceFor(btn);
    if (!src) return;
    var text = src.textContent || "";
    writeClipboard(text).then(
      function () {
        flashCopied(btn);
      },
      function () {
        /* both paths failed — leave UI alone */
      },
    );
  });
})();
