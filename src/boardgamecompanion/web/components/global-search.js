import {api} from "../core/api.js";
import {coverMarkup, escapeHtml} from "../core/ui.js";

export function bindGlobalSearch({onNavigate} = {}) {
  const dialog = document.querySelector("#globalSearchDialog");
  const input = document.querySelector("#globalSearchInput");
  const results = document.querySelector("#globalSearchResults");
  const triggers = document.querySelectorAll("[data-global-search]");
  if (!dialog || !input || !results) return {open() {}};
  let timer = null;
  let controller = null;

  function open() {
    if (!dialog.open) dialog.showModal();
    window.setTimeout(() => input.focus(), 0);
  }
  function close() {
    if (dialog.open) dialog.close();
  }

  triggers.forEach((button) => button.addEventListener("click", open));
  dialog.querySelector("[data-close-global-search]")?.addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      open();
    }
  });

  async function run() {
    const q = input.value.trim();
    controller?.abort();
    if (!q) {
      results.innerHTML = '<p class="global-search-hint">Cerca giochi, Liste, Wishlist e sezioni dell’app.</p>';
      return;
    }
    controller = new AbortController();
    results.innerHTML = '<div class="skeleton"></div>';
    try {
      const payload = await api(`/api/search?q=${encodeURIComponent(q)}&limit=12`, {signal: controller.signal});
      results.innerHTML = payload.groups.length
        ? payload.groups.map((group) => `
            <section class="global-search-group">
              <h3>${escapeHtml(group.label)}</h3>
              ${group.items.map((item) => `
                <a class="global-search-result" href="${escapeHtml(item.url)}" ${item.external ? 'target="_blank" rel="noopener noreferrer"' : "data-search-nav"}>
                  ${item.cover_url ? coverMarkup(item, "global-search-cover") : '<span class="global-search-icon" aria-hidden="true">⌕</span>'}
                  <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.subtitle || "")}</small></span>
                </a>
              `).join("")}
            </section>
          `).join("")
        : '<div class="empty-state"><strong>Nessun risultato</strong></div>';
      results.querySelectorAll("[data-search-nav]").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const url = new URL(link.href, window.location.origin);
          close();
          history.pushState({}, "", url.pathname);
          onNavigate?.();
        });
      });
    } catch (error) {
      if (error.name !== "AbortError") results.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    }
  }

  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(run, 140);
  });
  return {open, close};
}
