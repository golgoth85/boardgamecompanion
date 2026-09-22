const app = document.querySelector("#app");
const importDialog = document.querySelector("#importDialog");
const importButton = document.querySelector("#importButton");
const importForm = document.querySelector("#importForm");
const csvFile = document.querySelector("#csvFile");
const fileName = document.querySelector("#fileName");
const importResult = document.querySelector("#importResult");
const submitImport = document.querySelector("#submitImport");
const cancelImport = document.querySelector("#cancelImport");
const closeImport = document.querySelector("#closeImport");
const toast = document.querySelector("#toast");

const state = {
  q: "",
  itemType: "",
  owned: "",
  sort: "title",
  limit: 24,
  offset: 0,
  total: 0,
};

let searchTimer;
let catalogRequestController;
let importInProgress = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function initials(title) {
  const words = String(title || "?").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.slice(0, 3).map((word) => word[0]).join("").toUpperCase();
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("it-IT", { maximumFractionDigits: digits });
}

function playerText(game) {
  const min = game.players?.min;
  const max = game.players?.max;
  if (!min && !max) return "—";
  return min === max ? String(min) : `${min ?? "?"}–${max ?? "?"}`;
}

function timeText(game) {
  const min = game.play_time?.min;
  const max = game.play_time?.max;
  const playing = game.play_time?.playing;
  if (min && max && min !== max) return `${min}–${max} min`;
  if (playing) return `${playing} min`;
  if (min || max) return `${min || max} min`;
  return "—";
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function resetImportDialog() {
  importForm.reset();
  fileName.textContent = "Nessun file selezionato";
  importResult.hidden = true;
  importResult.textContent = "";
  submitImport.disabled = false;
  submitImport.textContent = "Importa";
  cancelImport.disabled = false;
  closeImport.disabled = false;
  importInProgress = false;
}

function setImportBusy(busy) {
  importInProgress = busy;
  submitImport.disabled = busy;
  submitImport.textContent = busy ? "Importazione…" : "Importa";
  cancelImport.disabled = busy;
  closeImport.disabled = busy;
}

function closeImportDialog() {
  if (!importInProgress && importDialog.open) {
    importDialog.close();
  }
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Errore HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function gameCard(game) {
  const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
  const year = game.year_published || "—";
  const rating = game.bgg?.average ? `★ ${formatNumber(game.bgg.average, 1)}` : "★ —";
  return `
    <a class="game-card" href="/games/${game.bgg_id}" data-nav aria-label="Apri ${escapeHtml(game.title)}">
      <div class="cover">
        <span class="badge card-badge">${type}</span>
        <span class="cover-initials">${escapeHtml(initials(game.title))}</span>
      </div>
      <div class="card-body">
        <h3 class="card-title">${escapeHtml(game.title)}</h3>
        <div class="card-meta">
          <span>${escapeHtml(year)}</span>
          <span>${escapeHtml(playerText(game))} gioc.</span>
          <span class="rating">${rating}</span>
        </div>
      </div>
    </a>
  `;
}

function skeletons() {
  return Array.from({length: 12}, () => '<div class="skeleton"></div>').join("");
}

async function renderCatalog() {
  app.innerHTML = `
    <section class="hero">
      <article class="hero-card">
        <p class="eyebrow">Catalogo locale</p>
        <h1>La tua ludoteca, ordinata.</h1>
        <p class="lead">
          Cerca giochi ed espansioni, consulta i dati BGG già presenti nel tuo export
          e aggiorna la collezione senza dipendere dall'API di BoardGameGeek.
        </p>
      </article>
      <section class="stats-panel" id="statsPanel" aria-label="Statistiche catalogo">
        <div class="stat"><strong>—</strong><span>Totale</span></div>
        <div class="stat"><strong>—</strong><span>Giochi base</span></div>
        <div class="stat"><strong>—</strong><span>Espansioni</span></div>
        <div class="stat"><strong>—</strong><span>Posseduti</span></div>
      </section>
    </section>

    <section class="toolbar" aria-label="Filtri catalogo">
      <label class="field search-field">
        <input id="searchInput" type="search" aria-label="Cerca per titolo" placeholder="Cerca titolo…" value="${escapeHtml(state.q)}" autocomplete="off">
      </label>
      <label class="field">
        <select id="typeFilter" aria-label="Tipo">
          <option value="">Tutti i tipi</option>
          <option value="standalone" ${state.itemType === "standalone" ? "selected" : ""}>Giochi base</option>
          <option value="expansion" ${state.itemType === "expansion" ? "selected" : ""}>Espansioni</option>
        </select>
      </label>
      <label class="field">
        <select id="ownedFilter" aria-label="Stato collezione">
          <option value="">Tutti gli stati</option>
          <option value="true" ${state.owned === "true" ? "selected" : ""}>Posseduti</option>
          <option value="false" ${state.owned === "false" ? "selected" : ""}>Non posseduti</option>
        </select>
      </label>
      <label class="field">
        <select id="sortFilter" aria-label="Ordina">
          <option value="title" ${state.sort === "title" ? "selected" : ""}>Titolo A–Z</option>
          <option value="year_desc" ${state.sort === "year_desc" ? "selected" : ""}>Anno più recente</option>
          <option value="rating_desc" ${state.sort === "rating_desc" ? "selected" : ""}>Rating BGG</option>
          <option value="rank_asc" ${state.sort === "rank_asc" ? "selected" : ""}>Ranking BGG</option>
          <option value="weight_desc" ${state.sort === "weight_desc" ? "selected" : ""}>Complessità</option>
        </select>
      </label>
    </section>

    <div class="catalog-head">
      <h2>Catalogo</h2>
      <span class="muted" id="resultCount">Caricamento…</span>
    </div>

    <section class="grid" id="catalogGrid">${skeletons()}</section>
    <nav class="pagination" id="pagination" aria-label="Paginazione"></nav>
  `;

  bindCatalogControls();
  const requestedPath = window.location.pathname;

  try {
    const [stats, catalog] = await Promise.all([
      api("/api/catalog/stats"),
      loadCatalogData(),
    ]);
    if (window.location.pathname !== requestedPath) return;
    renderStats(stats);
    renderCatalogData(catalog);
  } catch (error) {
    document.querySelector("#catalogGrid").innerHTML =
      `<div class="empty" style="grid-column:1/-1">Impossibile caricare il catalogo: ${escapeHtml(error.message)}</div>`;
    showToast(error.message, true);
  }
}

function bindCatalogControls() {
  document.querySelector("#searchInput").addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.q = event.target.value.trim();
      state.offset = 0;
      refreshCatalog();
    }, 260);
  });

  document.querySelector("#typeFilter").addEventListener("change", (event) => {
    state.itemType = event.target.value;
    state.offset = 0;
    refreshCatalog();
  });

  document.querySelector("#ownedFilter").addEventListener("change", (event) => {
    state.owned = event.target.value;
    state.offset = 0;
    refreshCatalog();
  });

  document.querySelector("#sortFilter").addEventListener("change", (event) => {
    state.sort = event.target.value;
    state.offset = 0;
    refreshCatalog();
  });
}

