import {api, jsonRequest} from "../core/api.js";
import {compactGameTile, escapeHtml} from "../core/ui.js";

const DEFAULT_DYNAMIC = {
  owned: true,
  query: "",
  supports_players: "",
  ideal_players: "",
  max_minutes: "",
  weight: "",
  min_rating: "",
  personal_rating_min: "",
  category: "",
  mechanic: "",
  played: "",
  completed: "",
  sort: "title",
};

function filterField(label, control, hint = "") {
  return `<label class="list-filter-field"><span>${escapeHtml(label)}</span>${control}${hint ? `<small>${escapeHtml(hint)}</small>` : ""}</label>`;
}

function dynamicFilterForm(filters = {}) {
  const f = {...DEFAULT_DYNAMIC, ...filters};
  return `
    <div class="list-filter-grid">
      ${filterField("Titolo", `<input name="query" value="${escapeHtml(f.query || "")}" placeholder="Contiene…">`)}
      ${filterField("Giocatori", `<input name="supports_players" type="number" min="1" max="30" value="${escapeHtml(f.supports_players || "")}" placeholder="es. 4">`, "Supportati")}
      ${filterField("Ideale in", `<input name="ideal_players" type="number" min="1" max="30" value="${escapeHtml(f.ideal_players || "")}" placeholder="es. 2">`, "Poll BGG")}
      ${filterField("Durata massima", `<input name="max_minutes" type="number" min="1" max="1440" value="${escapeHtml(f.max_minutes || "")}" placeholder="minuti">`)}
      ${filterField("Complessità", `<select name="weight"><option value="">Qualsiasi</option><option value="light" ${f.weight === "light" ? "selected" : ""}>Leggera</option><option value="medium" ${f.weight === "medium" ? "selected" : ""}>Media</option><option value="heavy" ${f.weight === "heavy" ? "selected" : ""}>Impegnativa</option></select>`)}
      ${filterField("Rating BGG minimo", `<input name="min_rating" type="number" min="0" max="10" step=".1" value="${escapeHtml(f.min_rating || "")}">`)}
      ${filterField("La mia valutazione", `<select name="personal_rating_min"><option value="">Qualsiasi</option>${[1,2,3,4,5].map((v) => `<option value="${v}" ${String(f.personal_rating_min) === String(v) ? "selected" : ""}>${v}+ stelle</option>`).join("")}</select>`)}
      ${filterField("Categoria", `<input name="category" list="listCategories" value="${escapeHtml(f.category || "")}">`)}
      ${filterField("Meccanica", `<input name="mechanic" list="listMechanics" value="${escapeHtml(f.mechanic || "")}">`)}
      ${filterField("Giocato", `<select name="played"><option value="">Qualsiasi</option><option value="true" ${String(f.played) === "true" ? "selected" : ""}>Sì</option><option value="false" ${String(f.played) === "false" ? "selected" : ""}>Mai giocato</option></select>`)}
      ${filterField("Completato", `<select name="completed"><option value="">Qualsiasi</option><option value="true" ${String(f.completed) === "true" ? "selected" : ""}>Sì</option><option value="false" ${String(f.completed) === "false" ? "selected" : ""}>No</option></select>`)}
      ${filterField("Ordine", `<select name="sort"><option value="title" ${f.sort === "title" ? "selected" : ""}>Titolo</option><option value="personal_rating_desc" ${f.sort === "personal_rating_desc" ? "selected" : ""}>Mia valutazione</option><option value="rating_desc" ${f.sort === "rating_desc" ? "selected" : ""}>Rating BGG</option><option value="duration_asc" ${f.sort === "duration_asc" ? "selected" : ""}>Più brevi</option><option value="weight_asc" ${f.sort === "weight_asc" ? "selected" : ""}>Più leggeri</option><option value="played_desc" ${f.sort === "played_desc" ? "selected" : ""}>Giocati di recente</option></select>`)}
    </div>
    <datalist id="listCategories"></datalist>
    <datalist id="listMechanics"></datalist>
  `;
}

function filtersFromForm(form) {
  const data = new FormData(form);
  const filters = {owned: true};
  for (const [key, raw] of data.entries()) {
    let value = String(raw).trim();
    if (!value || key === "name" || key === "kind") continue;
    if (["supports_players", "ideal_players", "max_minutes", "personal_rating_min"].includes(key)) value = Number(value);
    if (key === "min_rating") value = Number(value);
    if (["played", "completed"].includes(key)) value = value === "true";
    filters[key] = value;
  }
  return filters;
}

