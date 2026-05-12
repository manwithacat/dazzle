/**
 * dz-richtext.js — Dazzle-native rich-text editor (#977 cycles 1–2).
 *
 * Spec: dev_docs/2026-05-04-dz-richtext-spec.md
 *
 * Cycle 1: bold/italic/underline + emit pass + a11y baseline.
 * Cycle 2: lists (ul/ol), headings (h2/h3), blockquote, inline code,
 *          link prompt, clear-format, full keyboard shortcuts.
 * Cycle 3: paste sanitisation pipeline — DOMParser walk, tag-synonym
 *          rewrites (b→strong, i→em, font→text), structural normalisation
 *          (lift orphan li, collapse p-in-li), inline-style flood scrub.
 * Cycle 4: undo/redo stack, soft length cap with aria-live warning,
 *          server allowlist parity (IR + bleach). Bridge flipped from
 *          "richtext-native" to "richtext"; Quill removed.
 * Cycle 5: DSL knobs (rich_text_toolbar, rich_text_max_length).
 *
 * Security model: client-side schema enforcement is a UX layer. The
 * security boundary is `RichTextField` on the server (bleach with the
 * IR-sourced allowlist; cycle 4). HTML inserted into the editor goes
 * through DOMParser + a closed-tag walker (no innerHTML writes).
 */