async function loadCatalogData(signal) {
  const params = new URLSearchParams({
    limit: String(state.limit),
    offset: String(state.offset),
    sort: state.sort,
  });
  if (state.q) params.set("q", state.q);
  if (state.itemType) params.set("item_type", state.itemType);
  if (state.owned) params.set("owned", state.owned);
  return api(`/api/games?${params}`, signal ? {signal} : undefined);
}

async function refreshCatalog() {
  const grid = document.querySelector("#catalogGrid");
  const count = document.querySelector("#resultCount");
  if (!grid || !count) return;

  catalogRequestController?.abort();
  const controller = new AbortController();
  catalogRequestController = controller;

  grid.innerHTML = skeletons();
  count.textContent = "Caricamento…";
  try {
    const catalog = await loadCatalogData(controller.signal);
    if (controller.signal.aborted || !document.querySelector("#catalogGrid")) return;
    renderCatalogData(catalog);
  } catch (error) {
    if (error.name === "AbortError") return;
    if (document.querySelector("#catalogGrid")) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1">${escapeHtml(error.message)}</div>`;
    }
    showToast(error.message, true);
  } finally {
    if (catalogRequestController === controller) {
      catalogRequestController = undefined;
    }
  }
}

function renderStats(stats) {
  const values = [
    [stats.total, "Totale"],
    [stats.standalone, "Giochi base"],
    [stats.expansions, "Espansioni"],
    [stats.owned, "Posseduti"],
  ];
  document.querySelector("#statsPanel").innerHTML = values.map(([value, label]) =>
    `<div class="stat"><strong>${formatNumber(value, 0)}</strong><span>${label}</span></div>`
  ).join("");
}

function renderCatalogData(catalog) {
  state.total = catalog.total;
  const grid = document.querySelector("#catalogGrid");
  const count = document.querySelector("#resultCount");

  count.textContent = `${formatNumber(catalog.total, 0)} risultati`;
  if (!catalog.items.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1">Nessun gioco corrisponde ai filtri selezionati.</div>';
  } else {
    grid.innerHTML = catalog.items.map(gameCard).join("");
  }
  renderPagination();
}

function renderPagination() {
  const container = document.querySelector("#pagination");
  const page = Math.floor(state.offset / state.limit) + 1;
  const pages = Math.max(1, Math.ceil(state.total / state.limit));
  container.innerHTML = `
    <button class="button button-ghost" id="prevPage" ${page <= 1 ? "disabled" : ""}>← Precedente</button>
    <span class="muted">Pagina ${page} di ${pages}</span>
    <button class="button button-ghost" id="nextPage" ${page >= pages ? "disabled" : ""}>Successiva →</button>
  `;
  document.querySelector("#prevPage").addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    refreshCatalog();
    window.scrollTo({top: 0, behavior: "smooth"});
  });
  document.querySelector("#nextPage").addEventListener("click", () => {
    state.offset += state.limit;
    refreshCatalog();
    window.scrollTo({top: 0, behavior: "smooth"});
  });
}

function fact(label, value) {
  return `<div class="fact"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value ?? "—")}</strong></div>`;
}