function listCard(item) {
  const type = item.kind === "dynamic" ? "Dinamica" : "Manuale";
  const detail = item.kind === "dynamic"
    ? `${Object.keys(item.filters || {}).filter((key) => !["owned", "sort"].includes(key)).length} filtri`
    : `${item.manual_count || 0} giochi`;
  return `
    <article class="saved-list-card">
      <a href="/lists/${encodeURIComponent(item.id)}" data-nav>
        <span class="saved-list-icon" aria-hidden="true">${item.kind === "dynamic" ? "⌁" : "≡"}</span>
        <span><strong>${escapeHtml(item.name)}</strong><small>${type} · ${escapeHtml(detail)}</small></span>
      </a>
      <button class="icon-button delete-game-list" type="button" data-list-id="${escapeHtml(item.id)}" aria-label="Elimina ${escapeHtml(item.name)}">×</button>
    </article>
  `;
}

async function fillFacets(root) {
  try {
    const data = await api("/api/catalog/facets?limit=100");
    const categories = root.querySelector("#listCategories");
    const mechanics = root.querySelector("#listMechanics");
    if (categories) categories.innerHTML = (data.categories || []).map((x) => `<option value="${escapeHtml(x.name || x)}"></option>`).join("");
    if (mechanics) mechanics.innerHTML = (data.mechanics || []).map((x) => `<option value="${escapeHtml(x.name || x)}"></option>`).join("");
  } catch (_) {}
}

export async function renderListsView(app, {showToast, listId = null} = {}) {
  if (listId) return renderListDetail(app, listId, {showToast});
  app.innerHTML = `
    <section class="feature-page">
      <header class="feature-page-header">
        <div><p class="eyebrow">La mia ludoteca</p><h1>Liste</h1><p class="page-lead">Salva criteri che si aggiornano con la ludoteca, oppure crea raccolte manuali.</p></div>
      </header>
      <section class="feature-split">
        <form class="feature-card list-create-form" id="createGameListForm">
          <h2>Nuova lista</h2>
          <label class="list-filter-field"><span>Nome</span><input name="name" maxlength="120" required placeholder="Es. Brevi in 2"></label>
          <div class="segmented-control" id="listKindControl">
            <label><input type="radio" name="kind" value="dynamic" checked><span>Dinamica</span></label>
            <label><input type="radio" name="kind" value="manual"><span>Manuale</span></label>
          </div>
          <div id="dynamicListFields">${dynamicFilterForm()}</div>
          <button class="button button-primary" type="submit">Crea lista</button>
        </form>
        <section class="feature-card">
          <div class="feature-card-head"><h2>Le tue liste</h2><span id="listCount" class="quiet-pill">—</span></div>
          <div id="savedLists" class="saved-list-grid"><div class="skeleton"></div></div>
        </section>
      </section>
    </section>
  `;
  const form = app.querySelector("#createGameListForm");
  const fields = app.querySelector("#dynamicListFields");
  app.querySelectorAll('input[name="kind"]').forEach((input) => {
    input.addEventListener("change", () => {
      fields.hidden = form.elements.kind.value !== "dynamic";
    });
  });
  await fillFacets(app);

  async function refresh() {
    const data = await api("/api/lists");
    app.querySelector("#listCount").textContent = `${data.items.length} liste`;
    app.querySelector("#savedLists").innerHTML = data.items.length
      ? data.items.map(listCard).join("")
      : '<div class="empty-state"><strong>Nessuna lista salvata</strong><p>Le liste dinamiche si ricalcolano sempre sui dati correnti.</p></div>';
    app.querySelectorAll(".delete-game-list").forEach((button) => {
      button.addEventListener("click", async () => {
        await api(`/api/lists/${encodeURIComponent(button.dataset.listId)}`, {method: "DELETE"});
        showToast?.("Lista eliminata.");
        await refresh();
      });
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const kind = form.elements.kind.value;
      const created = await api("/api/lists", jsonRequest("POST", {
        name: form.elements.name.value.trim(),
        kind,
        filters: kind === "dynamic" ? filtersFromForm(form) : {},
      }));
      history.pushState({}, "", `/lists/${created.id}`);
      await renderListDetail(app, created.id, {showToast});
    } catch (error) {
      showToast?.(error.message, true);
    }
  });
  await refresh();
  document.title = "Liste · BoardGameCompanion";
}

