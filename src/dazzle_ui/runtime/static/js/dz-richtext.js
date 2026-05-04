/**
 * dz-richtext.js — Dazzle-native rich-text editor (#977 cycle 1).
 *
 * Spec: dev_docs/2026-05-04-dz-richtext-spec.md
 *
 * Cycle 1 scope: bold, italic, underline, emit pass, a11y baseline.
 * Cycles 2–5 add lists/headings/links, paste sanitisation, undo/redo,
 * server allowlist parity, DSL knobs.
 *
 * Coexists with the Quill bridge (registered as "richtext"); this
 * editor is registered as "richtext-native" until cycle 4 flips the
 * macro and the Quill bridge is deleted.
 *
 * Security model: client-side schema enforcement is a UX layer. The
 * security boundary is `RichTextField` on the server (bleach with the
 * IR-sourced allowlist; cycle 4). HTML inserted into the editor goes
 * through DOMParser + a closed-tag walker (no innerHTML writes).
 */
(function () {
  var bridge = window.dz && window.dz.bridge;
  if (!bridge) return;

  var COMMANDS = {
    bold: { tag: "strong", type: "inline", key: "b" },
    italic: { tag: "em", type: "inline", key: "i" },
    underline: { tag: "u", type: "inline", key: "u" },
  };

  // Closed inline-tag allowlist used by cycle 1's emit pass.
  // Cycle 3 expands this and moves the source of truth into the IR.
  var INLINE_ALLOW = { STRONG: 1, EM: 1, U: 1, BR: 1 };
  var BLOCK_ALLOW = { P: 1 };

  function isInside(node, tagName) {
    while (node && node !== document.body) {
      if (node.nodeType === 1 && node.tagName === tagName) return node;
      node = node.parentNode;
    }
    return null;
  }

  function selectionHas(editor, tagName) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return false;
    if (range.collapsed) {
      return !!isInside(range.startContainer, tagName);
    }
    var walker = document.createTreeWalker(
      range.commonAncestorContainer,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (n) {
          return range.intersectsNode(n) && n.textContent.length
            ? NodeFilter.FILTER_ACCEPT
            : NodeFilter.FILTER_REJECT;
        },
      },
    );
    var sawText = false;
    while (walker.nextNode()) {
      sawText = true;
      if (!isInside(walker.currentNode, tagName)) return false;
    }
    return sawText;
  }

  function unwrap(el) {
    var parent = el.parentNode;
    while (el.firstChild) parent.insertBefore(el.firstChild, el);
    parent.removeChild(el);
  }

  // Toggle an inline tag across the current range. Selection-collapsed
  // case: insert an empty wrapper at the caret so further typing is
  // formatted (matches the contract every editor uses).
  function toggleInline(editor, tagName) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return false;

    var on = selectionHas(editor, tagName);

    if (range.collapsed) {
      if (on) {
        var existing = isInside(range.startContainer, tagName);
        if (existing) unwrap(existing);
      } else {
        var wrap = document.createElement(tagName);
        wrap.appendChild(document.createTextNode("\u200B")); // ZWSP caret-anchor
        range.insertNode(wrap);
        var inner = document.createRange();
        inner.setStart(wrap.firstChild, 1);
        inner.setEnd(wrap.firstChild, 1);
        sel.removeAllRanges();
        sel.addRange(inner);
      }
      return true;
    }

    if (on) {
      var nodes = [];
      var w = document.createTreeWalker(editor, NodeFilter.SHOW_ELEMENT, {
        acceptNode: function (n) {
          return n.tagName === tagName && range.intersectsNode(n)
            ? NodeFilter.FILTER_ACCEPT
            : NodeFilter.FILTER_SKIP;
        },
      });
      while (w.nextNode()) nodes.push(w.currentNode);
      nodes.forEach(unwrap);
    } else {
      var wrapper = document.createElement(tagName);
      try {
        wrapper.appendChild(range.extractContents());
        range.insertNode(wrapper);
        sel.removeAllRanges();
        var r2 = document.createRange();
        r2.selectNodeContents(wrapper);
        sel.addRange(r2);
      } catch (_) {
        return false;
      }
    }
    return true;
  }

  // Walk an arbitrary HTML fragment, emit only allowlisted nodes,
  // strip every attribute. Used both for sanitising persisted values
  // on mount and for the emit pass on every commit.
  function sanitiseTree(rootClone) {
    (function walk(node) {
      var children = Array.prototype.slice.call(node.childNodes);
      children.forEach(function (child) {
        if (child.nodeType === 3) return;
        if (child.nodeType !== 1) {
          child.parentNode.removeChild(child);
          return;
        }
        var tag = child.tagName;
        if (INLINE_ALLOW[tag] || BLOCK_ALLOW[tag]) {
          while (child.attributes.length) {
            child.removeAttribute(child.attributes[0].name);
          }
          walk(child);
        } else {
          while (child.firstChild) {
            child.parentNode.insertBefore(child.firstChild, child);
          }
          child.parentNode.removeChild(child);
        }
      });
    })(rootClone);
    return rootClone;
  }

  function emit(editor) {
    var clone = editor.cloneNode(true);
    sanitiseTree(clone);
    var html = "";
    Array.prototype.forEach.call(clone.childNodes, function (n) {
      html += n.nodeType === 3 ? n.data : n.outerHTML;
    });
    return html
      .replace(/\u200B/g, "")
      .replace(/<p\/>|<p><\/p>/g, "")
      .trim();
  }

  // Replace the editor's contents from a (possibly untrusted) HTML
  // string. Parsed via DOMParser into a detached document — scripts
  // do not execute — then sanitised through the closed allowlist
  // before being adopted into the live tree.
  function replaceEditorContents(editor, html) {
    while (editor.firstChild) editor.removeChild(editor.firstChild);
    if (!html || !html.trim()) {
      var empty = document.createElement("p");
      empty.appendChild(document.createElement("br"));
      editor.appendChild(empty);
      return;
    }
    var doc = new DOMParser().parseFromString(
      "<div>" + html + "</div>",
      "text/html",
    );
    var wrapper = doc.body.firstChild;
    if (!wrapper) {
      var fallback = document.createElement("p");
      fallback.appendChild(document.createElement("br"));
      editor.appendChild(fallback);
      return;
    }
    sanitiseTree(wrapper);
    while (wrapper.firstChild) editor.appendChild(wrapper.firstChild);
    if (!editor.firstChild) {
      var p = document.createElement("p");
      p.appendChild(document.createElement("br"));
      editor.appendChild(p);
    }
  }

  function announce(host, text) {
    var live = host.querySelector("[data-dz-announce]");
    if (live) live.textContent = text;
  }

  function updateToolbarState(toolbar, editor) {
    var buttons = toolbar.querySelectorAll("button[data-cmd]");
    buttons.forEach(function (btn) {
      var cmd = COMMANDS[btn.getAttribute("data-cmd")];
      if (!cmd) return;
      var on = selectionHas(editor, cmd.tag);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("is-active", on);
    });
  }

  function wireToolbarKeyboard(toolbar) {
    var buttons = Array.prototype.slice.call(
      toolbar.querySelectorAll("button[data-cmd]"),
    );
    if (!buttons.length) return function () {};
    buttons.forEach(function (b, i) {
      b.setAttribute("tabindex", i === 0 ? "0" : "-1");
    });
    function onKey(e) {
      var idx = buttons.indexOf(document.activeElement);
      if (idx < 0) return;
      var next = idx;
      if (e.key === "ArrowRight") next = (idx + 1) % buttons.length;
      else if (e.key === "ArrowLeft")
        next = (idx - 1 + buttons.length) % buttons.length;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = buttons.length - 1;
      else return;
      e.preventDefault();
      buttons[idx].setAttribute("tabindex", "-1");
      buttons[next].setAttribute("tabindex", "0");
      buttons[next].focus();
    }
    toolbar.addEventListener("keydown", onKey);
    return function () {
      toolbar.removeEventListener("keydown", onKey);
    };
  }

  function buildToolbar(host, commandList) {
    var existing = host.querySelector("[data-dz-richtext-toolbar]");
    if (existing) return existing;
    var toolbar = document.createElement("div");
    toolbar.className = "dz-richtext-toolbar";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", "Formatting");
    toolbar.setAttribute("data-dz-richtext-toolbar", "");
    commandList.forEach(function (name) {
      var cmd = COMMANDS[name];
      if (!cmd) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("data-cmd", name);
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-keyshortcuts", "Control+" + cmd.key.toUpperCase());
      btn.setAttribute("title", name + " (Ctrl+" + cmd.key.toUpperCase() + ")");
      btn.textContent =
        name === "underline" ? "U" : name === "italic" ? "I" : "B";
      if (name === "italic") btn.style.fontStyle = "italic";
      if (name === "bold") btn.style.fontWeight = "700";
      if (name === "underline") btn.style.textDecoration = "underline";
      toolbar.appendChild(btn);
    });
    var editor = host.querySelector("[data-dz-editor]");
    host.insertBefore(toolbar, editor);
    return toolbar;
  }

  function ensureAnnouncer(host) {
    if (host.querySelector("[data-dz-announce]")) return;
    var live = document.createElement("div");
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    live.setAttribute("data-dz-announce", "");
    host.appendChild(live);
  }

  bridge.registerWidget("richtext-native", {
    mount: function (host, options) {
      var editor = host.querySelector("[data-dz-editor]");
      var hidden =
        host.querySelector("input[type=hidden]") ||
        host.querySelector("textarea");
      if (!editor) return null;

      editor.setAttribute("contenteditable", "true");
      editor.setAttribute("role", "textbox");
      editor.setAttribute("aria-multiline", "true");

      var initial = (hidden && hidden.value) || "";
      replaceEditorContents(editor, initial);

      var commandList = (options && options.toolbar) || [
        "bold",
        "italic",
        "underline",
      ];
      var toolbar = buildToolbar(host, commandList);
      ensureAnnouncer(host);

      var listeners = [];
      function on(target, ev, fn) {
        target.addEventListener(ev, fn);
        listeners.push(function () {
          target.removeEventListener(ev, fn);
        });
      }

      function commit() {
        if (hidden) hidden.value = emit(editor);
        updateToolbarState(toolbar, editor);
      }

      function runCommand(name) {
        var cmd = COMMANDS[name];
        if (!cmd) return;
        editor.focus();
        if (cmd.type === "inline") {
          if (toggleInline(editor, cmd.tag)) {
            commit();
            announce(
              host,
              name + " " + (selectionHas(editor, cmd.tag) ? "on" : "off"),
            );
          }
        }
      }

      on(toolbar, "mousedown", function (e) {
        // Prevent toolbar from stealing selection — the historical
        // contenteditable failure mode.
        if (e.target.closest("button[data-cmd]")) e.preventDefault();
      });
      on(toolbar, "click", function (e) {
        var btn = e.target.closest("button[data-cmd]");
        if (!btn) return;
        runCommand(btn.getAttribute("data-cmd"));
      });

      on(editor, "keydown", function (e) {
        if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey) return;
        var k = e.key.toLowerCase();
        var match = Object.keys(COMMANDS).find(function (name) {
          return COMMANDS[name].key === k;
        });
        if (!match) return;
        e.preventDefault();
        runCommand(match);
      });

      on(editor, "input", commit);
      on(document, "selectionchange", function () {
        if (
          document.activeElement === editor ||
          editor.contains(document.activeElement)
        ) {
          updateToolbarState(toolbar, editor);
        }
      });

      commit();

      var unwireToolbar = wireToolbarKeyboard(toolbar);

      return {
        destroy: function () {
          listeners.forEach(function (fn) {
            fn();
          });
          listeners.length = 0;
          unwireToolbar();
        },
        serialize: function () {
          return emit(editor);
        },
        focus: function () {
          editor.focus();
        },
      };
    },
    unmount: function (_host, instance) {
      if (instance && typeof instance.destroy === "function") {
        instance.destroy();
      }
    },
  });

  // Test/inspection hook (cycle 1 only — cycles 2+ replace with a
  // proper public API). Lets unit tests drive the editor without
  // re-implementing the bridge.
  window.dzRichText = {
    _emit: emit,
    _toggleInline: toggleInline,
    _selectionHas: selectionHas,
    _replaceEditorContents: replaceEditorContents,
    COMMANDS: COMMANDS,
  };
})();