(function () {
  var bridge = window.dz && window.dz.bridge;
  if (!bridge) return;

  // type: "inline" | "block" | "list" | "link" | "clear"
  // key:  letter pressed with Mod (Ctrl/Cmd). Combined with shift/alt
  //       via the modifier flags, so e.g. h2 = Mod+Alt+2.
  var COMMANDS = {
    bold: { tag: "strong", type: "inline", key: "b" },
    italic: { tag: "em", type: "inline", key: "i" },
    underline: { tag: "u", type: "inline", key: "u" },
    code: { tag: "code", type: "inline", key: "e" },
    h2: { tag: "h2", type: "block", key: "2", alt: true },
    h3: { tag: "h3", type: "block", key: "3", alt: true },
    blockquote: { tag: "blockquote", type: "block", key: "q", shift: true },
    paragraph: { tag: "p", type: "block", key: "0", alt: true },
    ul: { tag: "ul", type: "list", key: "8", shift: true },
    ol: { tag: "ol", type: "list", key: "7", shift: true },
    link: { type: "link", key: "k" },
    clear: { type: "clear", key: "\\" },
  };

  var INLINE_ALLOW = { STRONG: 1, EM: 1, U: 1, S: 1, CODE: 1, A: 1, BR: 1 };
  var BLOCK_ALLOW = {
    P: 1,
    H2: 1,
    H3: 1,
    UL: 1,
    OL: 1,
    LI: 1,
    BLOCKQUOTE: 1,
    PRE: 1,
  };
  var BLOCK_TAGS = { P: 1, H2: 1, H3: 1, BLOCKQUOTE: 1, PRE: 1, LI: 1 };
  var ATTR_ALLOW = { A: { href: 1 } };
  var SAFE_HREF = /^(https?:|mailto:|\/)/i;

  var ZWSP = "\u200B";

  function isInside(node, tagName) {
    while (node && node !== document.body) {
      if (node.nodeType === 1 && node.tagName === tagName) return node;
      node = node.parentNode;
    }
    return null;
  }

  function closestBlock(node, editor) {
    while (node && node !== editor) {
      if (node.nodeType === 1 && BLOCK_TAGS[node.tagName]) return node;
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
        wrap.appendChild(document.createTextNode(ZWSP));
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
      // #1000 — if the range spans block boundaries, wrap each
      // block's *contents* in `tagName` (one wrapper per block)
      // rather than wrapping the blocks themselves. Wrapping a
      // block element in an inline tag (`<strong><p>...</p></strong>`)
      // is invalid HTML and breaks the closed schema's inline-only
      // contract for `tagName`.
      //
      // Detection: the range spans blocks iff the closest block to
      // startContainer differs from the closest block to endContainer,
      // OR the range's commonAncestorContainer is the editor itself
      // (which only happens when the range crosses block siblings).
      var startBlock = closestBlock(range.startContainer, editor);
      var endBlock = closestBlock(range.endContainer, editor);
      var spansBlocks =
        range.commonAncestorContainer === editor ||
        (startBlock && endBlock && startBlock !== endBlock);
      if (spansBlocks) {
        // Wrap each block's contents individually. Walk the editor's
        // direct children that intersect the range; for each block
        // (P / H2 / H3 / BLOCKQUOTE / PRE / LI), wrap its contents.
        var blocksToWrap = [];
        var children = Array.prototype.slice.call(editor.children);
        children.forEach(function (child) {
          if (range.intersectsNode(child) && BLOCK_TAGS[child.tagName]) {
            blocksToWrap.push(child);
          }
        });
        if (blocksToWrap.length === 0) return false;
        blocksToWrap.forEach(function (block) {
          var inner = document.createElement(tagName);
          while (block.firstChild) inner.appendChild(block.firstChild);
          block.appendChild(inner);
        });
        sel.removeAllRanges();
        var rAll = document.createRange();
        rAll.setStartBefore(blocksToWrap[0]);
        rAll.setEndAfter(blocksToWrap[blocksToWrap.length - 1]);
        sel.addRange(rAll);
        return true;
      }
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

  // Replace the block containing the selection with a new block of
  // `tagName`. If the block already has that tag, revert to <p>.
  function setBlock(editor, tagName) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return false;

    var block = closestBlock(range.startContainer, editor);
    if (!block) return false;

    // Inside a list-item: treat the LI itself as the block to swap.
    // For simplicity, escape the list when toggling to a non-list block.
    if (block.tagName === "LI") {
      var li = block;
      var list = li.parentNode;
      var newBlock = document.createElement(
        li.tagName === tagName ? "p" : tagName,
      );
      while (li.firstChild) newBlock.appendChild(li.firstChild);
      list.parentNode.insertBefore(newBlock, list.nextSibling);
      li.parentNode.removeChild(li);
      if (!list.firstChild) list.parentNode.removeChild(list);
      restoreSelectionInside(newBlock);
      return true;
    }

    var target = block.tagName === tagName ? "p" : tagName;
    var replacement = document.createElement(target);
    while (block.firstChild) replacement.appendChild(block.firstChild);
    block.parentNode.replaceChild(replacement, block);
    restoreSelectionInside(replacement);
    return true;
  }

  function restoreSelectionInside(node) {
    var sel = window.getSelection();
    var r = document.createRange();
    r.selectNodeContents(node);
    r.collapse(false);
    sel.removeAllRanges();
    sel.addRange(r);
  }

  // Toggle a list of `tagName` (UL or OL) around the block containing
  // the selection. If already in a list of that type, escape it (back
  // to <p>). If in the other list type, swap.
  function toggleList(editor, tagName) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return false;

    var block = closestBlock(range.startContainer, editor);
    if (!block) return false;

    if (block.tagName === "LI") {
      var list = block.parentNode;
      if (list.tagName === tagName) {
        var p = document.createElement("p");
        while (block.firstChild) p.appendChild(block.firstChild);
        list.parentNode.insertBefore(p, list.nextSibling);
        block.parentNode.removeChild(block);
        if (!list.firstChild) list.parentNode.removeChild(list);
        restoreSelectionInside(p);
      } else {
        var newList = document.createElement(tagName);
        var moved = block.cloneNode(true);
        newList.appendChild(moved);
        list.parentNode.insertBefore(newList, list.nextSibling);
        block.parentNode.removeChild(block);
        if (!list.firstChild) list.parentNode.removeChild(list);
        restoreSelectionInside(moved);
      }
      return true;
    }

    var listEl = document.createElement(tagName);
    var newLi = document.createElement("li");
    while (block.firstChild) newLi.appendChild(block.firstChild);
    listEl.appendChild(newLi);
    block.parentNode.replaceChild(listEl, block);
    restoreSelectionInside(newLi);
    return true;
  }

  // Toggle a link around the current selection. If already inside a
  // link, unwrap it. Otherwise prompt for href and wrap the selection.
  function toggleLink(editor, promptFn) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return false;

    var existing = isInside(range.startContainer, "A");
    if (existing) {
      unwrap(existing);
      return true;
    }
    if (range.collapsed) return false;

    var url = (promptFn || window.prompt).call(null, "Link URL", "https://");
    if (!url || !SAFE_HREF.test(url)) return false;

    var a = document.createElement("a");
    a.setAttribute("href", url);
    try {
      a.appendChild(range.extractContents());
      range.insertNode(a);
      sel.removeAllRanges();
      var r2 = document.createRange();
      r2.selectNodeContents(a);
      sel.addRange(r2);
    } catch (_) {
      return false;
    }
    return true;
  }

  // Strip every inline-formatting wrapper across the selection. Block
  // tags (h2, ul, etc.) are preserved — use setBlock("p") to flatten.
  function clearFormat(editor) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return false;
    if (range.collapsed) return false;

    var nodes = [];
    var w = document.createTreeWalker(editor, NodeFilter.SHOW_ELEMENT, {
      acceptNode: function (n) {
        return INLINE_ALLOW[n.tagName] &&
          n.tagName !== "BR" &&
          range.intersectsNode(n)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_SKIP;
      },
    });
    while (w.nextNode()) nodes.push(w.currentNode);
    nodes.reverse().forEach(unwrap);
    return true;
  }

  // Cycle 3: tag synonyms rewritten before the schema walk so the
  // result of pasting from Word/Docs/Notion produces our canonical
  // tags rather than dropping the formatting entirely. Anything not
  // listed here goes through the standard sanitiseTree drop path.
  var TAG_SYNONYMS = {
    B: "STRONG",
    I: "EM",
    STRIKE: "S",
    DEL: "S",
    H1: "H2", // never produce H1 — surface owns it (#983)
    H4: "H3",
    H5: "H3",
    H6: "H3",
    DIV: "P",
  };

  // Block-level tags we drop from the paste tree without preserving
  // their formatting (script/style/iframe/etc.). Defence in depth —
  // the closed allowlist would drop them anyway, but explicit removal
  // means the children don't get unwrapped into the document.
  var PASTE_DROP_WITH_CHILDREN = {
    SCRIPT: 1,
    STYLE: 1,
    IFRAME: 1,
    OBJECT: 1,
    EMBED: 1,
    META: 1,
    LINK: 1,
    NOSCRIPT: 1,
    TEMPLATE: 1,
  };

  // Rewrite `from` tags to `to` tags in place. Returns the (possibly
  // new) root for chaining.
  function rewriteSynonyms(root) {
    var nodes = [];
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    while (w.nextNode()) nodes.push(w.currentNode);
    nodes.forEach(function (n) {
      var target = TAG_SYNONYMS[n.tagName];
      if (!target) return;
      var replacement = document.createElement(target);
      while (n.firstChild) replacement.appendChild(n.firstChild);
      n.parentNode.replaceChild(replacement, n);
    });
    return root;
  }

  // Lift orphan <li> nodes (no parent ul/ol) into a synthetic <ul>.
  // Also collapse <p> children of <li> into the li directly so the
  // paste matches the schema (li contains inline, not block).
  function normaliseListStructure(root) {
    var orphans = [];
    Array.prototype.forEach.call(root.querySelectorAll("li"), function (li) {
      var parent = li.parentNode;
      if (parent.tagName !== "UL" && parent.tagName !== "OL") {
        orphans.push(li);
      }
      // Collapse <p> children into the li.
      Array.prototype.forEach.call(li.querySelectorAll("p"), function (p) {
        if (p.parentNode === li) {
          while (p.firstChild) li.insertBefore(p.firstChild, p);
          if (li.lastChild !== p)
            li.insertBefore(document.createElement("br"), p);
          li.removeChild(p);
        }
      });
    });
    orphans.forEach(function (li) {
      var prev = li.previousElementSibling;
      if (prev && prev.tagName === "UL") {
        prev.appendChild(li);
        return;
      }
      var ul = document.createElement("ul");
      li.parentNode.insertBefore(ul, li);
      ul.appendChild(li);
    });
    return root;
  }

  // Strip pre-walk: drop entire subtrees whose root is in
  // PASTE_DROP_WITH_CHILDREN (script/style/iframe/etc.) plus comment
  // and processing-instruction nodes. Done before the synonym pass so
  // <script><b>x</b></script> doesn't leak its <b>.
  function dropDangerousSubtrees(root) {
    var children = Array.prototype.slice.call(root.childNodes);
    children.forEach(function (child) {
      if (child.nodeType === 8 || child.nodeType === 7) {
        child.parentNode.removeChild(child);
        return;
      }
      if (child.nodeType !== 1) return;
      if (PASTE_DROP_WITH_CHILDREN[child.tagName]) {
        child.parentNode.removeChild(child);
        return;
      }
      dropDangerousSubtrees(child);
    });
    return root;
  }

  // Cycle 3 entry point — given an HTML string from the clipboard,
  // produce a DocumentFragment of editor-safe nodes ready to insert
  // via Range.insertNode. Pure: no DOM mutation outside the parsed
  // tree.
  function pasteSanitise(html) {
    var doc = new DOMParser().parseFromString(
      "<div>" + html + "</div>",
      "text/html",
    );
    var root = doc.body.firstChild;
    if (!root) return document.createDocumentFragment();
    dropDangerousSubtrees(root);
    rewriteSynonyms(root);
    normaliseListStructure(root);
    sanitiseTree(root);
    var frag = document.createDocumentFragment();
    while (root.firstChild) frag.appendChild(root.firstChild);
    return frag;
  }

  function handlePaste(editor, event) {
    var data = event.clipboardData;
    if (!data) return;
    var html = data.getData("text/html");
    var text = data.getData("text/plain");
    if (!html && !text) return;
    event.preventDefault();
    var frag = html
      ? pasteSanitise(html)
      : (function () {
          // Plain-text paste: split on blank lines into <p>, single
          // newlines become <br>. Avoids dumping a raw text node
          // outside any block.
          var f = document.createDocumentFragment();
          text.split(/\n{2,}/).forEach(function (para) {
            var p = document.createElement("p");
            var lines = para.split("\n");
            lines.forEach(function (line, i) {
              if (i > 0) p.appendChild(document.createElement("br"));
              p.appendChild(document.createTextNode(line));
            });
            f.appendChild(p);
          });
          return f;
        })();
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    var range = sel.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return;
    range.deleteContents();
    var lastNode = frag.lastChild;
    range.insertNode(frag);
    if (lastNode) {
      var r = document.createRange();
      r.setStartAfter(lastNode);
      r.collapse(true);
      sel.removeAllRanges();
      sel.addRange(r);
    }
  }

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
          var allowAttrs = ATTR_ALLOW[tag] || {};
          var attrNames = Array.prototype.map.call(
            child.attributes,
            function (a) {
              return a.name;
            },
          );
          attrNames.forEach(function (name) {
            if (!allowAttrs[name]) child.removeAttribute(name);
          });
          if (tag === "A") {
            var href = child.getAttribute("href") || "";
            if (!SAFE_HREF.test(href)) child.removeAttribute("href");
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

  function commandIsActive(editor, name) {
    var cmd = COMMANDS[name];
    if (!cmd) return false;
    if (cmd.type === "inline") return selectionHas(editor, cmd.tag);
    if (cmd.type === "block") {
      var sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return false;
      var block = closestBlock(sel.getRangeAt(0).startContainer, editor);
      return !!(block && block.tagName === cmd.tag);
    }
    if (cmd.type === "list") {
      var s = window.getSelection();
      if (!s || s.rangeCount === 0) return false;
      var b = closestBlock(s.getRangeAt(0).startContainer, editor);
      return !!(b && b.tagName === "LI" && b.parentNode.tagName === cmd.tag);
    }
    if (cmd.type === "link") {
      var sl = window.getSelection();
      if (!sl || sl.rangeCount === 0) return false;
      return !!isInside(sl.getRangeAt(0).startContainer, "A");
    }
    return false;
  }

  function updateToolbarState(toolbar, editor) {
    var buttons = toolbar.querySelectorAll("button[data-cmd]");
    buttons.forEach(function (btn) {
      var name = btn.getAttribute("data-cmd");
      var on = commandIsActive(editor, name);
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

  function buttonLabel(name) {
    return (
      {
        bold: "B",
        italic: "I",
        underline: "U",
        code: "</>",
        h2: "H2",
        h3: "H3",
        blockquote: "❝",
        paragraph: "¶",
        ul: "•",
        ol: "1.",
        link: "🔗",
        clear: "✕",
      }[name] || name
    );
  }

  function shortcutLabel(cmd) {
    var parts = ["Control"];
    if (cmd.shift) parts.push("Shift");
    if (cmd.alt) parts.push("Alt");
    parts.push(cmd.key.toUpperCase());
    return parts.join("+");
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
      if (name === "|") {
        var sep = document.createElement("span");
        sep.className = "dz-richtext-toolbar-sep";
        sep.setAttribute("role", "separator");
        sep.setAttribute("aria-hidden", "true");
        toolbar.appendChild(sep);
        return;
      }
      var cmd = COMMANDS[name];
      if (!cmd) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("data-cmd", name);
      btn.setAttribute("aria-pressed", "false");
      var sc = shortcutLabel(cmd);
      btn.setAttribute("aria-keyshortcuts", sc);
      btn.setAttribute("title", name + " (" + sc + ")");
      btn.textContent = buttonLabel(name);
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

  function matchKeyEvent(e) {
    if (!(e.ctrlKey || e.metaKey)) return null;
    var k = e.key.toLowerCase();
    var names = Object.keys(COMMANDS);
    for (var i = 0; i < names.length; i++) {
      var c = COMMANDS[names[i]];
      if (c.key !== k) continue;
      if (!!c.shift !== !!e.shiftKey) continue;
      if (!!c.alt !== !!e.altKey) continue;
      return names[i];
    }
    return null;
  }

  bridge.registerWidget("richtext", {
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
        "|",
        "h2",
        "h3",
        "|",
        "ul",
        "ol",
        "|",
        "link",
        "clear",
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

      // Cycle 4: undo/redo. Each entry is the serialised HTML at the
      // moment of commit. Replaying walks the editor back through
      // replaceEditorContents (DOMParser-routed, schema-safe).
      var UNDO_LIMIT = 100;
      var undoStack = [];
      var redoStack = [];
      var lastSnapshot = null;

      function snapshot() {
        var html = emit(editor);
        if (html === lastSnapshot) return;
        if (lastSnapshot !== null) {
          undoStack.push(lastSnapshot);
          if (undoStack.length > UNDO_LIMIT) undoStack.shift();
          redoStack.length = 0;
        }
        lastSnapshot = html;
      }

      function applyHistory(html) {
        replaceEditorContents(editor, html);
        if (hidden) hidden.value = emit(editor);
        updateToolbarState(toolbar, editor);
      }

      function undo() {
        if (!undoStack.length) return false;
        redoStack.push(lastSnapshot);
        lastSnapshot = undoStack.pop();
        applyHistory(lastSnapshot);
        announce(host, "undo");
        return true;
      }

      function redo() {
        if (!redoStack.length) return false;
        undoStack.push(lastSnapshot);
        lastSnapshot = redoStack.pop();
        applyHistory(lastSnapshot);
        announce(host, "redo");
        return true;
      }

      // Cycle 4: soft length cap. Server enforces absolutely; client
      // surfaces a polite warning at 90% via the announcer.
      var maxLength =
        (options &&
          typeof options.maxLength === "number" &&
          options.maxLength) ||
        50000;
      var warnedAt90 = false;

      function commit() {
        if (hidden) hidden.value = emit(editor);
        var len = (hidden && hidden.value.length) || 0;
        if (len > 0.9 * maxLength && !warnedAt90) {
          warnedAt90 = true;
          announce(host, "approaching length limit");
        } else if (len <= 0.9 * maxLength) {
          warnedAt90 = false;
        }
        updateToolbarState(toolbar, editor);
        snapshot();
      }

      function runCommand(name) {
        var cmd = COMMANDS[name];
        if (!cmd) return;
        editor.focus();
        var changed = false;
        if (cmd.type === "inline") changed = toggleInline(editor, cmd.tag);
        else if (cmd.type === "block") changed = setBlock(editor, cmd.tag);
        else if (cmd.type === "list") changed = toggleList(editor, cmd.tag);
        else if (cmd.type === "link")
          changed = toggleLink(editor, options && options.linkPrompt);
        else if (cmd.type === "clear") changed = clearFormat(editor);
        if (!changed) return;
        commit();
        announce(
          host,
          name + " " + (commandIsActive(editor, name) ? "applied" : "removed"),
        );
      }

      on(toolbar, "mousedown", function (e) {
        if (e.target.closest("button[data-cmd]")) e.preventDefault();
      });
      on(toolbar, "click", function (e) {
        var btn = e.target.closest("button[data-cmd]");
        if (!btn) return;
        runCommand(btn.getAttribute("data-cmd"));
      });

      on(editor, "keydown", function (e) {
        // Cycle 4: explicit undo/redo handlers. We don't trust the
        // browser's contenteditable undo across our schema-rewriting
        // commands, and we want shift+z = redo to be standard
        // regardless of platform.
        if ((e.ctrlKey || e.metaKey) && !e.altKey) {
          var k = e.key.toLowerCase();
          if (k === "z" && !e.shiftKey) {
            e.preventDefault();
            undo();
            return;
          }
          if ((k === "z" && e.shiftKey) || k === "y") {
            e.preventDefault();
            redo();
            return;
          }
        }
        var match = matchKeyEvent(e);
        if (!match) return;
        e.preventDefault();
        runCommand(match);
      });

      on(editor, "input", commit);
      on(editor, "paste", function (e) {
        handlePaste(editor, e);
        commit();
      });
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

  window.dzRichText = {
    _emit: emit,
    _toggleInline: toggleInline,
    _setBlock: setBlock,
    _toggleList: toggleList,
    _toggleLink: toggleLink,
    _clearFormat: clearFormat,
    _selectionHas: selectionHas,
    _replaceEditorContents: replaceEditorContents,
    _matchKeyEvent: matchKeyEvent,
    _pasteSanitise: pasteSanitise,
    _handlePaste: handlePaste,
    _rewriteSynonyms: rewriteSynonyms,
    _normaliseListStructure: normaliseListStructure,
    _dropDangerousSubtrees: dropDangerousSubtrees,
    TAG_SYNONYMS: TAG_SYNONYMS,
    PASTE_DROP_WITH_CHILDREN: PASTE_DROP_WITH_CHILDREN,
    COMMANDS: COMMANDS,
  };
})();