async function renderListDetail(app, listId, {showToast} = {}) {
  app.innerHTML = '<section class="feature-page"><div class="skeleton"></div></section>';
  try {
    const data = await api(`/api/lists/${encodeURIComponent(listId)}`);
    app.innerHTML = `
      <section class="feature-page">
        <a class="detail-back" href="/lists" data-nav>← Tutte le liste</a>
        <header class="feature-page-header">
          <div><p class="eyebrow">${data.kind === "dynamic" ? "Lista dinamica" : "Lista manuale"}</p><h1>${escapeHtml(data.name)}</h1><p class="page-lead">${data.kind === "dynamic" ? "Ricalcolata sui dati correnti della ludoteca." : "Raccolta personale di titoli."}</p></div>
          <span class="feature-count">${data.count} giochi</span>
        </header>
        ${data.kind === "dynamic"
          ? `<details class="feature-card list-rules"><summary>Modifica criteri</summary><form id="editListForm">${dynamicFilterForm(data.filters)}<button class="button button-primary" type="submit">Salva criteri</button></form></details>`
          : `<section class="feature-card manual-list-adder">
               <div class="feature-card-head"><h2>Aggiungi gioco</h2><span class="quiet-pill">Catalogo</span></div>
               <label class="list-filter-field"><span>Cerca nella ludoteca</span><input id="manualListSearch" type="search" autocomplete="off" placeholder="Titolo del gioco…"></label>
               <div id="manualListSearchResults" class="manual-list-search-results"></div>
             </section>`}
        <div class="shared-game-grid" id="listGameGrid">${data.items.length ? data.items.map((game) => `
          <div class="manual-list-game-wrap">
            ${compactGameTile(game)}
            ${data.kind === "manual" ? `<button class="manual-list-remove" type="button" data-remove-list-game="${game.bgg_id}" aria-label="Rimuovi ${escapeHtml(game.title)} dalla lista">×</button>` : ""}
          </div>
        `).join("") : '<div class="empty-state"><strong>Nessun gioco corrisponde</strong><p>Modifica i criteri oppure aggiungi titoli alla lista manuale.</p></div>'}</div>
      </section>
    `;
    if (data.kind === "dynamic") {
      await fillFacets(app);
      const form = app.querySelector("#editListForm");
      form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await api(`/api/lists/${encodeURIComponent(listId)}`, jsonRequest("PATCH", {filters: filtersFromForm(form)}));
          showToast?.("Criteri aggiornati.");
          await renderListDetail(app, listId, {showToast});
        } catch (error) {
          showToast?.(error.message, true);
        }
      });
    } else {
      app.querySelectorAll("[data-remove-list-game]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await api(`/api/lists/${encodeURIComponent(listId)}/games/${encodeURIComponent(button.dataset.removeListGame)}`, {method: "DELETE"});
            showToast?.("Gioco rimosso dalla lista.");
            await renderListDetail(app, listId, {showToast});
          } catch (error) {
            showToast?.(error.message, true);
          }
        });
      });
      const search = app.querySelector("#manualListSearch");
      const results = app.querySelector("#manualListSearchResults");
      let timer = null;
      search?.addEventListener("input", () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(async () => {
          const q = search.value.trim();
          if (!q) {
            results.innerHTML = "";
            return;
          }
          try {
            const payload = await api(`/api/search?q=${encodeURIComponent(q)}&limit=8`);
            const games = (payload.groups || []).find((group) => group.type === "games")?.items || [];
            results.innerHTML = games.length
              ? games.map((item) => `
                  <button class="manual-list-search-result" type="button" data-add-list-game="${escapeHtml(String(item.id).replace("game:", ""))}">
                    <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.subtitle || "")}</small></span><b>+</b>
                  </button>
                `).join("")
              : '<span class="muted">Nessun gioco trovato.</span>';
            results.querySelectorAll("[data-add-list-game]").forEach((button) => {
              button.addEventListener("click", async () => {
                try {
                  await api(`/api/lists/${encodeURIComponent(listId)}/games`, jsonRequest("POST", {bgg_id: Number(button.dataset.addListGame)}));
                  showToast?.("Gioco aggiunto alla lista.");
                  await renderListDetail(app, listId, {showToast});
                } catch (error) {
                  showToast?.(error.message, true);
                }
              });
            });
          } catch (error) {
            results.innerHTML = `<span class="muted">${escapeHtml(error.message)}</span>`;
          }
        }, 160);
      });
    }
    document.title = `${data.name} · Liste · BoardGameCompanion`;
  } catch (error) {
    app.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}
