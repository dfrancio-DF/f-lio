"use strict";

const paths = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 3H20v19H6.5A2.5 2.5 0 0 1 4 19.5v-14A2.5 2.5 0 0 1 6.5 3z"/><path d="M8 7h8M8 11h5"/>',
  panel: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  moon: '<path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  up: '<path d="m6 15 6-6 6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 11.55-2L20 8M4 16l2.45 3A7 7 0 0 0 18 17"/>',
  maximize: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  type: '<path d="M4 5V3h16v2M12 3v18M8 21h8"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  keyboard: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M7 15h10"/>',
  eraser: '<path d="m16 3 5 5a2 2 0 0 1 0 3l-9 10H7l-5-5a2 2 0 0 1 0-3L13 3a2 2 0 0 1 3 0zM6 10l9 9M12 21h10"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
document.querySelectorAll("[data-icon]").forEach(el => { el.innerHTML = icon(el.dataset.icon); });

// Hold references to app chrome so document headings cannot shadow its IDs.
const elements = new Map([...document.querySelectorAll("[id]")].map(el => [el.id, el]));
const $ = id => elements.get(id);
const state = { theme: "light", zoom: 1, focus: false, recent: [], document: null, welcome: null };
const scrollArea = $("reading-scroll");
let toastTimer;
let searchTimer;
let headings = [];
let matches = [];
let matchIndex = -1;

function bridge(action, value) {
  const handler = window.webkit?.messageHandlers?.folio;
  if (handler) handler.postMessage(JSON.stringify({ action, value }));
  else window.dispatchEvent(new CustomEvent("folio-action", { detail: { action, value } }));
}

function notify(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4000);
}

