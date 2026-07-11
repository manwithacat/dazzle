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
 * falls back to a temporary textarea + execCommand for older hosts.
 */
(function () {
  "use strict";

  function sourceFor(btn) {
    var root = btn.closest("[data-dz-code]");
    if (!root) return null;
    return root.querySelector(".dz-code__source") || root.querySelector("code");
  }

  function writeClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (ok) resolve();
        else reject(new Error("execCommand copy failed"));
      } catch (err) {
        reject(err);
      }
    });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest("[data-dz-code-copy]");
    if (!btn) return;
    var src = sourceFor(btn);
    if (!src) return;
    var text = src.textContent || "";
    writeClipboard(text).then(
      function () {
        btn.setAttribute("data-copied", "");
        btn.blur();
        clearTimeout(btn._dzCodeCopyTimer);
        btn._dzCodeCopyTimer = setTimeout(function () {
          btn.removeAttribute("data-copied");
        }, 1600);
      },
      function () {
        /* leave UI alone on failure — no false "Copied" */
      },
    );
  });
})();