async function renderDetail(bggId) {
  app.innerHTML = `
    <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
    <section class="detail">
      <div class="skeleton"></div>
      <div class="panel detail-main"><div class="skeleton"></div></div>
    </section>
  `;
  const requestedPath = window.location.pathname;
  try {
    const game = await api(`/api/games/${bggId}`);
    if (window.location.pathname !== requestedPath) return;
    const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
    const collection = game.collection || {};
    const bgg = game.bgg || {};

    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
      <section class="detail">
        <div class="detail-cover">
          <span class="cover-initials">${escapeHtml(initials(game.title))}</span>
        </div>
        <article class="panel detail-main">
          <p class="eyebrow">BGG #${game.bgg_id}</p>
          <h1>${escapeHtml(game.title)}</h1>
          <p class="detail-subtitle">
            ${escapeHtml(game.original_title && game.original_title !== game.title ? game.original_title : "")}
          </p>

          <div class="detail-badges">
            <span class="badge">${type}</span>
            ${collection.own ? '<span class="badge">✓ Posseduto</span>' : ""}
            ${game.year_published ? `<span class="badge">${game.year_published}</span>` : ""}
          </div>

          <div class="fact-grid">
            ${fact("Giocatori", playerText(game))}
            ${fact("Durata", timeText(game))}
            ${fact("Rating BGG", bgg.average ? `★ ${formatNumber(bgg.average, 2)}` : "—")}
            ${fact("Complessità", bgg.average_weight ? `${formatNumber(bgg.average_weight, 2)} / 5` : "—")}
            ${fact("Ranking BGG", bgg.rank ? `#${formatNumber(bgg.rank, 0)}` : "—")}
            ${fact("Best players", bgg.best_players || "—")}
          </div>

          <h2 class="section-title">La mia copia</h2>
          <div class="fact-grid">
            ${fact("Lingua", collection.language || "—")}
            ${fact("Editore", collection.publishers || "—")}
            ${fact("Edizione", collection.version_nickname || collection.version_year || "—")}
            ${fact("Barcode", collection.barcode || "—")}
            ${fact("Posizione", collection.inventory_location || "—")}
            ${fact("Partite", collection.num_plays ?? "—")}
          </div>

          <h2 class="section-title">Dati BGG</h2>
          <div class="fact-grid">
            ${fact("Età consigliata", bgg.recommended_age || "—")}
            ${fact("Recommended players", bgg.recommended_players || "—")}
            ${fact("Dipendenza lingua", bgg.language_dependence || "—")}
          </div>

          <p style="margin-top:1.4rem">
            <a class="external-link" href="https://boardgamegeek.com/boardgame/${game.bgg_id}" target="_blank" rel="noopener noreferrer">
              Apri su BoardGameGeek ↗
            </a>
          </p>
        </article>
      </section>
    `;
    document.title = `${game.title} · BoardGameCompanion`;
  } catch (error) {
    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
      <div class="empty">Impossibile caricare il gioco: ${escapeHtml(error.message)}</div>
    `;
    showToast(error.message, true);
  }
}

async function route() {
  const match = window.location.pathname.match(/^\/games\/(\d+)\/?$/);
  if (match) {
    await renderDetail(Number(match[1]));
    return;
  }
  document.title = "BoardGameCompanion";
  await renderCatalog();
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-nav]");
  if (!link) return;
  const url = new URL(link.href, window.location.origin);
  if (url.origin !== window.location.origin) return;
  event.preventDefault();
  history.pushState({}, "", url.pathname);
  route();
  window.scrollTo({top: 0});
});

window.addEventListener("popstate", route);

importButton.addEventListener("click", () => {
  resetImportDialog();
  importDialog.showModal();
});

cancelImport.addEventListener("click", closeImportDialog);
closeImport.addEventListener("click", closeImportDialog);

importDialog.addEventListener("cancel", (event) => {
  if (importInProgress) {
    event.preventDefault();
  }
});

importDialog.addEventListener("close", resetImportDialog);

csvFile.addEventListener("change", () => {
  fileName.textContent = csvFile.files?.[0]?.name || "Nessun file selezionato";
});

importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = csvFile.files?.[0];
  if (!file || importInProgress) return;

  setImportBusy(true);
  importResult.hidden = true;

  try {
    const formData = new FormData();
    formData.append("file", file);
    const result = await api("/api/imports/bgg-csv", {method: "POST", body: formData});
    importResult.hidden = false;
    importResult.innerHTML = `
      <strong>Import completato.</strong><br>
      ${result.row_count} righe · ${result.created_count} nuovi ·
      ${result.updated_count} aggiornati · ${result.unchanged_count} invariati
    `;
    showToast("Collezione BGG aggiornata.");

    if (window.location.pathname === "/") {
      const stats = await api("/api/catalog/stats");
      renderStats(stats);
      state.offset = 0;
      await refreshCatalog();
    } else if (/^\/games\/\d+\/?$/.test(window.location.pathname)) {
      await route();
    }
  } catch (error) {
    importResult.hidden = false;
    importResult.textContent = error.message;
    showToast(error.message, true);
  } finally {
    setImportBusy(false);
  }
});

route();
