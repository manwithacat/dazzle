/**
 * Signing Pad Island — captures handwritten signatures for `signable: true`
 * entities (#1283 phase 4).
 *
 * Mount convention follows src/dazzle/page/runtime/static/js/dz-islands.js:
 * the host page emits a `<div data-island="signing_pad"
 * data-island-src="/static/js/islands/signing-pad.js"
 * data-island-props='{"entity": ..., "record": ..., "token": ...,
 *                     "signatoryName": ..., "apiBase": "/api/sign"}'>`
 * and dz-islands.js calls mount({ el, props }) on this module's export.
 *
 * Network contract — POST to `${apiBase}/${entity}/${record}` with JSON
 * body { token, signatory_name, signature_png_b64, decline?,
 * decline_reason? }. Matches the auto-mounted signing routes shipped in
 * v0.79.9 (phase 3d).
 *
 * Security: all DOM content is built via createElement/textContent. No
 * innerHTML calls with dynamic data — the only mutation that touches
 * `firstChild`/`removeChild` empties the container before re-rendering
 * with safe DOM nodes.
 */

export function mount({ el, props }) {
  const {
    entity,
    record,
    token,
    signatoryName = "Signer",
    entityName = entity,
    apiBase = "/api/sign",
  } = props || {};

  if (!entity || !record || !token) {
    showFatal(el, "Signing pad: missing entity, record, or token in props.");
    return function noop() {};
  }

  const container = document.createElement("div");
  container.className = "dz-signing-pad space-y-6";

  // Authority declaration
  const declSection = document.createElement("div");
  declSection.className = "form-control";

  const declLabel = document.createElement("label");
  declLabel.className = "label cursor-pointer gap-3 justify-start";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "checkbox checkbox-primary";

  const declText = document.createElement("span");
  declText.className = "label-text";
  declText.textContent =
    "I confirm that I am authorised to sign on behalf of " +
    entityName +
    " and agree to the terms set out above.";

  declLabel.appendChild(checkbox);
  declLabel.appendChild(declText);
  declSection.appendChild(declLabel);
  container.appendChild(declSection);

  // Signature canvas area
  const sigSection = document.createElement("div");
  sigSection.className = "border rounded-lg p-4 bg-white";

  const sigLabel = document.createElement("p");
  sigLabel.className = "text-sm font-medium mb-2";
  sigLabel.textContent = "Please sign below:";
  sigSection.appendChild(sigLabel);

  const canvasWrapper = document.createElement("div");
  canvasWrapper.className = "border border-base-300 rounded bg-white relative";
  canvasWrapper.style.touchAction = "none";

  const canvas = document.createElement("canvas");
  canvas.width = 600;
  canvas.height = 200;
  canvas.style.width = "100%";
  canvas.style.height = "200px";
  canvas.style.display = "block";
  canvasWrapper.appendChild(canvas);
  sigSection.appendChild(canvasWrapper);

  const btnRow = document.createElement("div");
  btnRow.className = "flex gap-2 mt-2";

  const clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "btn btn-sm btn-ghost";
  clearBtn.textContent = "Clear";

  const undoBtn = document.createElement("button");
  undoBtn.type = "button";
  undoBtn.className = "btn btn-sm btn-ghost";
  undoBtn.textContent = "Undo";

  btnRow.appendChild(clearBtn);
  btnRow.appendChild(undoBtn);
  sigSection.appendChild(btnRow);
  container.appendChild(sigSection);

  // Signer name display
  const nameInfo = document.createElement("p");
  nameInfo.className = "text-sm text-base-content/60";
  nameInfo.textContent = "Signing as: " + signatoryName;
  container.appendChild(nameInfo);

  // Action buttons
  const actionRow = document.createElement("div");
  actionRow.className = "flex gap-3 justify-end mt-4";

  const declineBtn = document.createElement("button");
  declineBtn.type = "button";
  declineBtn.className = "btn btn-ghost btn-sm";
  declineBtn.textContent = "Decline to Sign";

  const submitBtn = document.createElement("button");
  submitBtn.type = "button";
  submitBtn.className = "btn btn-primary";
  submitBtn.textContent = "Sign & Submit";
  submitBtn.disabled = true;

  actionRow.appendChild(declineBtn);
  actionRow.appendChild(submitBtn);
  container.appendChild(actionRow);

  const statusDiv = document.createElement("div");
  statusDiv.className = "hidden";
  container.appendChild(statusDiv);

  while (el.firstChild) el.removeChild(el.firstChild);
  el.appendChild(container);

  // Initialise SignaturePad — loaded via <script> tag on the host page.
  // If the global isn't present, surface the issue clearly instead of
  // silently breaking the canvas.
  if (typeof window.SignaturePad !== "function") {
    showFatal(
      el,
      "SignaturePad library not loaded. The host page must include " +
        "https://cdn.jsdelivr.net/npm/signature_pad@5/dist/signature_pad.umd.min.js " +
        "before this Island can mount.",
    );
    return function noop() {};
  }

  const signaturePad = new window.SignaturePad(canvas, {
    backgroundColor: "rgb(255, 255, 255)",
    penColor: "rgb(0, 0, 80)",
    minWidth: 1,
    maxWidth: 3,
  });

  function resizeCanvas() {
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);
    signaturePad.clear();
  }
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);

  function updateSubmitState() {
    submitBtn.disabled = signaturePad.isEmpty() || !checkbox.checked;
  }

  signaturePad.addEventListener("endStroke", updateSubmitState);
  checkbox.addEventListener("change", updateSubmitState);

  clearBtn.addEventListener("click", function () {
    signaturePad.clear();
    updateSubmitState();
  });

  undoBtn.addEventListener("click", function () {
    const data = signaturePad.toData();
    if (data.length > 0) {
      data.pop();
      signaturePad.fromData(data);
    }
    updateSubmitState();
  });

  const endpoint =
    apiBase +
    "/" +
    encodeURIComponent(entity) +
    "/" +
    encodeURIComponent(record);

  submitBtn.addEventListener("click", async function () {
    if (signaturePad.isEmpty() || !checkbox.checked) return;

    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting...";
    declineBtn.disabled = true;

    try {
      // Convert signature to PNG → base64 for JSON transport.
      const dataUrl = signaturePad.toDataURL("image/png");
      const sigB64 = dataUrl.split(",", 2)[1] || "";

      const result = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          token: token,
          signatory_name: signatoryName,
          signature_png_b64: sigB64,
        }),
      });

      if (result.ok) {
        // The framework returns the signed PDF inline. Trigger a download.
        const blob = await result.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = entity + "-" + record + ".pdf";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        replaceWithMessage(
          el,
          "alert-success",
          "Successfully Signed",
          "Your signed document is downloading. A digitally certified copy is " +
            "stored securely. You may close this page.",
        );
      } else {
        let detail = "Signing failed. Please try again.";
        try {
          const json = await result.json();
          detail = json.detail || json.error || detail;
        } catch (_) {}
        showError(statusDiv, detail);
        submitBtn.disabled = false;
        submitBtn.textContent = "Sign & Submit";
        declineBtn.disabled = false;
      }
    } catch (_err) {
      showError(
        statusDiv,
        "Network error. Please check your connection and try again.",
      );
      submitBtn.disabled = false;
      submitBtn.textContent = "Sign & Submit";
      declineBtn.disabled = false;
    }
  });

  declineBtn.addEventListener("click", async function () {
    if (!window.confirm("Are you sure you want to decline this document?")) {
      return;
    }
    declineBtn.disabled = true;
    submitBtn.disabled = true;

    try {
      const result = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: token, decline: true }),
      });
      if (result.ok) {
        replaceWithMessage(
          el,
          "alert-warning",
          "Document Declined",
          "You have declined this document. The originator will be notified. " +
            "You may close this page.",
        );
      } else {
        let detail = "Failed to decline.";
        try {
          const json = await result.json();
          detail = json.detail || json.error || detail;
        } catch (_) {}
        showError(statusDiv, detail);
        declineBtn.disabled = false;
        submitBtn.disabled = false;
      }
    } catch (_err) {
      showError(statusDiv, "Network error. Please try again.");
      declineBtn.disabled = false;
      submitBtn.disabled = false;
    }
  });

  return function unmount() {
    window.removeEventListener("resize", resizeCanvas);
    if (typeof signaturePad.off === "function") signaturePad.off();
  };
}

function replaceWithMessage(el, alertClass, title, body) {
  while (el.firstChild) el.removeChild(el.firstChild);

  const div = document.createElement("div");
  div.className = "alert " + alertClass + " shadow-lg";

  const icon = document.createElement("span");
  icon.textContent = alertClass.includes("success") ? "✓" : "⚠";
  icon.className = "text-2xl";

  const text = document.createElement("div");
  const h3 = document.createElement("h3");
  h3.className = "font-bold";
  h3.textContent = title;
  const p = document.createElement("p");
  p.className = "text-sm";
  p.textContent = body;
  text.appendChild(h3);
  text.appendChild(p);

  div.appendChild(icon);
  div.appendChild(text);
  el.appendChild(div);
}

function showError(statusDiv, message) {
  statusDiv.className = "alert alert-error mt-4";
  statusDiv.textContent = message;
}

function showFatal(el, message) {
  while (el.firstChild) el.removeChild(el.firstChild);
  const div = document.createElement("div");
  div.className = "alert alert-error shadow-lg";
  div.textContent = message;
  el.appendChild(div);
}