function applyTheme() {
  const dark = state.theme === "dark" || (state.theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("theme-button").innerHTML = icon(dark ? "sun" : "moon");
  $("theme-button").title = dark ? "Usar tema claro" : "Usar tema escuro";
}

function applySettings(settings) {
  Object.assign(state, settings);
  applyTheme();
  document.body.classList.toggle("focus", state.focus);
  document.documentElement.style.setProperty("--zoom", state.zoom);
  renderRecent();
}

function renderRecent() {
  $("recent").replaceChildren();
  for (const path of state.recent) {
    const button = document.createElement("button");
    button.className = "recent-item" + (path === state.document?.path ? " selected" : "");
    button.title = path;
    button.innerHTML = icon("file");
    const label = document.createElement("span");
    label.textContent = path.split("/").pop().replace(/\.(md|markdown|mdown|mkd)$/i, "");
    button.append(label);
    button.addEventListener("click", () => bridge("recent", path));
    $("recent").append(button);
  }
  document.querySelector(".welcome-item").classList.toggle("selected", !state.document?.path);
}

function showDocument(data) {
  const previousScroll = scrollArea.scrollTop;
  const sameFile = data.path === state.document?.path;
  state.document = data;
  if (!data.path) state.welcome = data;
  $("document").innerHTML = data.html;
  $("filename").textContent = data.filename;
  $("document-tag").textContent = data.path ? "DOCUMENTO MARKDOWN" : "BOAS-VINDAS";
  $("reading-time").textContent = `${data.minutes} min de leitura`;
  $("word-count").textContent = `${data.words.toLocaleString("pt-BR")} palavras`;
  $("folder").textContent = data.folder;
  $("folder").title = data.folder;
  $("live-status").innerHTML = `<i></i> ${data.path ? "Atualização automática" : "Leitura local"}`;
  document.title = `${data.title} — Fólio`;
  $("toc").replaceChildren();
  const outline = data.headings.filter(h => h.level <= 3 && h.level !== 1);
  for (const heading of outline) {
    const link = document.createElement("a");
    link.href = `#${heading.id}`;
    link.textContent = heading.title;
    link.className = `level-${heading.level}`;
    link.addEventListener("click", event => { event.preventDefault(); goTo(heading.id); });
    $("toc").append(link);
  }
  document.querySelector(".toc-panel").classList.toggle("empty", !outline.length);
  $("document").querySelectorAll("table").forEach(table => {
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    table.replaceWith(wrap);
    wrap.append(table);
    // Bound each column's preferred content length so a prose-heavy column
    // cannot take almost all available width from labels and file paths.
    const rows = [...table.rows];
    const lengths = [];
    for (const row of rows) {
      let index = 0;
      for (const cell of row.cells) {
        const length = cell.textContent.trim().length / cell.colSpan;
        for (let span = 0; span < cell.colSpan; span++, index++) {
          lengths[index] = Math.max(lengths[index] || 1, Math.min(48, length));
        }
      }
    }
    const total = lengths.reduce((sum, length) => sum + length, 0);
    const group = document.createElement("colgroup");
    lengths.forEach(length => {
      const column = document.createElement("col");
      column.style.width = `${length / total * 100}%`;
      group.append(column);
    });
    table.prepend(group);
  });
  $("document").querySelectorAll("pre").forEach(pre => {
    const copy = document.createElement("button");
    copy.className = "copy-code";
    copy.textContent = "Copiar";
    copy.setAttribute("aria-label", "Copiar bloco de código");
    copy.addEventListener("click", () => {
      bridge("copy", pre.querySelector("code")?.textContent || "");
      copy.textContent = "Copiado!";
      setTimeout(() => { copy.textContent = "Copiar"; }, 1800);
    });
    pre.append(copy);
  });
  headings = [...$("document").querySelectorAll("h2[id], h3[id]")];
  renderRecent();
  requestAnimationFrame(() => {
    scrollArea.scrollTo({ top: data.reload && sameFile ? previousScroll : 0, behavior: "instant" });
    updateProgress();
  });
  if (data.reload) {
    $("status-right").textContent = "Atualizado agora";
    setTimeout(() => { $("status-right").textContent = "Markdown, com calma."; }, 2300);
  }
  if (!$("find-bar").hidden && $("find-input").value) searchDocument();
}

function goTo(anchor) {
  const target = $("document").querySelector(`#${CSS.escape(anchor)}`);
  if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function updateProgress() {
  const available = scrollArea.scrollHeight - scrollArea.clientHeight;
  $("reading-progress").style.width = `${available > 0 ? scrollArea.scrollTop / available * 100 : 100}%`;
  let current = "";
  const top = scrollArea.getBoundingClientRect().top;
  for (const heading of headings) {
    if (heading.getBoundingClientRect().top - top <= 100) current = heading.id;
  }
  $("toc").querySelectorAll("a").forEach(a => a.classList.toggle("active", a.hash.slice(1) === current));
}
scrollArea.addEventListener("scroll", updateProgress, { passive: true });
window.addEventListener("resize", updateProgress);

function closeFind() {
  $("find-bar").hidden = true;
  $("find-input").value = "";
  $("find-count").textContent = "";
  clearTimeout(searchTimer);
  clearSearch();
  scrollArea.focus({ preventScroll: true });
}

function clearSearch() {
  matches = [];
  matchIndex = -1;
  if (CSS.highlights) {
    CSS.highlights.delete("folio-search");
    CSS.highlights.delete("folio-current");
  } else window.getSelection()?.removeAllRanges();
}

function searchDocument() {
  clearSearch();
  const query = $("find-input").value;
  if (!query) { $("find-count").textContent = ""; return; }
  const walker = document.createTreeWalker($("document"), NodeFilter.SHOW_TEXT);
  const segments = [];
  let text = "", lastBlock, node;
  while ((node = walker.nextNode())) {
    if (node.parentElement.closest("button")) continue;
    const block = node.parentElement.closest("p, li, h1, h2, h3, h4, h5, h6, td, th, pre, blockquote, summary, div");
    if (lastBlock && block !== lastBlock) text += "\n";
    segments.push({ node, start: text.length, end: text.length + node.length });
    text += node.textContent;
    lastBlock = block;
  }
  const expression = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
  let found;
  while ((found = expression.exec(text)) && matches.length < 10000) {
    const start = segments.find(s => s.start <= found.index && s.end > found.index);
    const endOffset = found.index + found[0].length;
    const end = segments.find(s => s.start < endOffset && s.end >= endOffset);
    if (!start || !end) continue;
    const range = document.createRange();
    range.setStart(start.node, found.index - start.start);
    range.setEnd(end.node, endOffset - end.start);
    matches.push(range);
  }
  if (CSS.highlights && window.Highlight) CSS.highlights.set("folio-search", new Highlight(...matches));
  if (matches.length) moveMatch(1);
  else $("find-count").textContent = "Nenhum resultado";
}

function moveMatch(direction) {
  if (!matches.length) return;
  matchIndex = (matchIndex + direction + matches.length) % matches.length;
  const range = matches[matchIndex];
  if (CSS.highlights && window.Highlight) CSS.highlights.set("folio-current", new Highlight(range));
  else {
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  const rect = range.getBoundingClientRect();
  const viewport = scrollArea.getBoundingClientRect();
  if (rect.top < viewport.top + 60 || rect.bottom > viewport.bottom - 60) {
    scrollArea.scrollBy({ top: rect.top - viewport.top - viewport.height / 2, behavior: "smooth" });
  }
  $("find-count").textContent = `${matchIndex + 1} / ${matches.length}`;
}

function action(name) {
  if (name !== "menu") {
    $("options").hidden = true;
    $("menu-button").setAttribute("aria-expanded", "false");
  }
  switch (name) {
    case "open": case "reload": case "clear-recent":
      bridge(name); break;
    case "find-next": moveMatch(1); break;
    case "find-previous": moveMatch(-1); break;
    case "reveal":
      if (state.document?.path) bridge("reveal");
      else notify("Abra um arquivo para ver sua localização.");
      break;
    case "welcome":
      if (window.webkit?.messageHandlers?.folio) bridge("welcome");
      else if (state.welcome) showDocument(state.welcome);
      break;
    case "focus":
      state.focus = !state.focus;
      document.body.classList.toggle("focus", state.focus);
      bridge("focus", state.focus);
      updateProgress();
      break;
    case "theme": case "theme-system":
      state.theme = name === "theme-system" ? "system" : document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme();
      bridge("theme", state.theme);
      break;
    case "zoom-in": case "zoom-out": case "zoom-reset":
      state.zoom = name === "zoom-reset" ? 1 : Math.round(Math.max(.8, Math.min(1.5, state.zoom + (name === "zoom-in" ? .1 : -.1))) * 10) / 10;
      document.documentElement.style.setProperty("--zoom", state.zoom);
      bridge("zoom", state.zoom);
      notify(`Tamanho do texto: ${Math.round(state.zoom * 100)}%`);
      updateProgress();
      break;
    case "find":
      $("find-bar").hidden = false;
      $("find-input").focus();
      $("find-input").select();
      break;
    case "close-find": closeFind(); break;
    case "escape":
      if (!$("find-bar").hidden) closeFind();
      else if (state.focus) action("focus");
      if ($("shortcuts-dialog").open) $("shortcuts-dialog").close();
      break;
    case "menu":
      $("options").hidden = !$("options").hidden;
      $("menu-button").setAttribute("aria-expanded", String(!$("options").hidden));
      break;
    case "top": scrollArea.scrollTo({ top: 0, behavior: "smooth" }); break;
    case "shortcuts": $("shortcuts-dialog").showModal(); break;
    case "close-shortcuts": $("shortcuts-dialog").close(); break;
  }
}

document.addEventListener("click", event => {
  const control = event.target.closest("[data-action]");
  if (control) action(control.dataset.action);
  else if (!event.target.closest("#options")) {
    $("options").hidden = true;
    $("menu-button").setAttribute("aria-expanded", "false");
  }
  const anchor = event.target.closest("#document a[href^='#']");
  if (anchor) { event.preventDefault(); goTo(decodeURIComponent(anchor.hash.slice(1))); }
});

$("find-input").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchDocument, 180);
});
$("find-input").addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); moveMatch(event.shiftKey ? -1 : 1); }
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

// Keyboard handling in GTK takes precedence; this also makes UI previews usable.
if (!window.webkit?.messageHandlers?.folio) {
  document.addEventListener("keydown", event => {
    let command;
    if (event.ctrlKey && event.key.toLowerCase() === "f") command = event.shiftKey ? "focus" : "find";
    else if (event.ctrlKey && event.key.toLowerCase() === "o") command = "open";
    else if (event.key === "Escape") command = "escape";
    if (command) { event.preventDefault(); action(command); }
  });
}

window.folio = {
  receive(event, data) {
    switch (event) {
      case "settings": applySettings(data); break;
      case "document": showDocument(data); break;
      case "command": action(data); break;
      case "toast": notify(data); break;
      case "anchor": requestAnimationFrame(() => goTo(data)); break;
    }
  },
};
