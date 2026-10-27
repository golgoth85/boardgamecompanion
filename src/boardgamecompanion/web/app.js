import {api} from "./api-client.js";
import {renderProviderPriority, readProviderPriority, setupCloudProviderControls, setupDescriptionPrompt, applyCloudProviderSettings, cloudProviderPayload} from "./ai-settings.js";
import {personalStatusLabel, starRatingMarkup} from "./personal-components.js";
import {shellRouteKey, shellSectionLabels} from "./routing.js";
import {
  CATALOG_ALL_LIMIT,
  catalogColumnSorts,
  catalogPageSizeValues,
  exploreState,
  initialCatalogColumns,
  initialCatalogPageSize,
  rankingState,
  state,
} from "./state.js";
import {coverSrc, escapeHtml, formatNumber, icon, initials, safeExternalHref} from "./ui-utils.js";
import {activateSettingsTab} from "./settings-ui.js";
import {exploreGroupArt} from "./explore-art.js";
import {bindDialogCancel, closeDialog, openDialog} from "./dialogs.js";

const app = document.querySelector("#app");
const appSidebar = document.querySelector("#appSidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const sidebarBackdrop = document.querySelector("#sidebarBackdrop");
const mobileSectionTitle = document.querySelector("#mobileSectionTitle");

function setSidebarOpen(open) {
  const expanded = Boolean(open);
  document.body.classList.toggle("sidebar-open", expanded);
  sidebarToggle?.setAttribute("aria-expanded", expanded ? "true" : "false");
  sidebarToggle?.setAttribute(
    "aria-label",
    expanded ? "Chiudi navigazione" : "Apri navigazione",
  );
  if (sidebarBackdrop) sidebarBackdrop.hidden = !expanded;
}

function closeSidebar() {
  setSidebarOpen(false);
}

function updateShellNavigation() {
  const routeKey = shellRouteKey();
  document.querySelectorAll("[data-route]").forEach((item) => {
    const active = item.dataset.route === routeKey;
    item.classList.toggle("is-active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  if (mobileSectionTitle) {
    mobileSectionTitle.textContent = shellSectionLabels[routeKey] || "Ludoteca";
  }
}
const importDialog = document.querySelector("#importDialog");
const importButton = document.querySelector("#importButton");
const importForm = document.querySelector("#importForm");
const csvFile = document.querySelector("#csvFile");
const fileName = document.querySelector("#fileName");
const importResult = document.querySelector("#importResult");
const submitImport = document.querySelector("#submitImport");
const cancelImport = document.querySelector("#cancelImport");
const closeImport = document.querySelector("#closeImport");
const copyDialog = document.querySelector("#copyDialog");
const copyForm = document.querySelector("#copyForm");
const copyDialogTitle = document.querySelector("#copyDialogTitle");
const copyDialogSubtitle = document.querySelector("#copyDialogSubtitle");
const closeCopyDialogButton = document.querySelector("#closeCopyDialog");
const cancelCopyDialog = document.querySelector("#cancelCopyDialog");
const saveCopy = document.querySelector("#saveCopy");
const copyBarcode = document.querySelector("#copyBarcode");
const copyLanguage = document.querySelector("#copyLanguage");
const copyEdition = document.querySelector("#copyEdition");
const copyPublishers = document.querySelector("#copyPublishers");
const copyVersionYear = document.querySelector("#copyVersionYear");
const copyLocation = document.querySelector("#copyLocation");
const copyAcquisitionDate = document.querySelector("#copyAcquisitionDate");
const copyAcquiredFrom = document.querySelector("#copyAcquiredFrom");
const copyPrice = document.querySelector("#copyPrice");
const copyCurrency = document.querySelector("#copyCurrency");
const copyCondition = document.querySelector("#copyCondition");
const copyNotes = document.querySelector("#copyNotes");
const copyResult = document.querySelector("#copyResult");
const scannerDialog = document.querySelector("#scannerDialog");
const closeScanner = document.querySelector("#closeScanner");
const scannerForm = document.querySelector("#scannerForm");
const scannerManualFallback = document.querySelector("#scannerManualFallback");
const scannerBarcode = document.querySelector("#scannerBarcode");
const lookupBarcode = document.querySelector("#lookupBarcode");
const scannerResult = document.querySelector("#scannerResult");
const cameraSection = document.querySelector("#cameraSection");
const scannerVideo = document.querySelector("#scannerVideo");
const toggleCamera = document.querySelector("#toggleCamera");
const cameraHint = document.querySelector("#cameraHint");
const scannerPhoto = document.querySelector("#scannerPhoto");
const scannerPhotoButton = document.querySelector("#scannerPhotoButton");
const settingsDialog = document.querySelector("#settingsDialog");
const settingsButton = document.querySelector("#settingsButton");
const settingsCollapseExpansions = document.querySelector("#settingsCollapseExpansions");
const settingsForm = document.querySelector("#settingsForm");
const closeSettings = document.querySelector("#closeSettings");
const cancelSettings = document.querySelector("#cancelSettings");
const saveSettings = document.querySelector("#saveSettings");
const referenceMinVotes = document.querySelector("#referenceMinVotes");
const referenceIncludeExpansions = document.querySelector("#referenceIncludeExpansions");
const referenceStatus = document.querySelector("#referenceStatus");
const referenceMinWishing = document.querySelector("#referenceMinWishing");
const referenceDailyBudget = document.querySelector("#referenceDailyBudget");
const referenceCrowdfundingGrace = document.querySelector("#referenceCrowdfundingGrace");
const saveTestSettings = document.querySelector("#saveTestSettings");
const settingsTabs = Array.from(document.querySelectorAll("[data-settings-tab]"));
const settingsPanels = Array.from(document.querySelectorAll("[data-settings-panel]"));
const bggUsername = document.querySelector("#bggUsername");
const bggApplicationToken = document.querySelector("#bggApplicationToken");
const bggClearToken = document.querySelector("#bggClearToken");
const clearTokenRow = document.querySelector("#clearTokenRow");
const bggTokenHint = document.querySelector("#bggTokenHint");
const bggSyncSettingsStatus = document.querySelector("#bggSyncSettingsStatus");
const bggSyncSettingsNow = document.querySelector("#bggSyncSettingsNow");
const youtubeApiKey = document.querySelector("#youtubeApiKey");
const youtubeApiKeyHint = document.querySelector("#youtubeApiKeyHint");
const youtubeClearApiKey = document.querySelector("#youtubeClearApiKey");
const clearYoutubeApiKeyRow = document.querySelector("#clearYoutubeApiKeyRow");
const apifyToken = document.querySelector("#apifyToken");
const apifyTokenHint = document.querySelector("#apifyTokenHint");
const apifyClearToken = document.querySelector("#apifyClearToken");
const clearApifyTokenRow = document.querySelector("#clearApifyTokenRow");
const apifyProviderState = document.querySelector("#apifyProviderState");
const verifyApifyToken = document.querySelector("#verifyApifyToken");
const apifyVerifyStatus = document.querySelector("#apifyVerifyStatus");
const settingsResult = document.querySelector("#settingsResult");
const ragEmbeddingOrder = document.querySelector("#ragEmbeddingOrder");
const ragGenerationOrder = document.querySelector("#ragGenerationOrder");
const ollamaUrl = document.querySelector("#ollamaUrl");
const ollamaEmbeddingModel = document.querySelector("#ollamaEmbeddingModel");
const ollamaGenerationModel = document.querySelector("#ollamaGenerationModel");
const lmstudioUrl = document.querySelector("#lmstudioUrl");
const lmstudioApiKey = document.querySelector("#lmstudioApiKey");
const lmstudioApiKeyHint = document.querySelector("#lmstudioApiKeyHint");
const lmstudioClearApiKey = document.querySelector("#lmstudioClearApiKey");
const clearLmstudioApiKeyRow = document.querySelector("#clearLmstudioApiKeyRow");
const lmstudioEmbeddingModel = document.querySelector("#lmstudioEmbeddingModel");
const lmstudioGenerationModel = document.querySelector("#lmstudioGenerationModel");
const lmstudioGenerationTimeout = document.querySelector("#lmstudioGenerationTimeout");
const lmstudioGenerationMaxTokens = document.querySelector("#lmstudioGenerationMaxTokens");
const lmstudioDisableThinking = document.querySelector("#lmstudioDisableThinking");
const lmstudioWolEnabled = document.querySelector("#lmstudioWolEnabled");
const lmstudioWolMac = document.querySelector("#lmstudioWolMac");
const lmstudioWolBroadcast = document.querySelector("#lmstudioWolBroadcast");
const lmstudioWolPort = document.querySelector("#lmstudioWolPort");
const lmstudioWakeButton = document.querySelector("#lmstudioWakeButton");
const geminiUrl = document.querySelector("#geminiUrl");
const geminiApiKey = document.querySelector("#geminiApiKey");
const geminiApiKeyHint = document.querySelector("#geminiApiKeyHint");
const geminiClearApiKey = document.querySelector("#geminiClearApiKey");
const clearGeminiApiKeyRow = document.querySelector("#clearGeminiApiKeyRow");
const geminiEmbeddingModel = document.querySelector("#geminiEmbeddingModel");
const geminiGenerationModel = document.querySelector("#geminiGenerationModel");
const documentDialog = document.querySelector("#documentDialog");
const documentForm = document.querySelector("#documentForm");
const documentDialogSubtitle = document.querySelector("#documentDialogSubtitle");
const closeDocumentDialogButton = document.querySelector("#closeDocumentDialog");
const cancelDocumentDialog = document.querySelector("#cancelDocumentDialog");
const saveDocument = document.querySelector("#saveDocument");
const documentFile = document.querySelector("#documentFile");
const documentFileName = document.querySelector("#documentFileName");
const documentType = document.querySelector("#documentType");
const documentLanguage = document.querySelector("#documentLanguage");
const documentTitle = document.querySelector("#documentTitle");
const documentVersion = document.querySelector("#documentVersion");
const documentEdition = document.querySelector("#documentEdition");
const documentSourceUrl = document.querySelector("#documentSourceUrl");
const documentOfficial = document.querySelector("#documentOfficial");
const documentResult = document.querySelector("#documentResult");
const globalSearchForm = document.querySelector("#globalSearchForm");
const globalSearchBar = document.querySelector("#globalSearchBar");
const mobileSearchButton = document.querySelector("#mobileSearchButton");
const globalSearchDialog = document.querySelector("#globalSearchDialog");
const globalSearchInput = document.querySelector("#globalSearchInput");
const globalSearchResults = document.querySelector("#globalSearchResults");
const globalSearchPopover = document.querySelector("#globalSearchPopover");
const closeGlobalSearch = document.querySelector("#closeGlobalSearch");
const notificationButton = document.querySelector("#notificationButton");
const mobileNotificationButton = document.querySelector("#mobileNotificationButton");
const notificationDialog = document.querySelector("#notificationDialog");
const notificationList = document.querySelector("#notificationList");
const notificationBadge = document.querySelector("#notificationBadge");
const mobileNotificationBadge = document.querySelector("#mobileNotificationBadge");
const closeNotificationDialog = document.querySelector("#closeNotificationDialog");
const diagnosticsPanel = document.querySelector("#diagnosticsPanel");
const toast = document.querySelector("#toast");

let exploreRequestController;
let currentExplorePayload = null;
let rankingRequestController;

function catalogSortHeader(label, key) {
  const [primary, secondary] = catalogColumnSorts[key];
  const active = state.sort === primary || state.sort === secondary;
  const ascending = state.sort.endsWith("_asc") || state.sort === "title";
  const next = state.sort === primary ? secondary : primary;
  const arrow = active ? (ascending ? "↑" : "↓") : "↕";
  const direction = active ? (ascending ? "crescente" : "decrescente") : "non ordinato";
  return `<button class="catalog-sort-button ${active ? "is-active" : ""}" type="button"
                  data-catalog-sort="${key}" data-next-sort="${next}"
                  aria-label="Ordina per ${escapeHtml(label)}: ${direction}">
            <span>${escapeHtml(label)}</span><i aria-hidden="true">${arrow}</i>
          </button>`;
}

function bindCatalogSortHeaders() {
  document.querySelectorAll("[data-catalog-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      state.sort = button.dataset.nextSort || "title";
      state.offset = 0;
      syncCatalogSortControls();
      refreshCatalog();
    });
  });
}

const catalogSortFieldLabels = Object.freeze({
  title: "Titolo",
  players: "Giocatori",
  age: "Età",
  duration: "Durata",
  weight: "Peso",
  rating: "Rating BGG",
});

function currentCatalogSortField() {
  for (const [key, [primary, secondary]] of Object.entries(catalogColumnSorts)) {
    if (state.sort === primary || state.sort === secondary) return key;
  }
  return "title";
}

function catalogSortAscending() {
  return state.sort === "title" || state.sort.endsWith("_asc");
}

function syncCatalogSortControls() {
  const field = currentCatalogSortField();
  const select = document.querySelector("#sortField");
  if (select) select.value = field;
  const button = document.querySelector("#sortDirection");
  if (!button) return;
  const ascending = catalogSortAscending();
  button.dataset.direction = ascending ? "asc" : "desc";
  button.setAttribute("aria-label", `Ordinamento ${ascending ? "crescente" : "decrescente"}`);
  button.setAttribute("title", ascending ? "Ordine crescente" : "Ordine decrescente");
  button.innerHTML = icon(ascending ? "caret-up" : "caret-down");
}

let searchTimer;
let catalogRequestController;
let currentCatalogData = null;
let importInProgress = false;
let settingsBusy = false;
let currentBggSettings = null;
let currentRagSettings = null;
setupCloudProviderControls({api, generationControl: ragGenerationOrder, onSelect: (label) => showToast(`${label} selezionato. Salva impostazioni per applicare.`)});
setupDescriptionPrompt({api});
let currentYoutubeSettings = null;
let currentCrowdfundingSettings = null;
let copyBusy = false;
let editingCopyId = null;
let editingCopyBggId = null;
let scannerBusy = false;
let scannerStream = null;
let scannerFrameHandle = null;
let scannerDetector = null;
let scannerFallbackControls = null;
let scannerDetectionLocked = false;
let scannerBackend = null;
let scannerStartId = 0;
let scannerImportCount = 0;
let documentBusy = false;
let documentBggId = null;
let metadataBackfillRunning = false;

// Human-reviewed web search: no Google API, scraping, or automatic PDF trust.
export function googleRulebookSearchUrl(title) {
  // URL encoding protects the href; this separately keeps untrusted game names
  // inside one quoted Google phrase (including names containing site: or quotes).
  const gameTitle = String(title ?? "")
    .normalize("NFC")
    .replace(/["\\\u201C\u201D\u201E\u201F\uFF02\u0000-\u001F\u007F-\u009F\u2028\u2029]/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
  const query = gameTitle
    ? `"${gameTitle}" regolamento italiano pdf`
    : "regolamento italiano pdf";
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
}

function formatCampaignMoney(value, currency) {
  const amount = Number(value);
  const code = String(currency || "").toUpperCase();
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat("it-IT", {
      style: "currency", currency: code, maximumFractionDigits: 0,
    }).format(amount);
  } catch (_) {
    return `${formatNumber(amount, 0)} ${code}`.trim();
  }
}

function formatTutorialDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "";
  const total = Math.round(value);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours) return `${hours} h ${minutes} min`;
  return `${minutes} min`;
}

function tutorialVideoCard(item) {
  const language = String(item.language || "en").toUpperCase();
  const kind = item.is_official ? "Ufficiale" : "Community";
  const duration = formatTutorialDuration(item.duration_seconds);
  const views = Number(item.view_count || 0);
  const meta = [
    item.channel_title || "YouTube",
    duration || null,
    views ? `${formatNumber(views, 0)} visualizzazioni` : null,
  ].filter(Boolean).join(" · ");
  return `
    <article class="tutorial-video-card">
      <div class="tutorial-video-frame">
        <iframe
          src="${escapeHtml(item.embed_url)}"
          title="${escapeHtml(item.title || "Video tutorial")}"
          loading="lazy"
          referrerpolicy="strict-origin-when-cross-origin"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowfullscreen></iframe>
      </div>
      <div class="tutorial-video-body">
        <div class="document-badges">
          <span class="badge">${escapeHtml(language)}</span>
          <span class="badge ${item.is_official ? "document-official" : "document-unofficial"}">${kind}</span>
        </div>
        <p class="muted">${escapeHtml(meta)}</p>
      </div>
    </article>
  `;
}

function runWhenIdle(callback, timeout = 1500) {
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(() => callback(), {timeout});
    return;
  }
  window.setTimeout(callback, 250);
}

function playerText(game) {
  const min = game.players?.min;
  const max = game.players?.max;
  if (!min && !max) return "—";
  return min === max ? String(min) : `${min ?? "?"}–${max ?? "?"}`;
}

const PLAYER_VERDICTS = {
  best: "Ideale",
  recommended: "Consigliato",
  not_recommended: "Sconsigliato",
};

// Expands BGG lists such as "2, 3", "2-4" or "5+" into player counts.
function playerCountSet(text, max) {
  const counts = new Set();
  for (const part of String(text || "").split(",")) {
    const range = part.trim().match(/^(\d+)\s*(?:[-–]\s*(\d+)|(\+))?$/);
    if (!range) continue;
    const low = Number(range[1]);
    const high = range[2] ? Number(range[2]) : range[3] ? Math.max(low, max || low) : low;
    for (let count = low; count <= high && count - low < 30; count += 1) counts.add(count);
  }
  return counts;
}

// One entry per player count in the box range, from the BGG community poll
// when stored, otherwise from the best/recommended summaries.
function playerChartRows(game, poll) {
  const min = Number(game.players?.min) || 0;
  const max = Number(game.players?.max) || min;
  if (!min) return [];
  const last = Math.min(max, min + 9);
  const votesByCount = new Map(
    (Array.isArray(poll) ? poll : [])
      .filter((row) => /^\d+$/.test(String(row?.players || "")))
      .map((row) => [Number(row.players), row])
  );
  const best = playerCountSet(game.bgg?.best_players, max);
  const recommended = playerCountSet(game.bgg?.recommended_players, max);
  const rows = [];
  for (let count = min; count <= last; count += 1) {
    const votes = votesByCount.get(count);
    const total = votes ? votes.best + votes.recommended + votes.not_recommended : 0;
    let verdict = "";
    if (total) {
      if (votes.best > 0 && votes.best >= votes.recommended && votes.best >= votes.not_recommended) verdict = "best";
      else if (votes.best + votes.recommended > votes.not_recommended) verdict = "recommended";
      else verdict = "not_recommended";
    } else if (best.size || recommended.size) {
      verdict = best.has(count) ? "best" : recommended.has(count) ? "recommended" : "not_recommended";
    }
    rows.push({
      label: count === last && last < max ? `${count}+` : String(count),
      verdict,
      total,
      shares: total
        ? ["best", "recommended", "not_recommended"].map((key) => Math.round((votes[key] / total) * 100))
        : null,
    });
  }
  return rows;
}

function playerChartMarkup(game, poll) {
  const rows = playerChartRows(game, poll);
  if (!rows.length || !rows.some((row) => row.verdict)) {
    return `<div><dt>Giocatori</dt><dd>${escapeHtml(playerText(game))}</dd></div>`;
  }
  const withVotes = rows.some((row) => row.shares);
  const summary = rows
    .map((row) => `${row.label}: ${(PLAYER_VERDICTS[row.verdict] || "nessun dato").toLowerCase()}`)
    .join(", ");
  const tip = withVotes ? `
    <div class="player-chart-tip" role="tooltip" id="playerChartTip">
      <strong>Sondaggio BGG</strong>
      <table>
        <thead><tr><th scope="col">Giocatori</th><th scope="col">Ideale</th><th scope="col">Consigliato</th><th scope="col">Sconsigliato</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr class="is-${row.verdict || "unknown"}">
              <th scope="row">${escapeHtml(row.label)}</th>
              ${row.shares ? row.shares.map((share) => `<td>${share}%</td>`).join("") : '<td colspan="3">—</td>'}
            </tr>
          `).join("")}
        </tbody>
      </table>
      <small>Fino a ${formatNumber(Math.max(...rows.map((row) => row.total)), 0)} voti per numero di giocatori</small>
    </div>
  ` : "";
  return `
    <div class="player-chart" ${withVotes ? 'tabindex="0" aria-describedby="playerChartTip"' : ""}>
      <dt>Giocatori</dt>
      <dd>
        <ol class="player-chart-counts" aria-label="${escapeHtml(`Numero di giocatori secondo BGG: ${summary}`)}">
          ${rows.map((row) => `
            <li class="player-chart-count is-${row.verdict || "unknown"}" title="${escapeHtml(`${row.label} giocatori: ${PLAYER_VERDICTS[row.verdict] || "nessun dato"}`)}">${escapeHtml(row.label)}</li>
          `).join("")}
        </ol>
      </dd>
      ${tip}
    </div>
  `;
}

// BGG language dependence poll, summarised in four levels.
function languageDependenceText(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return "—";
  if (text.startsWith("no necessary")) return "Nessuna";
  if (text.startsWith("some necessary")) return "Leggera";
  if (text.startsWith("moderate")) return "Moderata";
  if (text.startsWith("extensive") || text.startsWith("unplayable")) return "Estesa";
  return String(value);
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

let globalSearchTimer = null;
let latestGlobalSearchQuery = "";
let wishlistIndex = new Map();

function wishlistKey(sourceKind, sourceKey) {
  return `${String(sourceKind || "").toLowerCase()}:${String(sourceKey || "")}`;
}

async function refreshWishlistIndex() {
  const payload = await api("/api/wishlist");
  wishlistIndex = new Map(
    (payload.items || []).map((item) => [
      wishlistKey(item.source_kind, item.source_key),
      item,
    ]),
  );
  return payload;
}

function wishlistEntry(sourceKind, sourceKey) {
  return wishlistIndex.get(wishlistKey(sourceKind, sourceKey)) || null;
}

async function toggleWishlistButton(button) {
  const sourceKind = String(button.dataset.wishlistSourceKind || "");
  const sourceKey = String(button.dataset.wishlistSourceKey || "");
  const existing = wishlistEntry(sourceKind, sourceKey);
  button.disabled = true;
  try {
    if (existing) {
      await api(`/api/wishlist/${encodeURIComponent(existing.id)}`, {method: "DELETE"});
      wishlistIndex.delete(wishlistKey(sourceKind, sourceKey));
      button.classList.remove("is-active");
      if (button.classList.contains("wishlist-heart")) {
        button.innerHTML = `<span aria-hidden="true">${icon("heart")}</span>`;
        button.setAttribute("aria-label", "Aggiungi alla wishlist");
        button.setAttribute("title", "Aggiungi alla wishlist");
      } else {
        button.innerHTML = `${icon("heart")}<span>Wishlist</span>`;
      }
      button.dataset.wishlistItemId = "";
      showToast("Rimosso dalla Wishlist.");
      if (/^\/wishlist\/?$/.test(window.location.pathname)) void renderWishlist();
      return;
    }
    const body = {
      source_kind: sourceKind,
      source_key: sourceKey,
      title: button.dataset.wishlistTitle || "Titolo",
      bgg_id: button.dataset.wishlistBggId
        ? Number(button.dataset.wishlistBggId)
        : null,
      year_published: button.dataset.wishlistYear
        ? Number(button.dataset.wishlistYear)
        : null,
      cover_url: button.dataset.wishlistCover || null,
      target_url: button.dataset.wishlistTarget || null,
      metadata: {
        ...(button.dataset.wishlistPlatform ? {platform: button.dataset.wishlistPlatform} : {}),
        ...(button.dataset.wishlistMeta ? JSON.parse(button.dataset.wishlistMeta) : {}),
      },
    };
    const created = await api("/api/wishlist", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    wishlistIndex.set(wishlistKey(sourceKind, sourceKey), created);
    button.classList.add("is-active");
    if (button.classList.contains("wishlist-heart")) {
      button.innerHTML = `<span aria-hidden="true">${icon("heart-fill")}</span>`;
      button.setAttribute("aria-label", "Rimuovi dalla wishlist");
      button.setAttribute("title", "Rimuovi dalla wishlist");
    } else {
      button.innerHTML = `${icon("heart-fill")}<span>In Wishlist</span>`;
    }
    button.dataset.wishlistItemId = created.id;
    showToast("Aggiunto alla Wishlist.");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function bindWishlistActions(root = document) {
  root.querySelectorAll?.("[data-wishlist-source-kind]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void toggleWishlistButton(button);
    });
  });
}

function openGlobalSearchDialog() {
  openDialog(globalSearchDialog, {focus: globalSearchInput, select: true});
}

function hideGlobalSearchPopover() {
  if (globalSearchPopover) globalSearchPopover.hidden = true;
}

function closeGlobalSearchDialog() {
  closeDialog(globalSearchDialog);
}

async function performGlobalSearch(query, target) {
  latestGlobalSearchQuery = query;
  if (!query) {
    target.innerHTML = '<p class="muted">Scrivi almeno un carattere. Scorciatoia: Ctrl+K.</p>';
    return;
  }
  target.innerHTML = '<p class="muted">Ricerca…</p>';
  try {
    const [payload, referencePayload] = await Promise.all([
      api(`/api/search?q=${encodeURIComponent(query)}&limit=8`),
      api(`/api/reference/search?q=${encodeURIComponent(query)}&limit=8`).catch(() => ({items: []})),
    ]);
    if (query !== latestGlobalSearchQuery) return;
    const reference = (referencePayload.items || []).filter((item) => !item.in_catalog);
    const games = payload.groups?.games || [];
    const sections = payload.groups?.sections || [];
    const wishlist = payload.groups?.wishlist || [];
    const lists = payload.groups?.lists || [];
    const rulebooks = payload.groups?.rulebooks || [];
    const crowdfunding = payload.groups?.crowdfunding || [];
    target.innerHTML = `
      ${games.length ? `
        <section class="global-search-group">
          <h3>Giochi</h3>
          ${games.map((game) => `
            <a class="global-search-result" href="/games/${game.bgg_id}" data-nav>
              <span class="global-search-cover">
                ${game.bgg_metadata?.cover_url
                  ? `<img src="${coverSrc(game.bgg_id)}" alt="" referrerpolicy="no-referrer">`
                  : `<span>${escapeHtml(initials(game.title))}</span>`}
              </span>
              <span><strong>${escapeHtml(game.title)}</strong><small>${game.year_published || "—"} · ${escapeHtml(personalStatusLabel(game.progress))}</small></span>
            </a>
          `).join("")}
        </section>
      ` : ""}
      ${reference.length ? `
        <section class="global-search-group">
          <h3>Catalogo BGG</h3>
          ${reference.map(referenceSearchResult).join("")}
        </section>
      ` : ""}
      ${wishlist.length ? `
        <section class="global-search-group">
          <h3>Wishlist</h3>
          ${wishlist.map((item) => {
            const target = item.bgg_id
              ? `/wishlist?focus=${encodeURIComponent(item.id)}`
              : safeExternalHref(item.target_url, "/wishlist");
            const internal = String(target).startsWith("/");
            return `
              <a class="global-search-result" href="${escapeHtml(target)}"
                 ${internal ? "data-nav" : 'target="_blank" rel="noopener noreferrer"'}>
                <span class="global-search-cover">
                  ${item.cover_url
                    ? `<img src="${escapeHtml(coverSrc(item.bgg_id, item.cover_url))}" alt="" referrerpolicy="no-referrer">`
                    : `<span>${icon("heart")}</span>`}
                </span>
                <span><strong>${escapeHtml(item.title)}</strong><small>${item.source_kind === "crowdfunding" ? "Crowdfunding" : "Wishlist BGG"}</small></span>
              </a>
            `;
          }).join("")}
        </section>
      ` : ""}
      ${lists.length ? `
        <section class="global-search-group">
          <h3>Liste</h3>
          ${lists.map((item) => `
            <a class="global-search-result is-section" href="/lists?focus=${encodeURIComponent(item.id)}" data-nav>
              <span aria-hidden="true">${icon("list")}</span>
              <span><strong>${escapeHtml(item.name)}</strong><small>${item.kind === "smart" ? "Lista dinamica" : "Lista manuale"}</small></span>
            </a>
          `).join("")}
        </section>
      ` : ""}
      ${rulebooks.length ? `
        <section class="global-search-group">
          <h3>Regolamenti</h3>
          ${rulebooks.map((item) => `
            <a class="global-search-result is-section" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
              <span aria-hidden="true">${icon("book")}</span>
              <span><strong>${escapeHtml(item.game_title)}</strong><small>${escapeHtml(item.title || "Regolamento")} · ${escapeHtml(item.language || "—")}</small></span>
            </a>
          `).join("")}
        </section>
      ` : ""}
      ${crowdfunding.length ? `
        <section class="global-search-group">
          <h3>Crowdfunding</h3>
          ${crowdfunding.map((item) => {
            const target = /^https?:\/\//i.test(String(item.project_url || ""))
              ? item.project_url : "/crowdfunding";
            const external = target !== "/crowdfunding";
            return `
              <a class="global-search-result is-section" href="${escapeHtml(target)}"
                ${external ? 'target="_blank" rel="noopener noreferrer"' : "data-nav"}>
                <span aria-hidden="true">${icon("external")}</span>
                <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.platform || "Crowdfunding")}</small></span>
              </a>
            `;
          }).join("")}
        </section>
      ` : ""}
      ${sections.length ? `
        <section class="global-search-group">
          <h3>Sezioni</h3>
          ${sections.map((item) => `
            <a class="global-search-result is-section" href="${escapeHtml(item.url)}" data-nav>
              <span aria-hidden="true">${icon("arrow-right")}</span>
              <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.description)}</small></span>
            </a>
          `).join("")}
        </section>
      ` : ""}
      ${!games.length && !reference.length && !wishlist.length && !lists.length && !rulebooks.length && !crowdfunding.length && !sections.length
        ? '<div class="empty">Nessun risultato.</div>'
        : ""}
    `;
    bindWishlistActions(target);
    bindReferenceActions(target);
  } catch (error) {
    target.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function referenceActionButtons(item) {
  if (item.owned) {
    return `<span class="collection-icon-button is-active" role="img" aria-label="In ludoteca" title="In ludoteca">${icon("check")}</span>`;
  }
  const key = String(item.bgg_id);
  const wishlist = wishlistEntry("bgg", key);
  const thumbnail = item.thumbnail_url || item.image_url || "";
  return `
    <button class="wishlist-heart ${wishlist ? "is-active" : ""}" type="button"
            aria-label="${wishlist ? "Rimuovi dalla wishlist" : "Aggiungi alla wishlist"}"
            title="${wishlist ? "Rimuovi dalla wishlist" : "Aggiungi alla wishlist"}"
            data-wishlist-source-kind="bgg"
            data-wishlist-source-key="${escapeHtml(key)}"
            data-wishlist-item-id="${escapeHtml(wishlist?.id || "")}"
            data-wishlist-bgg-id="${Number(item.bgg_id)}"
            data-wishlist-title="${escapeHtml(item.name)}"
            data-wishlist-year="${escapeHtml(String(item.year_published || ""))}"
            data-wishlist-cover="${escapeHtml(thumbnail)}"
            data-wishlist-target="https://boardgamegeek.com/boardgame/${Number(item.bgg_id)}">
      <span aria-hidden="true">${wishlist ? icon("heart-fill") : icon("heart")}</span>
    </button>
    <button class="collection-icon-button ${item.in_catalog ? "is-active" : ""}" type="button"
            data-reference-collection="${Number(item.bgg_id)}"
            ${item.in_catalog ? "disabled" : ""}
            aria-label="${item.in_catalog ? "In collezione" : `Aggiungi ${escapeHtml(item.name)} alla collezione`}"
            title="${item.in_catalog ? "In collezione" : "Aggiungi alla collezione"}">${icon(item.in_catalog ? "check" : "shelf")}</button>
  `;
}

function referenceSearchResult(item) {
  const details = [
    item.year_published || "—",
    item.is_expansion ? "Espansione" : null,
    item.rank ? `#${formatNumber(item.rank, 0)} BGG` : null,
    `${formatNumber(item.users_rated, 0)} voti`,
  ].filter(Boolean).join(" · ");
  return `
    <div class="global-search-result reference-result">
      <span class="global-search-cover">
        ${item.thumbnail_url
          ? `<img src="${coverSrc(item.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<span>${escapeHtml(initials(item.name))}</span>`}
      </span>
      <a class="reference-open" href="/bgg/${Number(item.bgg_id)}" data-nav>
        <strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(details)}</small>
      </a>
      <span class="reference-result-actions">${referenceActionButtons(item)}</span>
    </div>
  `;
}

// Catalog titles outside the Ludoteca: BGG data, wishlist and collection, Italian description.
function referenceDetailGame(item) {
  const details = item.details || {};
  return referenceAsGame({
    ...item,
    players: {min: details.min_players, max: details.max_players},
    play_time: {playing: details.playing_time, min: details.min_play_time, max: details.max_play_time},
    average_weight: details.bgg_average_weight,
    recommended_age: details.bgg_recommended_age,
    best_players: details.bgg_best_players,
    recommended_players: details.bgg_recommended_players,
  });
}

function referenceDescriptionMarkup(item) {
  if (item.description) {
    return '<div class="game-description-text reference-description-text" id="referenceDescriptionText" aria-busy="true">Sto traducendo la descrizione…</div>';
  }
  const note = item.detail_error === "no_token"
    ? "Descrizione non disponibile: configura il token BGG nelle impostazioni."
    : item.detail_error
      ? "Descrizione non disponibile: BGG non ha risposto, riprova più tardi."
      : "Descrizione non disponibile.";
  return `<div class="game-description-text" id="referenceDescriptionText">${escapeHtml(note)}</div>`;
}

async function loadReferenceDescription(bggId) {
  const node = document.querySelector("#referenceDescriptionText");
  if (!node?.isConnected) return;
  try {
    const result = await api(`/api/reference/${encodeURIComponent(bggId)}/description-it/translate`, {method: "POST"});
    const text = result.translation?.translated_text;
    if (text && node.isConnected) node.textContent = text;
  } catch (error) {
    if (node.isConnected) node.textContent = `Traduzione non disponibile: ${error.message}`;
  } finally {
    node?.removeAttribute("aria-busy");
  }
}

async function renderReferenceDetail(bggId) {
  app.innerHTML = `
    <a class="detail-back" href="/bgg" data-nav>← Torna al catalogo</a>
    <section class="game-page game-page-loading">
      <div class="game-summary-rail"><div class="skeleton"></div></div>
      <div class="game-main"><div class="skeleton"></div></div>
    </section>
  `;
  const requestedPath = window.location.pathname;
  try {
    const item = await api(`/api/reference/${encodeURIComponent(bggId)}`);
    if (window.location.pathname !== requestedPath) return;
    if (item.owned) {
      history.replaceState({}, "", `/games/${item.bgg_id}`);
      await renderDetail(Number(item.bgg_id));
      return;
    }

    const game = referenceDetailGame(item);
    const details = item.details || {};
    const type = item.is_expansion ? "Espansione" : "Gioco base";
    const cover = item.image_url || item.thumbnail_url;
    app.innerHTML = `
      <a class="detail-back" href="/bgg" data-nav>← Torna al catalogo</a>

      <section class="game-page game-centric-detail">
        <aside class="game-summary-rail" aria-label="Riepilogo gioco">
          <div class="game-summary-cover">
            <div class="detail-cover">
              ${cover
                ? `<img class="cover-image" src="${coverSrc(item.bgg_id)}" alt="Cover di ${escapeHtml(item.name)}" referrerpolicy="no-referrer">`
                : `<span class="cover-initials">${escapeHtml(initials(item.name))}</span>`}
              ${bggRatingBadge(game.bgg)}
            </div>
          </div>

          <div class="game-summary-card">
            <div class="game-summary-badges">
              <span class="badge">${type}</span>
              ${item.year_published ? `<span class="badge">${item.year_published}</span>` : ""}
            </div>
            <dl class="game-summary-list game-facts-primary">
              ${playerChartMarkup(game, details.player_poll)}
              <div><dt>Età ufficiale</dt><dd>${escapeHtml(ageText(game))}</dd></div>
              <div><dt>Durata</dt><dd>${escapeHtml(timeText(game))}</dd></div>
              <div><dt>Complessità</dt><dd>${game.bgg.average_weight ? `${formatNumber(game.bgg.average_weight, 2)} / 5` : "—"}</dd></div>
            </dl>
            <a class="external-link game-bgg-link"
               href="https://boardgamegeek.com/boardgame/${item.bgg_id}"
               target="_blank" rel="noopener noreferrer">Apri su BoardGameGeek ${icon("external")}</a>
          </div>
        </aside>

        <article class="game-main detail-main">
          <header class="game-header game-header-player">
            <div class="game-title-block">
              <h1>${escapeHtml(item.name)}</h1>
              <span class="game-title-meta">BGG #${item.bgg_id}</span>
            </div>
            <div class="game-primary-actions reference-page-actions">
              ${referenceActionButtons(item)}
            </div>
          </header>

          <section class="game-description-panel">
            ${referenceDescriptionMarkup(item)}
          </section>
        </article>
      </section>
    `;
    bindWishlistActions(app);
    bindReferenceActions(app);
    if (item.description) void loadReferenceDescription(item.bgg_id);
    document.title = `${item.name} · BoardGameCompanion`;
  } catch (error) {
    app.innerHTML = `
      <a class="detail-back" href="/bgg" data-nav>← Torna al catalogo</a>
      <div class="empty">Impossibile caricare il gioco: ${escapeHtml(error.message)}</div>
    `;
    showToast(error.message, true);
  }
}

function bindReferenceActions(root = document) {
  root.querySelectorAll?.("[data-reference-collection]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      button.disabled = true;
      try {
        await api(`/api/reference/${encodeURIComponent(button.dataset.referenceCollection)}/collection`, {method: "POST"});
        button.classList.add("is-active");
        button.innerHTML = icon("check");
        button.setAttribute("aria-label", "In collezione");
        button.title = "In collezione";
        showToast("Aggiunto alla collezione.");
      } catch (error) {
        button.disabled = false;
        showToast(error.message, true);
      }
    });
  });
}

function setNotificationBadge(count) {
  const value = Math.max(0, Number(count) || 0);
  for (const badge of [notificationBadge, mobileNotificationBadge]) {
    if (!badge) continue;
    badge.hidden = value === 0;
    badge.textContent = value > 99 ? "99+" : String(value);
  }
}

async function refreshNotificationBadge() {
  try {
    const payload = await api("/api/notifications?unread_only=true&limit=1");
    setNotificationBadge(payload.unread_count || 0);
  } catch (_) {
    setNotificationBadge(0);
  }
}

async function openNotificationCenter() {
  if (!notificationDialog || !notificationList) return;
  openDialog(notificationDialog);
  notificationList.innerHTML = '<p class="muted">Caricamento…</p>';
  try {
    const payload = await api("/api/notifications?limit=100");
    setNotificationBadge(payload.unread_count || 0);
    const items = payload.items || [];
    notificationList.innerHTML = items.length
      ? items.map((item) => {
          const rawTarget = String(item.target_url || "");
          const internal = rawTarget.startsWith("/");
          const target = internal ? rawTarget : safeExternalHref(rawTarget);
          return `
            <a class="notification-item ${item.read ? "" : "is-unread"}"
               href="${escapeHtml(target)}"
               ${internal ? "data-nav" : 'target="_blank" rel="noopener noreferrer"'}
               data-notification-id="${escapeHtml(item.id)}">
              <span class="notification-kind" aria-hidden="true">${item.category === "expansion" ? '<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#i-plus"/></svg>' : '<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#i-megaphone"/></svg>'}</span>
              <span>
                <strong>${escapeHtml(item.title)}</strong>
                <small>${escapeHtml(item.body)}</small>
              </span>
            </a>
          `;
        }).join("")
      : '<div class="empty"><strong>Nessuna notifica.</strong><span>Le novità rilevanti compariranno qui.</span></div>';
    notificationList.querySelectorAll("[data-notification-id]").forEach((item) => {
      item.addEventListener("click", () => {
        void api(`/api/notifications/${encodeURIComponent(item.dataset.notificationId)}`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({read: true}),
        }).then(() => refreshNotificationBadge()).catch(() => {});
      });
    });
  } catch (error) {
    notificationList.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function refreshDiagnostics() {
  if (!diagnosticsPanel) return;
  diagnosticsPanel.innerHTML = '<span class="muted">Aggiornamento diagnostica…</span>';
  try {
    const payload = await api("/api/diagnostics");
    const bgg = payload.bgg || {};
    const assistant = payload.assistant || {};
    const crowdfunding = payload.crowdfunding || {};
    const suggestions = payload.suggestions || {};
    const rulebooks = payload.rulebooks || {};
    const personal = payload.personal || {};
    const cacheLabel = (cache) => {
      if (!cache?.exists) return "Assente";
      const date = cache.updated_at
        ? new Date(cache.updated_at).toLocaleString("it-IT")
        : "data ignota";
      return `${date} · ${formatNumber(cache.bytes || 0, 0)} B`;
    };
    const statusSummary = (states = {}) => Object.entries(states)
      .map(([key, value]) => `${key}: ${value}`)
      .join(" · ") || "Nessun dato";

    diagnosticsPanel.innerHTML = `
      <div class="diagnostics-section">
        <h4>Sistema</h4>
        <dl class="diagnostics-grid">
          <div><dt>Schema DB</dt><dd>${escapeHtml(String(payload.schema_version ?? "—"))}</dd></div>
          <div><dt>BGG</dt><dd>${bgg.configured ? "Configurato" : "Non configurato"}</dd></div>
          <div><dt>Sync collezione</dt><dd>${bgg.collection_sync_configured ? "Configurata" : "Non configurata"}</dd></div>
          <div><dt>Ultima sync BGG</dt><dd>${escapeHtml(bgg.last_success_at || "Mai")}</dd></div>
          <div class="diagnostics-wide"><dt>Ultimo errore BGG</dt><dd>${escapeHtml(bgg.last_error || "Nessuno")}</dd></div>
        </dl>
      </div>
      <div class="diagnostics-section">
        <h4>Assistente e indicizzazione</h4>
        <dl class="diagnostics-grid">
          <div><dt>Generazione</dt><dd>${escapeHtml((assistant.generation_order || []).join(" → ") || "—")}</dd></div>
          <div><dt>Embedding</dt><dd>${escapeHtml((assistant.embedding_order || []).join(" → ") || "—")}</dd></div>
          <div><dt>YouTube</dt><dd>${assistant.youtube_configured ? "Configurato" : "Non configurato"}</dd></div>
          <div><dt>Job documenti</dt><dd>${escapeHtml(statusSummary(rulebooks.indexing))}</dd></div>
          <div class="diagnostics-wide"><dt>Discovery regolamenti</dt><dd>${escapeHtml(statusSummary(rulebooks.discovery))}</dd></div>
        </dl>
      </div>
      <div class="diagnostics-section">
        <h4>Cache e provider</h4>
        <dl class="diagnostics-grid">
          <div><dt>Suggerimenti</dt><dd>${escapeHtml(cacheLabel(suggestions.cache))}</dd></div>
          <div><dt>Editoriale suggerimenti</dt><dd>${escapeHtml(cacheLabel(suggestions.editorial_cache))}</dd></div>
          <div><dt>Crowdfunding</dt><dd>${escapeHtml(cacheLabel(crowdfunding.cache))}</dd></div>
          <div><dt>Kickstarter</dt><dd>${crowdfunding.kickstarter_configured ? "Configurato" : "Non configurato"}</dd></div>
        </dl>
      </div>
      <div class="diagnostics-section">
        <h4>Stato personale</h4>
        <dl class="diagnostics-grid">
          <div><dt>Liste</dt><dd>${formatNumber(personal.list_count || 0, 0)}</dd></div>
          <div><dt>Wishlist</dt><dd>${formatNumber(personal.wishlist_count || 0, 0)}</dd></div>
          <div><dt>Notifiche</dt><dd>${formatNumber(personal.notifications_total || 0, 0)}</dd></div>
          <div><dt>Non lette</dt><dd>${formatNumber(personal.notifications_unread || 0, 0)}</dd></div>
          <div><dt>Scan espansioni</dt><dd>${formatNumber(personal.expansion_scans || 0, 0)}</dd></div>
          <div><dt>Baseline espansioni</dt><dd>${formatNumber(personal.expansion_baselines || 0, 0)}</dd></div>
          <div><dt>Errori scan espansioni</dt><dd>${formatNumber(personal.expansion_scan_errors || 0, 0)}</dd></div>
        </dl>
      </div>
    `;
  } catch (error) {
    diagnosticsPanel.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
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

function setSettingsBusy(busy) {
  settingsBusy = busy;
  for (const control of [
    closeSettings,
    cancelSettings,
    saveSettings,
    saveTestSettings,
    verifyApifyToken,
  ]) {
    if (control) control.disabled = busy;
  }
  if (bggSyncSettingsNow) {
    bggSyncSettingsNow.disabled =
      busy || !currentBggSettings?.collection_sync_configured;
  }
  saveSettings.textContent = busy ? "Salvataggio…" : "Salva";
  saveTestSettings.textContent = busy ? "Verifica…" : "Salva e verifica";
}

function closeSettingsDialog() {
  if (!settingsBusy && settingsDialog.open) {
    settingsDialog.close();
  }
}

function setSettingsTab(name = "general") {
  activateSettingsTab({
    name,
    tabs: settingsTabs,
    panels: settingsPanels,
    saveSettings,
    saveTestSettings,
    onDiagnostics: () => void refreshDiagnostics(),
  });
}

function applyBggSettingsToForm(data) {
  currentBggSettings = data;
  bggUsername.value = data.username || "";
  bggApplicationToken.value = "";
  bggClearToken.checked = false;

  const usernameOverridden = Boolean(data.overrides?.username);
  bggUsername.disabled = usernameOverridden;

  const overridden = Boolean(data.overrides?.application_token);
  bggApplicationToken.disabled = overridden;
  bggClearToken.disabled = overridden;

  if (overridden) {
    bggTokenHint.textContent =
      "Token configurato tramite BGC_BGG_APPLICATION_TOKEN. L'override runtime ha precedenza.";
    clearTokenRow.hidden = true;
  } else if (data.stored_application_token_configured) {
    bggTokenHint.textContent =
      "Token BGG configurato. Lascia vuoto per mantenerlo invariato.";
    clearTokenRow.hidden = false;
  } else {
    bggTokenHint.textContent =
      "Nessun Application Token BGG configurato.";
    clearTokenRow.hidden = true;
  }
}

function applyYoutubeSettingsToForm(data) {
  currentYoutubeSettings = data;
  youtubeApiKey.value = "";
  youtubeClearApiKey.checked = false;
  const overridden = Boolean(data.overrides?.api_key);
  youtubeApiKey.disabled = overridden;
  youtubeClearApiKey.disabled = overridden;
  if (overridden) {
    youtubeApiKeyHint.textContent =
      "Chiave configurata tramite BGC_YOUTUBE_API_KEY. L'override runtime ha precedenza.";
    clearYoutubeApiKeyRow.hidden = true;
  } else if (data.stored_api_key_configured) {
    youtubeApiKeyHint.textContent =
      "YouTube Data API key configurata. Lascia vuoto per mantenerla invariata.";
    clearYoutubeApiKeyRow.hidden = false;
  } else {
    youtubeApiKeyHint.textContent =
      "Nessuna YouTube Data API key configurata.";
    clearYoutubeApiKeyRow.hidden = true;
  }
}

function applyCrowdfundingSettingsToForm(data) {
  currentCrowdfundingSettings = data;
  apifyToken.value = "";
  apifyClearToken.checked = false;
  apifyVerifyStatus.textContent = "";

  const overridden = Boolean(data.overrides?.apify_token);
  apifyToken.disabled = overridden;
  apifyClearToken.disabled = overridden;
  verifyApifyToken.disabled = settingsBusy;

  if (overridden) {
    apifyTokenHint.textContent =
      "Token configurato tramite BGC_APIFY_TOKEN. L'override runtime ha precedenza.";
    clearApifyTokenRow.hidden = true;
  } else if (data.stored_apify_token_configured) {
    apifyTokenHint.textContent =
      "Token Apify configurato. Lascia vuoto per mantenerlo invariato.";
    clearApifyTokenRow.hidden = false;
  } else {
    apifyTokenHint.textContent =
      "Nessun token Apify configurato. Crea un token dedicato in Apify Console → Settings → API & Integrations.";
    clearApifyTokenRow.hidden = true;
  }
  apifyProviderState.textContent = data.configured ? "Configurato" : "Configura";
}


async function saveCrowdfundingSettings() {
  const payload = {
    apify_token:
      apifyToken.disabled || apifyClearToken.checked || !apifyToken.value.trim()
        ? null
        : apifyToken.value.trim(),
    clear_apify_token:
      !apifyClearToken.disabled && apifyClearToken.checked,
  };
  const saved = await api("/api/settings/crowdfunding", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  applyCrowdfundingSettingsToForm(saved);
  return saved;
}


async function saveAndVerifyApify() {
  if (settingsBusy) return;
  setSettingsBusy(true);
  apifyVerifyStatus.textContent = "Verifica…";
  try {
    const saved = await saveCrowdfundingSettings();
    if (!saved.configured) {
      throw new Error("Inserisci un token Apify prima della verifica.");
    }
    const result = await api("/api/settings/crowdfunding/verify", {method: "POST"});
    apifyVerifyStatus.textContent = result.username
      ? `Token valido · account ${result.username}`
      : "Token valido.";
    showToast("Token Apify verificato.");
  } catch (error) {
    apifyVerifyStatus.textContent = error.message;
    showToast(error.message, true);
  } finally {
    setSettingsBusy(false);
  }
}


function formatBggSyncTime(value) {
  if (!value) return "mai";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "mai";
  return date.toLocaleString("it-IT", {dateStyle: "short", timeStyle: "short"});
}

function renderBggSyncSettingsStatus(data) {
  if (!bggSyncSettingsStatus || !bggSyncSettingsNow) return;
  bggSyncSettingsNow.disabled = settingsBusy || !data?.configured;
  if (!data?.configured) {
    bggSyncSettingsStatus.textContent =
      "Configura username e token BGG per abilitare la sincronizzazione automatica.";
    return;
  }
  const everyHours = Math.round((data.interval_seconds || 21600) / 3600);
  const last = formatBggSyncTime(data.last_success_at);
  bggSyncSettingsStatus.textContent = data.last_error
    ? `Ultimo tentativo con errore · ${String(data.last_error).slice(0, 160)}`
    : `Automatica ogni ${everyHours} h · ultima riuscita: ${last}`;
}

async function runManualBggSync() {
  if (!bggSyncSettingsNow || bggSyncSettingsNow.disabled) return;
  const original = bggSyncSettingsNow.textContent;
  bggSyncSettingsNow.disabled = true;
  bggSyncSettingsNow.textContent = "Sincronizzazione…";
  try {
    const result = await api("/api/bgg-collection-sync/run", {method: "POST"});
    renderBggSyncSettingsStatus(result);
    const summary = result.result;
    if (summary) {
      showToast(
        `BGG sincronizzato: ${summary.created_count} nuovi, ${summary.updated_count} aggiornati.`,
      );
    } else {
      showToast("Sincronizzazione BGG già in corso.");
    }
    if (window.location.pathname === "/") {
      const stats = await api("/api/catalog/stats");
      renderStats(stats);
      state.offset = 0;
      await refreshCatalog();
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    bggSyncSettingsNow.textContent = original;
    try {
      renderBggSyncSettingsStatus(await api("/api/bgg-collection-sync"));
    } catch (_) {
      bggSyncSettingsNow.disabled = false;
    }
  }
}

function applyRagSettingsToForm(data) {
  currentRagSettings = data;
  const providers = data.providers || {};
  const ollama = providers.ollama || {};
  const lmstudio = providers.lmstudio || {};
  const gemini = providers.gemini || {};

  renderProviderPriority(ragEmbeddingOrder, ["lmstudio", "ollama", "gemini"], data.embedding_provider_order);
  renderProviderPriority(ragGenerationOrder, ["deepseek", "groq", "lmstudio", "ollama", "gemini"], data.generation_provider_order);
  applyCloudProviderSettings(data);
  ollamaUrl.value = ollama.url || "";
  ollamaEmbeddingModel.value = ollama.embedding_model || "";
  ollamaGenerationModel.value = ollama.generation_model || "";
  lmstudioUrl.value = lmstudio.url || "";
  lmstudioEmbeddingModel.value = lmstudio.embedding_model || "";
  lmstudioGenerationModel.value = lmstudio.generation_model || "";
  lmstudioGenerationTimeout.value = lmstudio.generation_timeout_seconds ?? 300;
  lmstudioGenerationMaxTokens.value = lmstudio.generation_max_tokens ?? 512;
  lmstudioDisableThinking.checked = lmstudio.generation_disable_thinking !== false;
  lmstudioWolEnabled.checked = lmstudio.wol_enabled !== false;
  lmstudioWolMac.value = lmstudio.wol_mac || "";
  lmstudioWolBroadcast.value = lmstudio.wol_broadcast || "192.168.1.255";
  lmstudioWolPort.value = lmstudio.wol_port ?? 9;
  lmstudioApiKey.value = "";
  lmstudioClearApiKey.checked = false;
  clearLmstudioApiKeyRow.hidden = lmstudio.api_key_source !== "stored";
  lmstudioApiKeyHint.textContent = lmstudio.api_key_configured
    ? `API key configurata (${lmstudio.api_key_source || "runtime"}). Lascia vuoto per mantenerla invariata.`
    : "Nessuna API key LM Studio configurata.";

  geminiUrl.value = gemini.url || "";
  geminiEmbeddingModel.value = gemini.embedding_model || "";
  geminiGenerationModel.value = gemini.generation_model || "";
  geminiApiKey.value = "";
  geminiClearApiKey.checked = false;
  clearGeminiApiKeyRow.hidden = gemini.api_key_source !== "stored";
  geminiApiKeyHint.textContent = gemini.api_key_configured
    ? `API key configurata (${gemini.api_key_source || "runtime"}). Lascia vuoto per mantenerla invariata.`
    : "Nessuna Gemini API key configurata.";
}


function renderReferenceStatus(status) {
  if (!referenceStatus) return;
  const value = status.settings || {};
  referenceMinVotes.value = value.min_votes ?? 100;
  referenceIncludeExpansions.checked = value.include_expansions !== false;
  referenceMinWishing.value = value.min_wishing ?? 50;
  referenceDailyBudget.value = value.daily_budget ?? 1500;
  referenceCrowdfundingGrace.value = value.crowdfunding_grace_days ?? 540;
  const last = status.last_dump_import;
  const when = last?.imported_at ? formatBggSyncTime(last.imported_at) : "mai";
  const worker = status.worker || {};
  const sync = worker.last_error
    ? `ultimo errore API: ${String(worker.last_error).slice(0, 120)}`
    : worker.last_run
      ? `aggiornamento API: ${formatBggSyncTime(worker.last_run)} · ${formatNumber(worker.budget_used || 0, 0)}/${formatNumber(worker.daily_budget || 0, 0)} richieste oggi`
      : "aggiornamento API: mai eseguito (richiede il token BGG)";
  const campaigns = worker.crowdfunding_matched
    ? ` · ${formatNumber(worker.crowdfunding_matched, 0)} campagne abbinate`
    : "";
  referenceStatus.textContent =
    `${formatNumber(status.visible, 0)} titoli visibili su ${formatNumber(status.total, 0)} · ultimo import: ${when} · ${sync}${campaigns}`;
}

function readIntegerField(input, label) {
  const value = Number.parseInt(input.value, 10);
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${label} deve essere un numero intero ≥ 0.`);
  }
  return value;
}

async function saveReferenceSettings() {
  if (!referenceMinVotes || referenceMinVotes.value === "") return;
  await api("/api/reference/settings", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      min_votes: readIntegerField(referenceMinVotes, "I voti minimi"),
      include_expansions: referenceIncludeExpansions.checked,
      min_wishing: readIntegerField(referenceMinWishing, "Il wishing minimo"),
      daily_budget: readIntegerField(referenceDailyBudget, "Le richieste al giorno"),
      crowdfunding_grace_days: readIntegerField(referenceCrowdfundingGrace, "I giorni dopo la campagna"),
    }),
  });
  renderReferenceStatus(await api("/api/reference/status"));
}

async function openSettingsDialog(initialTab = "general") {
  if (settingsCollapseExpansions) {
    settingsCollapseExpansions.checked = Boolean(state.collapseExpansions);
  }
  settingsDialog.querySelectorAll(".settings-provider").forEach((section) => {
    section.open = false;
  });
  setSettingsTab(initialTab);
  settingsResult.hidden = true;
  settingsResult.textContent = "";
  setSettingsBusy(true);
  try {
    api("/api/reference/status").then(renderReferenceStatus).catch(() => {
      if (referenceStatus) referenceStatus.textContent = "Stato del catalogo non disponibile.";
    });
    const [bggData, ragData, youtubeData, crowdfundingData, syncData] = await Promise.all([
      api("/api/settings/bgg"),
      api("/api/settings/rag"),
      api("/api/settings/youtube"),
      api("/api/settings/crowdfunding"),
      api("/api/bgg-collection-sync"),
    ]);
    applyBggSettingsToForm(bggData);
    applyRagSettingsToForm(ragData);
    applyYoutubeSettingsToForm(youtubeData);
    applyCrowdfundingSettingsToForm(crowdfundingData);
    renderBggSyncSettingsStatus(syncData);
    settingsDialog.showModal();
  } catch (error) {
    settingsDialog.showModal();
    settingsResult.hidden = false;
    settingsResult.textContent = error.message;
  } finally {
    setSettingsBusy(false);
  }
}

async function persistSettings({verifyAfter = false} = {}) {
  if (settingsBusy) return;
  setSettingsBusy(true);
  settingsResult.hidden = true;

  try {
    const ragPayload = {
      embedding_provider_order: readProviderPriority(ragEmbeddingOrder),
      generation_provider_order: readProviderPriority(ragGenerationOrder),
      ...cloudProviderPayload(),
      ollama_url: ollamaUrl.value.trim() || null,
      ollama_embedding_model: ollamaEmbeddingModel.value.trim() || null,
      ollama_generation_model: ollamaGenerationModel.value.trim() || null,
      lmstudio_url: lmstudioUrl.value.trim() || null,
      lmstudio_api_key:
        lmstudioClearApiKey.checked || !lmstudioApiKey.value.trim()
          ? null
          : lmstudioApiKey.value.trim(),
      clear_lmstudio_api_key: lmstudioClearApiKey.checked,
      lmstudio_embedding_model: lmstudioEmbeddingModel.value.trim() || null,
      lmstudio_generation_model: lmstudioGenerationModel.value.trim() || null,
      lmstudio_generation_timeout_seconds: Number(lmstudioGenerationTimeout.value || 300),
      lmstudio_generation_max_tokens: Number(lmstudioGenerationMaxTokens.value || 512),
      lmstudio_generation_disable_thinking: lmstudioDisableThinking.checked,
      lmstudio_wol_enabled: lmstudioWolEnabled.checked,
      lmstudio_wol_mac: lmstudioWolMac.value.trim() || "",
      lmstudio_wol_broadcast: lmstudioWolBroadcast.value.trim() || "192.168.1.255",
      lmstudio_wol_port: Number(lmstudioWolPort.value || 9),
      gemini_url: geminiUrl.value.trim() || null,
      gemini_api_key:
        geminiClearApiKey.checked || !geminiApiKey.value.trim()
          ? null
          : geminiApiKey.value.trim(),
      clear_gemini_api_key: geminiClearApiKey.checked,
      gemini_embedding_model: geminiEmbeddingModel.value.trim() || null,
      gemini_generation_model: geminiGenerationModel.value.trim() || null,
    };
    const savedRag = await api("/api/settings/rag", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(ragPayload),
    });
    applyRagSettingsToForm(savedRag);

    const bggPayload = {
      username: bggUsername.disabled ? currentBggSettings?.username || null : bggUsername.value.trim() || null,
      application_token:
        bggApplicationToken.disabled || !bggApplicationToken.value.trim()
          ? null
          : bggApplicationToken.value.trim(),
      clear_application_token:
        !bggClearToken.disabled && bggClearToken.checked,
    };
    const savedBgg = await api("/api/settings/bgg", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(bggPayload),
    });
    applyBggSettingsToForm(savedBgg);

    const youtubePayload = {
      api_key:
        youtubeClearApiKey.checked || !youtubeApiKey.value.trim()
          ? null
          : youtubeApiKey.value.trim(),
      clear_api_key: youtubeClearApiKey.checked,
    };
    const savedYoutube = await api("/api/settings/youtube", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(youtubePayload),
    });
    applyYoutubeSettingsToForm(savedYoutube);

    await saveReferenceSettings();

    const savedCrowdfunding = await saveCrowdfundingSettings();
    applyCrowdfundingSettingsToForm(savedCrowdfunding);

    try {
      renderBggSyncSettingsStatus(await api("/api/bgg-collection-sync"));
    } catch (_) {}

    settingsResult.hidden = false;
    settingsResult.innerHTML =
      "<strong>Impostazioni salvate.</strong> Il primo provider di ogni ordine è quello effettivo; nessun fallback automatico.";
    showToast("Impostazioni salvate.");

    if (verifyAfter) {
      const status = await api("/api/settings/bgg/verify", {method: "POST"});
      if (status.verified) {
        settingsResult.innerHTML =
          `<strong>Impostazioni salvate; token BGG verificato.</strong> Accesso XML API2 riuscito con ${escapeHtml(status.title || `BGG #${status.bgg_id}`)}. Nessun fallback RAG automatico.`;
      } else if (status.reason === "catalog_empty") {
        settingsResult.innerHTML =
          "<strong>Impostazioni salvate.</strong> Importa almeno un gioco per verificare XML API2.";
      }
    }
  } catch (error) {
    settingsResult.hidden = false;
    settingsResult.textContent = error.message;
    showToast(error.message, true);
  } finally {
    setSettingsBusy(false);
  }
}

function setCopyBusy(busy) {
  copyBusy = busy;
  for (const control of [closeCopyDialogButton, cancelCopyDialog, saveCopy]) {
    if (control) control.disabled = busy;
  }
  saveCopy.textContent = busy ? "Salvataggio…" : "Salva copia";
}

function copyFormPayload() {
  const payload = {
    barcode: copyBarcode.value.trim() || null,
    language: copyLanguage.value.trim() || null,
    edition: copyEdition.value.trim() || null,
    publishers: copyPublishers.value.trim() || null,
    acquisition_date: copyAcquisitionDate.value || null,
    acquired_from: copyAcquiredFrom.value.trim() || null,
    price_currency: copyCurrency.value.trim() || null,
    condition_text: copyCondition.value.trim() || null,
    inventory_location: copyLocation.value.trim() || null,
    notes: copyNotes.value.trim() || null,
  };
  const versionYear = copyVersionYear.value.trim();
  const price = copyPrice.value.trim();
  payload.version_year_published = versionYear ? Number(versionYear) : null;
  payload.price_paid = price ? Number(price) : null;
  return payload;
}

function fillCopyForm(copy = null, presetBarcode = null) {
  copyForm.reset();
  copyBarcode.value = presetBarcode || copy?.barcode || "";
  copyLanguage.value = copy?.language || "";
  copyEdition.value = copy?.edition || "";
  copyPublishers.value = copy?.publishers || "";
  copyVersionYear.value = copy?.version_year_published || "";
  copyLocation.value = copy?.inventory_location || "";
  copyAcquisitionDate.value = copy?.acquisition_date || "";
  copyAcquiredFrom.value = copy?.acquired_from || "";
  copyPrice.value = copy?.price_paid ?? "";
  copyCurrency.value = copy?.price_currency || "";
  copyCondition.value = copy?.condition || "";
  copyNotes.value = copy?.notes || "";
  copyResult.hidden = true;
  copyResult.textContent = "";
}

function openCopyEditor(bggId, title, copy = null, presetBarcode = null) {
  editingCopyBggId = Number(bggId);
  editingCopyId = copy?.id || null;
  copyDialogTitle.textContent = copy ? "Modifica copia fisica" : "Aggiungi copia fisica";
  copyDialogSubtitle.textContent = title || `BGG #${bggId}`;
  fillCopyForm(copy, presetBarcode);
  setCopyBusy(false);
  copyDialog.showModal();
}

function closeCopyEditor() {
  if (!copyBusy && copyDialog.open) copyDialog.close();
}

async function saveCopyEditor(event) {
  event.preventDefault();
  if (copyBusy || !editingCopyBggId) return;
  setCopyBusy(true);
  copyResult.hidden = true;

  try {
    const payload = copyFormPayload();
    if (editingCopyId) {
      await api(`/api/copies/${encodeURIComponent(editingCopyId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
    } else {
      await api(`/api/games/${editingCopyBggId}/copies`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
    }
    showToast(editingCopyId ? "Copia aggiornata." : "Copia aggiunta.");
    const bggId = editingCopyBggId;
    copyDialog.close();
    if (window.location.pathname === `/games/${bggId}`) {
      await route();
    }
  } catch (error) {
    copyResult.hidden = false;
    copyResult.textContent = error.message;
    showToast(error.message, true);
  } finally {
    setCopyBusy(false);
  }
}

function setDocumentBusy(busy) {
  documentBusy = busy;
  for (const control of documentForm.querySelectorAll("input, select, button")) {
    control.disabled = busy;
  }
  saveDocument.textContent = busy ? "Caricamento…" : "Carica PDF";
}

function resetDocumentDialog() {
  documentForm.reset();
  documentLanguage.value = "it";
  documentFileName.textContent = "Nessun file selezionato";
  documentResult.hidden = true;
  documentResult.textContent = "";
  documentBggId = null;
  setDocumentBusy(false);
}

function openDocumentDialog(bggId, title) {
  resetDocumentDialog();
  documentBggId = bggId;
  documentDialogSubtitle.textContent = title || `BGG #${bggId}`;
  documentDialog.showModal();
}

function closeDocumentDialog() {
  if (!documentBusy && documentDialog.open) {
    documentDialog.close();
  }
}

async function saveDocumentUpload(event) {
  event.preventDefault();
  const file = documentFile.files?.[0];
  const bggId = documentBggId;
  if (!file || !bggId || documentBusy) return;

  setDocumentBusy(true);
  documentResult.hidden = true;
  documentResult.textContent = "";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("document_type", documentType.value);
  formData.append("language", documentLanguage.value.trim() || "und");
  if (documentTitle.value.trim()) formData.append("title", documentTitle.value.trim());
  if (documentVersion.value.trim()) formData.append("version_label", documentVersion.value.trim());
  if (documentEdition.value.trim()) formData.append("edition", documentEdition.value.trim());
  if (documentSourceUrl.value.trim()) formData.append("source_url", documentSourceUrl.value.trim());
  formData.append("is_official", String(documentOfficial.checked));

  try {
    const result = await api(`/api/games/${encodeURIComponent(bggId)}/documents`, {
      method: "POST",
      body: formData,
    });
    const created = result.created === true;
    documentDialog.close();
    showToast(created ? "Documento caricato. Preparazione dell’assistente avviata." : "Documento già presente. Assistente verificato.");
    if (window.location.pathname === `/games/${bggId}`) {
      await renderDetail(bggId);
    }
  } catch (error) {
    documentResult.hidden = false;
    documentResult.textContent = error.message;
  } finally {
    setDocumentBusy(false);
  }
}

const SCANNER_NATIVE_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];

function scannerCameraUsable() {
  return Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia);
}

function scannerVideoConstraints() {
  return {
    facingMode: {ideal: "environment"},
    width: {ideal: 1280},
    height: {ideal: 720},
  };
}

async function applyScannerFocus(stream) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track?.getCapabilities || !track?.applyConstraints) return;
  try {
    const capabilities = track.getCapabilities();
    if (Array.isArray(capabilities.focusMode) && capabilities.focusMode.includes("continuous")) {
      await track.applyConstraints({advanced: [{focusMode: "continuous"}]});
    }
  } catch (_) {
    // Autofocus constraints are an optional enhancement, never a scan blocker.
  }
}

function stopScannerCamera() {
  scannerStartId += 1;
  if (scannerFrameHandle) {
    cancelAnimationFrame(scannerFrameHandle);
    scannerFrameHandle = null;
  }
  if (scannerFallbackControls) {
    try {
      void scannerFallbackControls.stop();
    } catch (_) {
      // Continue with direct track cleanup below.
    }
    scannerFallbackControls = null;
  }
  if (scannerStream) {
    for (const track of scannerStream.getTracks()) track.stop();
    scannerStream = null;
  }
  scannerDetector = null;
  scannerBackend = null;
  scannerVideo.srcObject = null;
  if (toggleCamera) toggleCamera.textContent = "Avvia fotocamera";
}

function acceptScannerDetection(rawValue) {
  const code = String(rawValue || "").trim();
  if (!code || scannerDetectionLocked || !scannerDialog.open) return;
  scannerDetectionLocked = true;
  scannerBarcode.value = code;
  stopScannerCamera();
  cameraHint.textContent = "Codice letto. Ricerca in corso…";
  void lookupScannerBarcode(code);
}

async function createNativeScannerDetector() {
  if (typeof window.BarcodeDetector !== "function") return null;
  try {
    let formats = SCANNER_NATIVE_FORMATS;
    if (typeof window.BarcodeDetector.getSupportedFormats === "function") {
      const supported = await window.BarcodeDetector.getSupportedFormats();
      formats = SCANNER_NATIVE_FORMATS.filter((format) => supported.includes(format));
      if (!formats.length) return null;
    }
    return new window.BarcodeDetector({formats});
  } catch (_) {
    return null;
  }
}

function configureZxingFormats(reader) {
  const formats = window.ZXingBrowser?.BarcodeFormat;
  if (!formats) return;
  reader.possibleFormats = [
    formats.EAN_13,
    formats.EAN_8,
    formats.UPC_A,
    formats.UPC_E,
  ].filter((value) => value !== undefined);
}


function scannerPhotoCanvas(bitmap, rotation = 0, highContrast = false) {
  const maxSide = 2600;
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const sourceWidth = Math.max(1, Math.round(bitmap.width * scale));
  const sourceHeight = Math.max(1, Math.round(bitmap.height * scale));
  const quarterTurn = Math.abs(rotation) % 180 === 90;
  const canvas = document.createElement("canvas");
  canvas.width = quarterTurn ? sourceHeight : sourceWidth;
  canvas.height = quarterTurn ? sourceWidth : sourceHeight;
  const context = canvas.getContext("2d", {willReadFrequently: highContrast});
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((rotation * Math.PI) / 180);
  context.drawImage(
    bitmap,
    -sourceWidth / 2,
    -sourceHeight / 2,
    sourceWidth,
    sourceHeight,
  );
  context.setTransform(1, 0, 0, 1, 0, 0);

  if (highContrast) {
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    const data = image.data;
    for (let offset = 0; offset < data.length; offset += 4) {
      const gray = Math.round(
        (0.299 * data[offset]) +
        (0.587 * data[offset + 1]) +
        (0.114 * data[offset + 2]),
      );
      const value = gray < 145 ? 0 : 255;
      data[offset] = value;
      data[offset + 1] = value;
      data[offset + 2] = value;
    }
    context.putImageData(image, 0, 0);
  }
  return canvas;
}

async function decodeScannerPhoto(file) {
  if (!file || scannerBusy) return;
  const Reader = window.ZXingBrowser?.BrowserMultiFormatReader;
  if (!Reader) {
    cameraHint.textContent = "Lettore barcode non disponibile.";
    scannerManualFallback.open = true;
    return;
  }

  const objectUrl = URL.createObjectURL(file);
  let bitmap = null;
  scannerPhotoButton?.classList.add("is-busy");
  cameraHint.textContent = "Leggo il barcode dalla foto…";
  try {
    if (typeof createImageBitmap === "function") {
      try {
        bitmap = await createImageBitmap(file);
      } catch (_) {
        bitmap = null;
      }
    }

    if (bitmap && typeof window.BarcodeDetector === "function") {
      try {
        const detector = await createNativeScannerDetector();
        const nativeResults = detector ? await detector.detect(bitmap) : [];
        const nativeText = nativeResults?.[0]?.rawValue?.trim();
        if (nativeText) {
          acceptScannerDetection(nativeText);
          return;
        }
      } catch (_) {
        // Continue with the local ZXing multipass fallback.
      }
    }

    const reader = new Reader();
    configureZxingFormats(reader);
    try {
      const result = await reader.decodeFromImageUrl(objectUrl);
      const text = result?.getText?.() ?? result?.text;
      if (text) {
        acceptScannerDetection(text);
        return;
      }
    } catch (_) {
      // Continue with processed variants.
    }

    if (bitmap) {
      const variants = [];
      for (const rotation of [0, 90, -90, 180]) {
        for (const highContrast of [false, true]) {
          variants.push({rotation, highContrast});
        }
      }
      for (let index = 0; index < variants.length; index += 1) {
        const {rotation, highContrast} = variants[index];
        cameraHint.textContent =
          `Analisi barcode… tentativo ${index + 2}/${variants.length + 1}`;
        const canvas = scannerPhotoCanvas(bitmap, rotation, highContrast);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.94);
        try {
          const result = await reader.decodeFromImageUrl(dataUrl);
          const text = result?.getText?.() ?? result?.text;
          if (text) {
            acceptScannerDetection(text);
            return;
          }
        } catch (_) {
          // Try the next rotation/contrast variant.
        }
        canvas.width = 1;
        canvas.height = 1;
      }
    }
    throw new Error("Barcode non trovato");
  } catch (_) {
    cameraHint.textContent =
      "Non riesco a leggere il barcode dalla foto. Prova a riempire l'inquadratura col solo codice, senza riflessi, oppure inseriscilo manualmente.";
    scannerManualFallback.open = true;
  } finally {
    bitmap?.close?.();
    URL.revokeObjectURL(objectUrl);
    if (scannerPhoto) scannerPhoto.value = "";
    scannerPhotoButton?.classList.remove("is-busy");
  }
}

async function startZxingScanner(existingStream = null, startId = scannerStartId) {
  if (startId !== scannerStartId || !scannerDialog.open) {
    for (const track of existingStream?.getTracks?.() || []) track.stop();
    return;
  }

  const Reader = window.ZXingBrowser?.BrowserMultiFormatReader;
  if (!Reader) throw new Error("Fallback ZXing non caricato");
  const reader = new Reader(undefined, {
    delayBetweenScanAttempts: 180,
    delayBetweenScanSuccess: 500,
  });
  configureZxingFormats(reader);
  const callback = (result) => {
    const text = result?.getText?.() ?? result?.text;
    if (text) acceptScannerDetection(text);
  };

  let controls;
  if (existingStream) {
    controls = await reader.decodeFromStream(
      existingStream,
      scannerVideo,
      callback,
    );
  } else {
    controls = await reader.decodeFromConstraints(
      {video: scannerVideoConstraints(), audio: false},
      scannerVideo,
      callback,
    );
  }

  const stream = existingStream || scannerVideo.srcObject || null;
  if (
    startId !== scannerStartId ||
    scannerDetectionLocked ||
    !scannerDialog.open
  ) {
    try {
      void controls.stop();
    } catch (_) {
      for (const track of stream?.getTracks?.() || []) track.stop();
    }
    if (scannerVideo.srcObject === stream) scannerVideo.srcObject = null;
    return;
  }

  scannerBackend = "zxing";
  scannerStream = stream;
  scannerFallbackControls = controls;
  await applyScannerFocus(stream);
  if (startId !== scannerStartId || !scannerDialog.open) return;
  toggleCamera.textContent = "Ferma fotocamera";
  cameraHint.textContent = "Inquadra EAN/UPC. Scanner compatibile ZXing attivo.";
}

async function scanCameraFrame() {
  if (scannerBackend !== "native" || !scannerStream || !scannerDetector) return;
  if (scannerVideo.readyState < 2) {
    scannerFrameHandle = requestAnimationFrame(scanCameraFrame);
    return;
  }
  try {
    const barcodes = await scannerDetector.detect(scannerVideo);
    const rawValue = barcodes?.[0]?.rawValue?.trim();
    if (rawValue) {
      acceptScannerDetection(rawValue);
      return;
    }
  } catch (error) {
    const stream = scannerStream;
    scannerStream = null;
    scannerDetector = null;
    if (scannerFrameHandle) {
      cancelAnimationFrame(scannerFrameHandle);
      scannerFrameHandle = null;
    }
    scannerDetectionLocked = false;
    const fallbackStartId = scannerStartId;
    try {
      await startZxingScanner(stream, fallbackStartId);
      return;
    } catch (_) {
      for (const track of stream?.getTracks?.() || []) track.stop();
      stopScannerCamera();
      cameraHint.textContent = `Scanner non disponibile: ${error.message || "errore di rilevazione"}`;
      scannerManualFallback.open = true;
      return;
    }
  }
  if (scannerBackend === "native" && scannerStream) {
    scannerFrameHandle = requestAnimationFrame(scanCameraFrame);
  }
}

function scannerCameraErrorMessage(error) {
  if (!window.isSecureContext) {
    return "Il browser blocca la fotocamera live su HTTP. Usa “Scatta foto”: funziona anche nella LAN.";
  }
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "Permesso fotocamera negato. Abilitalo nel browser oppure usa l’inserimento manuale.";
  }
  if (error?.name === "NotFoundError") {
    return "Nessuna fotocamera disponibile. Usa l’inserimento manuale.";
  }
  if (error?.name === "NotReadableError") {
    return "La fotocamera è occupata o non leggibile. Chiudi le altre app che la usano e riprova.";
  }
  return "Fotocamera non disponibile. Usa l’inserimento manuale.";
}

async function startScannerCamera() {
  if (scannerBackend || scannerStream || scannerFallbackControls) {
    stopScannerCamera();
    scannerDetectionLocked = false;
    cameraHint.textContent = "Fotocamera arrestata.";
    return;
  }
  scannerDetectionLocked = false;
  if (!scannerCameraUsable()) {
    cameraHint.textContent = scannerCameraErrorMessage();
    scannerManualFallback.open = true;
    return;
  }

  const startId = ++scannerStartId;
  try {
    const detector = await createNativeScannerDetector();
    if (startId !== scannerStartId || !scannerDialog.open) return;

    if (detector) {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: scannerVideoConstraints(),
        audio: false,
      });
      if (startId !== scannerStartId || !scannerDialog.open) {
        for (const track of stream.getTracks()) track.stop();
        return;
      }

      scannerDetector = detector;
      scannerBackend = "native";
      scannerStream = stream;
      scannerVideo.srcObject = stream;
      await scannerVideo.play();
      if (startId !== scannerStartId || !scannerDialog.open) return;

      await applyScannerFocus(stream);
      if (startId !== scannerStartId || !scannerDialog.open) return;

      toggleCamera.textContent = "Ferma fotocamera";
      cameraHint.textContent = "Inquadra EAN/UPC. Scanner nativo attivo.";
      scannerFrameHandle = requestAnimationFrame(scanCameraFrame);
      return;
    }

    await startZxingScanner(null, startId);
  } catch (error) {
    if (startId !== scannerStartId || !scannerDialog.open) return;
    stopScannerCamera();
    cameraHint.textContent = scannerCameraErrorMessage(error);
    scannerManualFallback.open = true;
    window.setTimeout(() => scannerBarcode.focus(), 0);
  }
}

function resetScanner() {
  stopScannerCamera();
  scannerBusy = false;
  scannerDetectionLocked = false;
  scannerImportCount = 0;
  scannerForm.reset();
  if (scannerPhoto) scannerPhoto.value = "";
  lookupBarcode.disabled = false;
  lookupBarcode.textContent = "Cerca";
  scannerResult.innerHTML =
    '<p class="muted">Inquadra o fotografa il barcode: se non è associato potrai scegliere il gioco e importarlo.</p>';
  cameraSection.hidden = false;
  const cameraUsable = scannerCameraUsable();
  toggleCamera.disabled = !cameraUsable;
  scannerManualFallback.open = false;
  cameraHint.textContent = cameraUsable
    ? "La fotocamera live partirà automaticamente; puoi anche scattare una foto."
    : scannerCameraErrorMessage();
}

function beginNextScannerImport() {
  stopScannerCamera();
  scannerBusy = false;
  scannerDetectionLocked = false;
  scannerBarcode.value = "";
  if (scannerPhoto) scannerPhoto.value = "";
  lookupBarcode.disabled = false;
  lookupBarcode.textContent = "Cerca";
  scannerResult.innerHTML =
    `<p class="muted">${scannerImportCount ? `${scannerImportCount} barcode importati. ` : ""}Inquadra o fotografa il prossimo codice.</p>`;
  cameraSection.hidden = false;
  if (scannerCameraUsable()) {
    cameraHint.textContent = "Fotocamera pronta per il prossimo barcode.";
    void startScannerCamera();
  } else {
    cameraHint.textContent = scannerCameraErrorMessage();
  }
}

function renderScannerImported(barcode, title) {
  scannerImportCount += 1;
  scannerBarcode.value = barcode;
  scannerResult.innerHTML = `
    <div class="scanner-success">
      <strong>Barcode importato</strong>
      <span class="muted">${escapeHtml(title || "Copia fisica")} · ${escapeHtml(barcode)}</span>
    </div>
    <div class="dialog-actions scanner-next-actions">
      <button class="button button-primary" id="scannerNextBarcode" type="button">
        Scansiona prossimo
      </button>
    </div>
  `;
  scannerResult.querySelector("#scannerNextBarcode")?.addEventListener("click", beginNextScannerImport);
}

function openScannerDialog() {
  resetScanner();
  scannerDialog.showModal();
  if (scannerCameraUsable()) {
    void startScannerCamera();
  } else {
    cameraHint.textContent = scannerCameraErrorMessage();
  }
}

function closeScannerDialog() {
  stopScannerCamera();
  if (scannerDialog.open) scannerDialog.close();
}

function copySummary(copy) {
  const source = copy.source?.kind === "bgg_csv" ? "BGG" : "Manuale";
  const parts = [
    copy.edition,
    copy.language,
    copy.inventory_location,
    copy.barcode ? `Barcode ${copy.barcode}` : null,
    source,
  ].filter(Boolean);
  return parts.join(" · ") || "Copia senza dettagli";
}

function renderScannerMatches(result) {
  const items = result.matches || [];
  scannerResult.innerHTML = `
    <div class="scanner-success">
      <strong>${items.length === 1 ? "Copia trovata" : `${items.length} copie trovate`}</strong>
      <span class="muted">Codice normalizzato: ${escapeHtml(result.normalized)}</span>
    </div>
    <div class="scanner-match-list">
      ${items.map((copy) => `
        <article class="scanner-match">
          <div>
            <strong>${escapeHtml(copy.game_title)}</strong>
            <span class="muted">BGG #${escapeHtml(copy.bgg_id)} · ${escapeHtml(copySummary(copy))}</span>
          </div>
          <a class="button button-ghost scanner-open-game"
             href="/games/${encodeURIComponent(copy.bgg_id)}"
             data-nav>Apri gioco</a>
        </article>
      `).join("")}
    </div>
    <div class="dialog-actions scanner-next-actions">
      <button class="button button-primary" id="scannerNextBarcode" type="button">
        Scansiona prossimo
      </button>
    </div>
  `;
  scannerResult.querySelectorAll(".scanner-open-game").forEach((link) => {
    link.addEventListener("click", () => closeScannerDialog(), {once: true});
  });
  scannerResult.querySelector("#scannerNextBarcode")?.addEventListener("click", beginNextScannerImport);
}

function renderScannerUnmatched(barcode, lookup = null) {
  const product = lookup?.product || null;
  const candidates = lookup?.candidates || [];
  const externalFailed = lookup?.external_lookup === "failed";
  scannerResult.innerHTML = `
    <div class="scanner-unmatched">
      <strong>${product ? "Prodotto identificato, gioco da confermare" : "Barcode non riconosciuto automaticamente"}</strong>
      ${product ? `
        <p class="muted">
          EAN/UPC: <code>${escapeHtml(barcode)}</code><br>
          Prodotto: <strong>${escapeHtml(product.title || "Titolo non disponibile")}</strong>
          ${product.brand ? ` · ${escapeHtml(product.brand)}` : ""}
        </p>
      ` : `
        <p class="muted">
          Non ho trovato un'associazione affidabile per <code>${escapeHtml(barcode)}</code>.
          ${externalFailed ? "Il servizio di lookup esterno non era raggiungibile; puoi comunque scegliere il gioco manualmente." : "Puoi scegliere il gioco manualmente."}
        </p>
      `}
      ${candidates.length ? `
        <div class="scanner-game-results">
          <p class="muted">Possibili corrispondenze nella tua ludoteca:</p>
          ${candidates.map((game) => `
            <button class="scanner-game-choice scanner-resolved-choice" type="button"
                    data-bgg="${escapeHtml(game.bgg_id)}"
                    data-title="${escapeHtml(game.title)}">
              <strong>${escapeHtml(game.title)}</strong>
              <span class="muted">Confidenza ${Math.round(Number(game.confidence || 0) * 100)}%</span>
            </button>
          `).join("")}
        </div>
      ` : ""}
      <div class="inline-input-action">
        <input id="scannerGameSearch" type="search" autocomplete="off"
               placeholder="Cerca gioco posseduto…"
               value="${escapeHtml(product?.title || "")}">
        <button class="button button-ghost" id="scannerSearchGames" type="button">Cerca</button>
      </div>
      <div id="scannerGameResults" class="scanner-game-results"></div>
    </div>
  `;
  scannerResult.querySelectorAll(".scanner-resolved-choice").forEach((button) => {
    button.addEventListener("click", () => {
      void assignScannedBarcodeToGame(
        Number(button.dataset.bgg),
        button.dataset.title,
        barcode,
      );
    });
  });
  const searchInput = scannerResult.querySelector("#scannerGameSearch");
  scannerResult.querySelector("#scannerSearchGames")?.addEventListener("click", () => {
    void searchScannerGames(searchInput.value, barcode);
  });
  searchInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void searchScannerGames(searchInput.value, barcode);
    }
  });
  if (product?.title && !candidates.length) {
    window.setTimeout(() => {
      void searchScannerGames(product.title, barcode);
    }, 0);
  } else {
    window.setTimeout(() => searchInput?.focus(), 0);
  }
}

async function lookupScannerBarcode(rawBarcode = null) {
  const barcode = String(rawBarcode ?? scannerBarcode.value).trim();
  if (!barcode || scannerBusy) return;
  scannerBusy = true;
  lookupBarcode.disabled = true;
  lookupBarcode.textContent = "Ricerca…";
  scannerResult.innerHTML = '<p class="muted">Ricerca barcode…</p>';

  try {
    const result = await api("/api/barcodes/lookup", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({barcode}),
    });
    if (result.count) {
      renderScannerMatches(result);
    } else if (result.auto_match) {
      scannerResult.innerHTML = `
        <p class="muted">
          Barcode riconosciuto come <strong>${escapeHtml(result.auto_match.title)}</strong>
          · confidenza ${Math.round(Number(result.auto_match.confidence || 0) * 100)}%.
          Associazione in corso…
        </p>
      `;
      await assignScannedBarcodeToGame(
        Number(result.auto_match.bgg_id),
        result.auto_match.title,
        barcode,
      );
    } else {
      renderScannerUnmatched(barcode, result);
    }
  } catch (error) {
    scannerResult.innerHTML =
      `<span class="integration-error">${escapeHtml(error.message)}</span>`;
    showToast(error.message, true);
  } finally {
    scannerBusy = false;
    lookupBarcode.disabled = false;
    lookupBarcode.textContent = "Cerca";
  }
}

async function searchScannerGames(query, barcode) {
  const results = scannerResult.querySelector("#scannerGameResults");
  if (!results) return;
  const value = String(query || "").trim();
  if (!value) {
    results.innerHTML = '<p class="muted">Inserisci almeno una parte del titolo.</p>';
    return;
  }

  results.innerHTML = '<p class="muted">Ricerca giochi…</p>';
  try {
    const params = new URLSearchParams({
      q: value,
      owned: "true",
      limit: "8",
      offset: "0",
      sort: "title",
    });
    const catalog = await api(`/api/games?${params}`);
    if (!catalog.items.length) {
      results.innerHTML = '<p class="muted">Nessun gioco posseduto trovato.</p>';
      return;
    }
    results.innerHTML = catalog.items.map((game) => `
      <button class="scanner-game-choice" type="button"
              data-bgg="${escapeHtml(game.bgg_id)}"
              data-title="${escapeHtml(game.title)}">
        <strong>${escapeHtml(game.title)}</strong>
        <span class="muted">BGG #${escapeHtml(game.bgg_id)} · ${game.item_type === "expansion" ? "Espansione" : "Gioco base"}</span>
      </button>
    `).join("");
    results.querySelectorAll(".scanner-game-choice").forEach((button) => {
      button.addEventListener("click", () => {
        void assignScannedBarcodeToGame(
          Number(button.dataset.bgg),
          button.dataset.title,
          barcode,
        );
      });
    });
  } catch (error) {
    results.innerHTML =
      `<span class="integration-error">${escapeHtml(error.message)}</span>`;
  }
}

async function assignBarcodeToCopy(copyId, barcode, title = null) {
  await api(`/api/copies/${encodeURIComponent(copyId)}`, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({barcode}),
  });
  showToast("Barcode importato nella copia.");
  renderScannerImported(barcode, title);
}

async function assignScannedBarcodeToGame(bggId, title, barcode) {
  scannerResult.innerHTML = '<p class="muted">Controllo copie fisiche…</p>';
  try {
    const copies = await api(`/api/games/${bggId}/copies`);
    const unbarcoded = (copies.items || []).filter((copy) => !copy.barcode_normalized);

    if (unbarcoded.length === 1) {
      await assignBarcodeToCopy(unbarcoded[0].id, barcode, title);
      return;
    }

    if (unbarcoded.length > 1) {
      scannerResult.innerHTML = `
        <strong>Scegli la copia di ${escapeHtml(title)}</strong>
        <p class="muted">Più copie non hanno ancora un barcode.</p>
        <div class="scanner-match-list">
          ${unbarcoded.map((copy) => `
            <button class="scanner-game-choice scanner-copy-choice" type="button"
                    data-copy-id="${escapeHtml(copy.id)}">
              <strong>${escapeHtml(copySummary(copy))}</strong>
              <span class="muted">${escapeHtml(copy.id.slice(0, 8))}</span>
            </button>
          `).join("")}
        </div>
      `;
      scannerResult.querySelectorAll(".scanner-copy-choice").forEach((button) => {
        button.addEventListener("click", () => {
          void assignBarcodeToCopy(button.dataset.copyId, barcode, title);
        });
      });
      return;
    }

    if ((copies.items || []).length === 0) {
      await api(`/api/games/${bggId}/copies`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({barcode}),
      });
      showToast("Nuova copia creata con il barcode.");
      renderScannerImported(barcode, title);
      return;
    }

    scannerResult.innerHTML = `
      <strong>Tutte le copie hanno già un barcode</strong>
      <p class="muted">
        Non modifico automaticamente una copia esistente. Puoi aggiungere esplicitamente
        una nuova copia di ${escapeHtml(title)} con questo codice.
      </p>
      <button class="button button-primary" id="scannerCreateCopy" type="button">
        Aggiungi nuova copia
      </button>
    `;
    scannerResult.querySelector("#scannerCreateCopy")?.addEventListener("click", async () => {
      try {
        await api(`/api/games/${bggId}/copies`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({barcode}),
        });
        showToast("Nuova copia creata.");
        renderScannerImported(barcode, title);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  } catch (error) {
    scannerResult.innerHTML =
      `<span class="integration-error">${escapeHtml(error.message)}</span>`;
    showToast(error.message, true);
  }
}

function normalizedGameTitle(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("it")
    .replace(/\s+/g, " ")
    .trim();
}

function ageText(game) {
  const value = game.bgg?.recommended_age;
  if (!value) return "—";
  const text = String(value).trim();
  if (/^\d+$/.test(text)) return `${text}+`;
  return text;
}

function catalogMetric(label, value, kind = "") {
  const suffix = kind ? ` catalog-metric-${kind}` : "";
  return `<div class="catalog-metric${suffix}"><strong title="${escapeHtml(value)}">${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function inferExpansionParent(expansion, standaloneGames) {
  const titles = [expansion.title, expansion.original_title]
    .filter(Boolean)
    .map(normalizedGameTitle);
  const candidates = standaloneGames.filter((base) => {
    const baseTitles = [base.title, base.original_title].filter(Boolean).map(normalizedGameTitle);
    return baseTitles.some((baseTitle) => titles.some((title) => {
      if (!baseTitle || title === baseTitle || !title.startsWith(baseTitle)) return false;
      const rest = title.slice(baseTitle.length);
      return /^(\s*[:–—-]\s*|\s+\(|\s+–\s+|\s+—\s+)/.test(rest);
    }));
  });
  candidates.sort((a, b) => normalizedGameTitle(b.title).length - normalizedGameTitle(a.title).length);
  return candidates[0] || null;
}

function groupCatalogItems(items) {
  if (!state.collapseExpansions || state.itemType === "expansion") {
    return items.map((game) => ({game, expansions: []}));
  }
  const standaloneGames = items.filter((game) => game.item_type !== "expansion");
  const byId = new Map(
    standaloneGames.map((game) => [Number(game.bgg_id), {game, expansions: []}]),
  );
  const orphanIds = new Set();

  for (const game of items) {
    if (game.item_type !== "expansion") continue;

    // The explicit BGG relationship is authoritative. If the base game is not
    // in this sorted/page slice, keep the expansion collapsed instead of
    // promoting it to a top-level card.
    const explicitParent = Number(game.parent_bgg_id || 0);
    if (explicitParent) {
      const group = byId.get(explicitParent);
      if (group) group.expansions.push(game);
      continue;
    }

    // Legacy metadata can still fall back to the conservative title matcher.
    const parent = inferExpansionParent(game, standaloneGames);
    if (parent) byId.get(Number(parent.bgg_id)).expansions.push(game);
    else orphanIds.add(game.bgg_id);
  }

  const emitted = new Set();
  const groups = [];
  for (const game of items) {
    if (game.item_type === "expansion") {
      if (!orphanIds.has(game.bgg_id)) continue;
      groups.push({game, expansions: []});
      continue;
    }
    if (!emitted.has(game.bgg_id)) {
      groups.push(byId.get(Number(game.bgg_id)));
      emitted.add(game.bgg_id);
    }
  }
  return groups;
}

function expansionMiniCard(game) {
  return `
    <a class="expansion-mini-card" href="/games/${game.bgg_id}" data-nav aria-label="Apri espansione ${escapeHtml(game.title)}">
      <span class="expansion-mini-cover">
        ${game.bgg_metadata?.cover_url
          ? `<img src="${coverSrc(game.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<span>${escapeHtml(initials(game.title))}</span>`}
      </span>
      <span class="expansion-mini-copy">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${escapeHtml(playerText(game))} gioc. · ${escapeHtml(timeText(game))}</small>
      </span>
      ${game.collection?.own ? `<span class="owned-dot" title="Posseduta">${icon("check")}</span>` : ""}
    </a>
  `;
}

function compactCount(value) {
  const number = Number(value) || 0;
  if (number >= 1_000_000) return `${formatNumber(number / 1_000_000, number < 10_000_000 ? 1 : 0)}M`;
  if (number >= 1_000) return `${formatNumber(number / 1_000, number < 10_000 ? 1 : 0)}k`;
  return formatNumber(number, 0);
}

// BGG average on the cover: star, value and a discreet voter count.
function bggRatingBadge(bgg = {}) {
  if (!bgg.average) return "";
  const voters = Number(bgg.users_rated) || 0;
  const title = voters
    ? `Voto medio BGG · ${formatNumber(voters, 0)} votanti`
    : "Voto medio BGG";
  return `<span class="card-bgg-rating" title="${escapeHtml(title)}"><b aria-hidden="true">★</b>${formatNumber(bgg.average, 1)}${voters ? `<small aria-label="${formatNumber(voters, 0)} votanti">${compactCount(voters)}</small>` : ""}</span>`;
}

// Reference rows of the BGG catalog in the shape used by Ludoteca cards and rows.
function referenceAsGame(item) {
  return {
    bgg_id: Number(item.bgg_id),
    title: item.name,
    year_published: item.year_published,
    item_type: item.is_expansion ? "expansion" : "standalone",
    players: item.players || {},
    play_time: item.play_time || {},
    bgg: {
      average: Number(item.average) > 0 ? Number(item.average) : null,
      users_rated: item.users_rated,
      average_weight: item.average_weight,
      recommended_age: item.recommended_age,
      best_players: item.best_players,
      recommended_players: item.recommended_players,
      rank: item.rank,
    },
    bgg_metadata: {cover_url: item.image_url || item.thumbnail_url || ""},
    has_description: Boolean(item.has_description),
    collection: {own: Boolean(item.owned)},
    progress: {},
  };
}

// Owned titles open their Ludoteca page; the others open the BGG catalog sheet.
function gameOpenAttributes(game, reference) {
  if (!reference || game.collection?.own) {
    return {tag: "a", attrs: `href="/games/${game.bgg_id}" data-nav`};
  }
  return {tag: "a", attrs: `href="/bgg/${game.bgg_id}" data-nav`};
}

function gameCard(game, expansions = [], {reference = null} = {}) {
  const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
  const weight = game.bgg?.average_weight ? formatNumber(game.bgg.average_weight, 2) : "—";
  const ownedExpansionCount = expansions.filter((item) => item.collection?.own).length;
  const groupId = `game-group-${game.bgg_id}`;
  const expanded = state.expandedGameGroups.has(String(game.bgg_id));
  const open = gameOpenAttributes(game, reference);
  const rank = reference && Number(game.bgg?.rank) > 0 ? Number(game.bgg.rank) : 0;
  return `
    <article class="game-card-wrap ${expansions.length ? "has-expansions" : ""} ${reference ? "has-actions" : ""}" data-game-id="${game.bgg_id}">
      <${open.tag} class="game-card" ${open.attrs} aria-label="Apri ${escapeHtml(game.title)}">
        <div class="cover ${game.bgg_metadata?.cover_url ? "has-image" : ""}">
          ${rank || game.item_type === "expansion" ? `
            <span class="card-corner">
              ${rank ? `<span class="card-rank" title="Posizione nella classifica BGG">#${formatNumber(rank, 0)}</span>` : ""}
              ${game.item_type === "expansion" ? `<span class="badge card-badge">${type}</span>` : ""}
            </span>
          ` : ""}
          ${game.bgg_metadata?.cover_url
            ? `<img class="cover-image" src="${coverSrc(game.bgg_id)}" alt="Cover di ${escapeHtml(game.title)}" loading="lazy" referrerpolicy="no-referrer">`
            : `<span class="cover-initials">${escapeHtml(initials(game.title))}</span>`}
          ${bggRatingBadge(game.bgg)}
        </div>
        <div class="card-body">
          <h3 class="card-title" title="${escapeHtml(game.title)}">${escapeHtml(game.title)}</h3>
          <div class="catalog-metrics">
            ${catalogMetric("Giocatori", playerText(game))}
            ${catalogMetric("Età", ageText(game))}
            ${catalogMetric("Durata", timeText(game).replace(" min", ""), "duration")}
            ${catalogMetric("Peso", weight)}
          </div>
          ${game.progress?.rating ? `
            <div class="card-footer-meta">
              <span class="personal-card-rating">Il tuo voto ${starRatingMarkup(game.progress.rating, {compact: true})}</span>
            </div>
          ` : ""}
        </div>
      </${open.tag}>
      ${reference ? `<div class="card-actions">${referenceActionButtons(reference)}</div>` : ""}
      ${expansions.length ? `
        <button class="expansion-count-badge" type="button" data-expansion-toggle="${game.bgg_id}"
                aria-controls="${groupId}" aria-expanded="${expanded ? "true" : "false"}"
                aria-label="Espansioni: ${ownedExpansionCount} possedute su ${expansions.length}"
                title="${ownedExpansionCount} espansioni possedute su ${expansions.length}">${ownedExpansionCount}</button>
        <div class="expansion-drawer" id="${groupId}" ${expanded ? "" : "hidden"}>
          ${expansions.map(expansionMiniCard).join("")}
        </div>
      ` : ""}
    </article>
  `;
}

function gameListRow(game, expansions = [], isExpansion = false, {reference = null} = {}) {
  const rating = game.bgg?.average ? formatNumber(game.bgg.average, 1) : "—";
  const voters = Number(game.bgg?.users_rated) || 0;
  const weight = game.bgg?.average_weight ? formatNumber(game.bgg.average_weight, 2) : "—";
  const ownedExpansionCount = expansions.filter((item) => item.collection?.own).length;
  const expanded = state.expandedGameGroups.has(String(game.bgg_id));
  const open = gameOpenAttributes(game, reference);
  const rank = reference && Number(game.bgg?.rank) > 0 ? `#${formatNumber(game.bgg.rank, 0)}` : "";
  const subtitle = [
    rank,
    game.item_type === "expansion" ? "Espansione" : (game.year_published || (reference ? "" : "Gioco base")),
  ].filter(Boolean).join(" · ");
  return `
    <div class="catalog-list-row ${isExpansion ? "is-expansion-row" : ""} ${reference ? "is-reference-row" : ""}">
      <${open.tag} class="catalog-list-game" ${open.attrs} aria-label="Apri ${escapeHtml(game.title)}">
        <span class="catalog-list-cover">
          ${game.bgg_metadata?.cover_url
            ? `<img src="${coverSrc(game.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
            : `<span>${escapeHtml(initials(game.title))}</span>`}
        </span>
        <span class="catalog-list-title">
          <strong>${escapeHtml(game.title)}</strong>
          <small>${escapeHtml(subtitle || "—")}</small>
        </span>
      </${open.tag}>
      <span class="list-stat"><strong>${escapeHtml(playerText(game))}</strong><small>Giocatori</small></span>
      <span class="list-stat"><strong>${escapeHtml(ageText(game))}</strong><small>Età</small></span>
      <span class="list-stat"><strong>${escapeHtml(timeText(game).replace(" min", ""))}</strong><small>Minuti</small></span>
      <span class="list-stat"><strong>${weight}</strong><small>Peso</small></span>
      <span class="list-rating" ${voters ? `title="${formatNumber(voters, 0)} votanti"` : ""}><strong>${rating}</strong><small>${voters ? compactCount(voters) : "BGG"}</small></span>
      ${reference ? `<span class="list-actions">${referenceActionButtons(reference)}</span>` : `
      <span class="list-personal-rating">
        ${game.progress?.rating ? starRatingMarkup(game.progress.rating, {compact: true}) : "—"}
        <small>Tu</small>
      </span>
      ${expansions.length ? `
        <button class="list-expansion-toggle" type="button" data-expansion-toggle="${game.bgg_id}"
                aria-expanded="${expanded ? "true" : "false"}"
                aria-label="Espansioni: ${ownedExpansionCount} possedute su ${expansions.length}"
                title="${ownedExpansionCount} espansioni possedute su ${expansions.length}">
          <strong>${ownedExpansionCount}</strong><i aria-hidden="true">${icon(expanded ? "caret-up" : "caret-down")}</i>
        </button>
      ` : '<span class="list-expansion-placeholder"></span>'}`}
    </div>
    ${expansions.length ? `
      <div class="catalog-list-expansions" id="game-group-${game.bgg_id}" ${expanded ? "" : "hidden"}>
        ${expansions.map((item) => gameListRow(item, [], true)).join("")}
      </div>
    ` : ""}
  `;
}

function bindExpansionToggles() {
  document.querySelectorAll("[data-expansion-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = String(button.dataset.expansionToggle);
      if (state.expandedGameGroups.has(id)) state.expandedGameGroups.delete(id);
      else state.expandedGameGroups.add(id);
      const panel = document.querySelector(`#game-group-${CSS.escape(id)}`);
      const expanded = state.expandedGameGroups.has(id);
      button.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (panel) panel.hidden = !expanded;
      const caret = button.querySelector("i");
      if (caret) caret.innerHTML = icon(expanded ? "caret-up" : "caret-down");
    });
  });
}

function skeletons() {
  return Array.from({length: 12}, () => '<div class="skeleton"></div>').join("");
}

function syncCatalogViewControls() {
  for (const [id, view] of [
    ["cardViewButton", "cards"],
    ["listViewButton", "list"],
  ]) {
    const button = document.querySelector(`#${id}`);
    if (!button) continue;
    const active = state.catalogView === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
  const columnsField = document.querySelector("#cardsPerRowField");
  const columnsSelect = document.querySelector("#cardsPerRowFilter");
  const cardsVisible = state.catalogView === "cards";
  if (columnsField) columnsField.hidden = !cardsVisible;
  if (columnsSelect) columnsSelect.disabled = !cardsVisible;
  syncCatalogSortControls();
}

function rerenderCurrentCatalog() {
  if (!currentCatalogData) {
    void refreshCatalog();
    return;
  }
  syncCatalogViewControls();
  renderCatalogData(currentCatalogData);
}

async function renderCatalog() {
  currentCatalogData = null;
  const activeFacet = state.category
    ? `Genere: ${state.category}`
    : state.mechanic
    ? `Meccanica: ${state.mechanic}`
    : "";

  app.innerHTML = `
    <section class="page-header catalog-page-header">
      <div class="page-header-copy">
        <h1>Ludoteca</h1>
        <p class="muted catalog-page-summary">La tua collezione, le partite giocate e i regolamenti raccolti</p>
        ${activeFacet ? `
          <div class="catalog-hero-actions">
            <button class="active-facet-chip" id="clearFacet" type="button">
              ${escapeHtml(activeFacet)} <span aria-hidden="true">×</span>
            </button>
          </div>
        ` : ""}
      </div>
      <section class="catalog-stats" id="statsPanel" aria-label="Riepilogo ludoteca">
        <div class="stat"><strong>—</strong><span>Giochi base</span></div>
        <div class="stat"><strong>—</strong><span>Espansioni</span></div>
        <div class="stat"><strong>—</strong><span>Giocati</span></div>
        <div class="stat"><strong>—</strong><span>Regolamenti</span></div>
      </section>
    </section>

    <section class="catalog-recent" id="achievementShowcase" aria-labelledby="catalogRecentHeading" hidden>
      <div class="catalog-recent-head">
        <h2 class="catalog-recent-title" id="catalogRecentHeading">Giocati di recente</h2>
        <a class="catalog-recent-all" href="/plays" data-nav>Partite ${icon("arrow-right")}</a>
      </div>
      <div class="catalog-recent-list" id="achievementShowcaseGrid"></div>
    </section>

    <section class="catalog-workspace" aria-label="Ludoteca">
      <span id="resultCount" hidden></span>
      <section class="toolbar catalog-simple-search" aria-label="Ricerca catalogo">
        <label class="field search-field">
          <input id="searchInput" type="search" aria-label="Cerca per titolo"
                 placeholder="Cerca un gioco…" value="${escapeHtml(state.q)}" autocomplete="off">
        </label>
        <label class="field catalog-type-field">
          <select id="typeFilter" aria-label="Tipo">
            <option value="">Tutti i tipi</option>
            <option value="standalone" ${state.itemType === "standalone" ? "selected" : ""}>Giochi base</option>
            <option value="expansion" ${state.itemType === "expansion" ? "selected" : ""}>Espansioni</option>
          </select>
        </label>
        <div class="catalog-sort-control">
          <select id="sortField" aria-label="Ordina per">
            ${Object.entries(catalogSortFieldLabels).map(([value, label]) => `<option value="${value}" ${currentCatalogSortField() === value ? "selected" : ""}>${label}</option>`).join("")}
          </select>
          <button class="catalog-sort-direction" id="sortDirection" type="button"
                  data-direction="${catalogSortAscending() ? "asc" : "desc"}"
                  aria-label="Ordinamento ${catalogSortAscending() ? "crescente" : "decrescente"}"
                  title="${catalogSortAscending() ? "Ordine crescente" : "Ordine decrescente"}">${icon(catalogSortAscending() ? "caret-up" : "caret-down")}</button>
        </div>
        <div class="catalog-view-switch catalog-filter-view" aria-label="Vista catalogo">
          <button class="view-switch-button ${state.catalogView === "cards" ? "is-active" : ""}" id="cardViewButton"
                  type="button" aria-label="Card" title="Card" aria-pressed="${state.catalogView === "cards" ? "true" : "false"}">${icon("catalog")}</button>
          <button class="view-switch-button ${state.catalogView === "list" ? "is-active" : ""}" id="listViewButton"
                  type="button" aria-label="Lista" title="Lista" aria-pressed="${state.catalogView === "list" ? "true" : "false"}">${icon("list")}</button>
        </div>
        <button class="button button-ghost advanced-search-toggle" id="advancedSearchToggle" type="button"
                aria-controls="advancedSearch" aria-expanded="${state.supportsPlayers || state.idealPlayers || state.playerAge || state.weight || state.maxMinutes || state.minRating ? "true" : "false"}">Ricerca avanzata</button>
        <div class="catalog-density-fields">
          <label class="catalog-density-field" id="cardsPerRowField" ${state.catalogView === "cards" ? "" : "hidden"}>
            <span class="catalog-density-label">Righe</span>
            <select id="cardsPerRowFilter" aria-label="Card per riga">
              ${[3, 4, 5].map((value) => `<option value="${value}" ${state.cardsPerRow === value ? "selected" : ""}>${value}</option>`).join("")}
            </select>
          </label>
          <label class="catalog-density-field">
            <span class="catalog-density-label">Pagina</span>
            <select id="pageSizeFilter" aria-label="Titoli per pagina">
              ${[["20", "20"], ["50", "50"], ["100", "100"], ["250", "250"], ["all", "Tutti"]].map(([value, label]) => `<option value="${value}" ${state.pageSize === value ? "selected" : ""}>${label}</option>`).join("")}
            </select>
          </label>
        </div>
        <button class="button button-ghost catalog-scan-button" id="scannerButton" type="button"
                aria-label="Scansiona barcode" title="Scansiona barcode">
          <span aria-hidden="true">+</span>
        </button>
      </section>
      <details class="advanced-search" id="advancedSearch" ${state.supportsPlayers || state.idealPlayers || state.playerAge || state.weight || state.maxMinutes || state.minRating ? "open" : ""}>
        <summary>Ricerca avanzata</summary>
        <div class="advanced-search-grid">
          <label><span>Giocabile in</span><input id="supportsPlayers" type="number" min="1" max="30" placeholder="es. 2" value="${escapeHtml(state.supportsPlayers)}"></label>
          <label><span>Ideale in</span><input id="idealPlayers" type="number" min="1" max="30" placeholder="es. 2" value="${escapeHtml(state.idealPlayers)}"></label>
          <label><span>Età del giocatore</span><input id="playerAge" type="number" min="3" max="99" placeholder="es. 8" value="${escapeHtml(state.playerAge)}"></label>
          <label><span>Complessità</span>
            <select id="weightFilter">
              <option value="">Qualsiasi</option>
              <option value="light" ${state.weight === "light" ? "selected" : ""}>Semplice (≤ 2,3)</option>
              <option value="medium" ${state.weight === "medium" ? "selected" : ""}>Media (2,3–3,5)</option>
              <option value="heavy" ${state.weight === "heavy" ? "selected" : ""}>Impegnativa (&gt; 3,5)</option>
            </select>
          </label>
          <label><span>Durata massima</span><input id="maxMinutes" type="number" min="1" max="1440" placeholder="minuti" value="${escapeHtml(state.maxMinutes)}"></label>
          <label><span>Rating BGG minimo</span><input id="minRating" type="number" min="0" max="10" step="0.1" placeholder="es. 7" value="${escapeHtml(state.minRating)}"></label>
        </div>
        <div class="advanced-search-actions">
          <p>“Età del giocatore” usa l'età minima ufficiale indicata su BGG.</p>
          <button class="button button-ghost" id="resetAdvancedSearch" type="button">Azzera filtri avanzati</button>
        </div>
      </details>

      <section class="catalog-results ${state.catalogView === "list" ? "catalog-results-list" : `catalog-results-cards catalog-columns-${state.cardsPerRow}`}"
               id="catalogGrid">${skeletons()}</section>
      <nav class="pagination" id="pagination" aria-label="Paginazione"></nav>
    </section>
  `;

  bindCatalogControls();
  const requestedPath = window.location.pathname;

  catalogRequestController?.abort();
  const controller = new AbortController();
  catalogRequestController = controller;
  try {
    const [stats, catalog] = await Promise.all([
      api("/api/catalog/stats", {signal: controller.signal}),
      loadCatalogData(controller.signal),
    ]);
    if (
      controller.signal.aborted
      || window.location.pathname !== requestedPath
    ) return;
    renderStats(stats);
    renderCatalogData(catalog);
    runWhenIdle(() => {
      void refreshAchievementShowcase();
      void backfillMissingMetadata();
      void checkBggCollectionSyncOnOpen();
    });
  } catch (error) {
    if (error.name === "AbortError") return;
    const grid = document.querySelector("#catalogGrid");
    if (grid) {
      grid.innerHTML =
        `<div class="empty catalog-empty">Impossibile caricare il catalogo: ${escapeHtml(error.message)}</div>`;
    }
    showToast(error.message, true);
  } finally {
    if (catalogRequestController === controller) {
      catalogRequestController = undefined;
    }
  }
}

function bindCatalogControls() {
  document.querySelector("#scannerButton")?.addEventListener("click", () => {
    openScannerDialog();
  });

  const advancedSearch = document.querySelector("#advancedSearch");
  const advancedSearchToggle = document.querySelector("#advancedSearchToggle");
  advancedSearchToggle?.addEventListener("click", () => {
    advancedSearch.open = !advancedSearch.open;
  });
  advancedSearch?.addEventListener("toggle", () => {
    advancedSearchToggle?.setAttribute("aria-expanded", advancedSearch.open ? "true" : "false");
  });

  const refreshFrom = (key, value) => {
    state[key] = String(value ?? "").trim();
    state.offset = 0;
    refreshCatalog();
  };

  document.querySelector("#searchInput")?.addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => refreshFrom("q", event.target.value), 260);
  });
  document.querySelector("#typeFilter")?.addEventListener("change", (event) => refreshFrom("itemType", event.target.value));

  document.querySelector("#sortField")?.addEventListener("change", (event) => {
    const [primary] = catalogColumnSorts[event.target.value] || catalogColumnSorts.title;
    refreshFrom("sort", primary);
    syncCatalogSortControls();
  });

  document.querySelector("#sortDirection")?.addEventListener("click", () => {
    const field = currentCatalogSortField();
    const [primary, secondary] = catalogColumnSorts[field] || catalogColumnSorts.title;
    refreshFrom("sort", state.sort === primary ? secondary : primary);
    syncCatalogSortControls();
  });

  document.querySelector("#pageSizeFilter")?.addEventListener("change", (event) => {
    const value = catalogPageSizeValues.has(event.target.value) ? event.target.value : "50";
    if (state.pageSize === value) return;
    state.pageSize = value;
    state.limit = value === "all" ? CATALOG_ALL_LIMIT : Number(value);
    state.offset = 0;
    window.localStorage.setItem("bgc.catalogPageSize", value);
    refreshCatalog();
  });

  document.querySelector("#cardsPerRowFilter")?.addEventListener("change", (event) => {
    const value = Number(event.target.value);
    if (![3, 4, 5].includes(value) || state.cardsPerRow === value) return;
    state.cardsPerRow = value;
    window.localStorage.setItem("bgc.catalogColumns", String(value));
    rerenderCurrentCatalog();
  });

  for (const [id, key] of [
    ["supportsPlayers", "supportsPlayers"],
    ["idealPlayers", "idealPlayers"],
    ["playerAge", "playerAge"],
    ["weightFilter", "weight"],
    ["maxMinutes", "maxMinutes"],
    ["minRating", "minRating"],
  ]) {
    document.querySelector(`#${id}`)?.addEventListener("change", (event) => refreshFrom(key, event.target.value));
  }

  document.querySelector("#resetAdvancedSearch")?.addEventListener("click", () => {
    for (const [id, key] of [
      ["supportsPlayers", "supportsPlayers"],
      ["idealPlayers", "idealPlayers"],
      ["playerAge", "playerAge"],
      ["weightFilter", "weight"],
      ["maxMinutes", "maxMinutes"],
      ["minRating", "minRating"],
    ]) {
      state[key] = "";
      const control = document.querySelector(`#${id}`);
      if (control) control.value = "";
    }
    state.offset = 0;
    refreshCatalog();
  });

  document.querySelector("#clearFacet")?.addEventListener("click", (event) => {
    state.category = "";
    state.mechanic = "";
    state.offset = 0;
    event.currentTarget.remove();
    refreshCatalog();
  });

  document.querySelector("#cardViewButton")?.addEventListener("click", () => {
    if (state.catalogView === "cards") return;
    state.catalogView = "cards";
    window.localStorage.setItem("bgc.catalogView", "cards");
    rerenderCurrentCatalog();
  });
  document.querySelector("#listViewButton")?.addEventListener("click", () => {
    if (state.catalogView === "list") return;
    state.catalogView = "list";
    window.localStorage.setItem("bgc.catalogView", "list");
    rerenderCurrentCatalog();
  });
}

function renderCatalogBggSyncStatus(data) {
  const button = document.querySelector("#catalogBggSync");
  const status = document.querySelector("#catalogBggSyncStatus");
  const dot = document.querySelector("#catalogBggSyncDot");
  if (!button || !status) return;
  button.disabled = Boolean(data?.running);
  dot?.classList.remove("is-running", "is-error");
  if (!data?.configured) {
    status.textContent = "BGG non configurato";
    dot?.classList.add("is-error");
    return;
  }
  if (data.running) {
    status.textContent = "BGG · sync…";
    dot?.classList.add("is-running");
    return;
  }
  if (data.last_error) {
    status.textContent = "BGG · errore";
    dot?.classList.add("is-error");
    return;
  }
  status.textContent = data.last_success_at
    ? `BGG · ${formatBggSyncTime(data.last_success_at)}`
    : "BGG · mai";
}

async function runCatalogBggSync() {
  const button = document.querySelector("#catalogBggSync");
  if (!button) return;
  button.disabled = true;
  renderCatalogBggSyncStatus({configured: true, running: true});
  try {
    const result = await api("/api/bgg-collection-sync/run", {method: "POST"});
    const summary = result.result;
    renderCatalogBggSyncStatus(result);
    if (summary) {
      showToast(
        `BGG sincronizzato: ${summary.created_count} nuovi, ${summary.updated_count} aggiornati.`,
      );
    }
    const stats = await api("/api/catalog/stats");
    renderStats(stats);
    state.offset = 0;
    await refreshCatalog();
  } catch (error) {
    if (error.status === 409) {
      showToast("Configura username e token BGG nelle impostazioni.", true);
      void openSettingsDialog();
    } else {
      showToast(error.message, true);
    }
    try {
      renderCatalogBggSyncStatus(await api("/api/bgg-collection-sync"));
    } catch (_) {}
  } finally {
    if (document.querySelector("#catalogBggSync")) {
      document.querySelector("#catalogBggSync").disabled = false;
    }
  }
}

async function checkBggCollectionSyncOnOpen() {
  if (navigator.webdriver || window.location.pathname !== "/") return;
  try {
    const before = await api("/api/bgg-collection-sync");
    renderCatalogBggSyncStatus(before);
    if (!before.configured) return;

    const check = await api("/api/bgg-collection-sync/check", {method: "POST"});
    renderCatalogBggSyncStatus({...check, running: check.scheduled});
    if (!check.scheduled) return;

    const previousSuccess = before.last_success_at;
    for (let attempt = 0; attempt < 12 && window.location.pathname === "/"; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 5000));
      const current = await api("/api/bgg-collection-sync");
      const finished =
        current.last_success_at &&
        current.last_success_at !== previousSuccess &&
        !current.due;
      renderCatalogBggSyncStatus({...current, running: !finished});
      if (finished) {
        const stats = await api("/api/catalog/stats");
        renderStats(stats);
        state.offset = 0;
        await refreshCatalog();
        showToast("Collezione BGG aggiornata automaticamente.");
        break;
      }
      if (current.last_error) break;
    }
  } catch (_) {
    // Automatic collection sync is opportunistic and must never block browsing.
  }
}

async function loadCatalogData(signal) {
  // Grouping base games with their expansions must happen before pagination.
  // Otherwise a page boundary can separate an expansion from its parent.
  const groupBeforePaginating = state.collapseExpansions;
  const params = new URLSearchParams({
    limit: String(groupBeforePaginating ? CATALOG_ALL_LIMIT : state.limit),
    offset: String(groupBeforePaginating ? 0 : state.offset),
    sort: state.sort,
  });
  if (state.q) params.set("q", state.q);
  if (state.itemType) params.set("item_type", state.itemType);
  if (state.owned) params.set("owned", state.owned);
  if (state.supportsPlayers) params.set("supports_players", state.supportsPlayers);
  if (state.idealPlayers) params.set("ideal_players", state.idealPlayers);
  if (state.playerAge) params.set("player_age", state.playerAge);
  if (state.weight) params.set("weight", state.weight);
  if (state.maxMinutes) params.set("max_minutes", state.maxMinutes);
  if (state.minRating) params.set("min_rating", state.minRating);
  if (state.category) params.set("category", state.category);
  if (state.mechanic) params.set("mechanic", state.mechanic);
  return api(`/api/games?${params}`, signal ? {signal} : undefined);
}

async function refreshCatalog() {
  const grid = document.querySelector("#catalogGrid");
  const count = document.querySelector("#resultCount");
  if (!grid || !count) return;

  catalogRequestController?.abort();
  const controller = new AbortController();
  catalogRequestController = controller;

  grid.classList.add("is-refreshing");
  grid.setAttribute("aria-busy", "true");
  count.textContent = currentCatalogData ? "Aggiornamento…" : "Caricamento…";
  if (!currentCatalogData) grid.innerHTML = skeletons();
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
      const liveGrid = document.querySelector("#catalogGrid");
      liveGrid?.classList.remove("is-refreshing");
      liveGrid?.removeAttribute("aria-busy");
    }
  }
}

async function backfillMissingMetadata() {
  if (navigator.webdriver || metadataBackfillRunning || window.location.pathname !== "/") return;
  metadataBackfillRunning = true;
  let updatedAny = false;
  try {
    for (let batch = 0; batch < 10 && window.location.pathname === "/"; batch += 1) {
      const result = await api("/api/catalog/bgg-metadata/refresh-missing?limit=20", {method: "POST"});
      updatedAny = updatedAny || Boolean(result.updated);
      if (!result.updated || !result.remaining) break;
    }
    if (updatedAny && window.location.pathname === "/") {
      await refreshCatalog();
    }
  } catch (_) {
    // Opportunistic enrichment must never block catalog browsing.
  } finally {
    metadataBackfillRunning = false;
  }
}

function renderStats(stats) {
  const values = [
    [stats.standalone_owned, "Giochi base"],
    [stats.expansions_owned, "Espansioni"],
    [stats.played ?? stats.completed, "Giocati"],
    [stats.rulebooks, "Regolamenti"],
  ];
  document.querySelector("#statsPanel").innerHTML = values.map(([value, label]) =>
    `<div class="stat"><strong>${formatNumber(value, 0)}</strong><span>${label}</span></div>`
  ).join("");
}

function renderCatalogData(catalog) {
  currentCatalogData = catalog;
  const grid = document.querySelector("#catalogGrid");
  const count = document.querySelector("#resultCount");
  if (!grid || !count) return;

  count.textContent = `${formatNumber(catalog.total, 0)} titoli`;
  grid.className = `catalog-results ${state.catalogView === "list" ? "catalog-results-list" : `catalog-results-cards catalog-columns-${state.cardsPerRow}`}`;

  if (!catalog.items.length) {
    state.total = 0;
    grid.innerHTML = '<div class="empty catalog-empty">Nessun gioco corrisponde ai filtri selezionati.</div>';
  } else {
    const allGroups = groupCatalogItems(catalog.items);
    state.total = state.collapseExpansions ? allGroups.length : catalog.total;
    const groups = state.collapseExpansions
      ? allGroups.slice(state.offset, state.offset + state.limit)
      : allGroups;
    if (state.catalogView === "list") {
      grid.innerHTML = `
        <div class="catalog-list-head" aria-label="Ordina la lista per colonna">
          ${catalogSortHeader("Gioco", "title")}
          ${catalogSortHeader("Giocatori", "players")}
          ${catalogSortHeader("Età", "age")}
          ${catalogSortHeader("Durata", "duration")}
          ${catalogSortHeader("Peso", "weight")}
          ${catalogSortHeader("BGG", "rating")}
          <span aria-hidden="true"></span>
        </div>
        ${groups.map(({game, expansions}) => gameListRow(game, expansions)).join("")}
      `;
    } else {
      grid.innerHTML = groups.map(({game, expansions}) => gameCard(game, expansions)).join("");
    }
    bindExpansionToggles();
    bindCatalogSortHeaders();
  }
  renderPagination();
}

function renderPagination() {
  const container = document.querySelector("#pagination");
  if (!container) return;
  const page = Math.floor(state.offset / state.limit) + 1;
  const pages = Math.max(1, Math.ceil(state.total / state.limit));
  if (pages <= 1) {
    container.innerHTML = "";
    container.hidden = true;
    return;
  }
  container.hidden = false;
  container.innerHTML = `
    <button class="button button-ghost" id="prevPage" ${page <= 1 ? "disabled" : ""}>← Precedente</button>
    <span class="muted">Pagina ${page} di ${pages} · ${state.pageSize === "all" ? "tutti i titoli" : `${state.pageSize} per pagina`}</span>
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

const documentTypeLabels = {
  rulebook: "Regolamento",
  reference: "Riferimento",
  faq: "FAQ",
  errata: "Errata",
  scenario_book: "Libro scenari",
  campaign_book: "Libro campagna",
  player_aid: "Player aid",
  other: "Altro",
};

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, 1)} KB`;
  return `${formatNumber(bytes / (1024 * 1024), 1)} MB`;
}

function documentCard(document) {
  const typeLabel = documentTypeLabels[document.document_type] || document.document_type || "Documento";
  const source = document.source || {};
  const details = [
    document.version_label ? `Versione ${document.version_label}` : null,
    document.edition ? `Edizione ${document.edition}` : null,
    document.original_filename || null,
    formatBytes(document.size_bytes),
  ].filter(Boolean).join(" · ");
  const provenance = source.kind === "manual_upload" ? "Upload manuale" : (source.provider || source.kind || "Fonte registrata");
  const official = source.official === true;

  return `
    <article class="game-document-card" data-document-id="${escapeHtml(document.id)}">
      <div class="game-document-head">
        <div>
          <div class="document-badges">
            <span class="badge">${escapeHtml(typeLabel)}</span>
            <span class="badge">${escapeHtml((document.language || "und").toUpperCase())}</span>
            ${official ? '<span class="badge document-official">Ufficiale</span>' : '<span class="badge document-unofficial">Non ufficiale</span>'}
          </div>
          <strong class="game-document-title">${escapeHtml(document.title || document.original_filename || typeLabel)}</strong>
        </div>
        <a class="button button-ghost document-download"
           href="/api/documents/${encodeURIComponent(document.id)}/file"
           target="_blank" rel="noopener noreferrer">Apri PDF</a>
      </div>
      <p class="game-document-meta">${escapeHtml(details)}</p>
      <p class="game-document-source">${escapeHtml(provenance)}${source.url ? ` · ${escapeHtml(source.url)}` : ""}</p>
    </article>
  `;
}

function physicalCopyCard(copy, index) {
  const sourceLabel = copy.source?.kind === "bgg_csv" ? "Import BGG" : "Manuale";
  const purchase = [
    copy.acquisition_date,
    copy.acquired_from,
    copy.price_paid !== null && copy.price_paid !== undefined
      ? `${formatNumber(copy.price_paid, 2)} ${copy.price_currency || ""}`.trim()
      : null,
  ].filter(Boolean).join(" · ");

  return `
    <article class="physical-copy-card" data-copy-id="${escapeHtml(copy.id)}">
      <div class="physical-copy-head">
        <div>
          <p class="eyebrow">Copia ${index + 1}</p>
          <strong>${escapeHtml(copy.edition || copy.language || "Copia fisica")}</strong>
        </div>
        <button class="button button-ghost edit-copy" type="button"
                data-copy-id="${escapeHtml(copy.id)}">Modifica</button>
      </div>
      <div class="copy-facts">
        ${fact("Barcode", copy.barcode || "—")}
        ${fact("Lingua", copy.language || "—")}
        ${fact("Editore", copy.publishers || "—")}
        ${fact("Anno edizione", copy.version_year_published || "—")}
        ${fact("Posizione", copy.inventory_location || "—")}
        ${fact("Condizioni", copy.condition || "—")}
      </div>
      ${purchase ? `<p class="copy-note"><strong>Acquisto:</strong> ${escapeHtml(purchase)}</p>` : ""}
      ${copy.notes ? `<p class="copy-note"><strong>Note:</strong> ${escapeHtml(copy.notes)}</p>` : ""}
      <span class="copy-source">${escapeHtml(sourceLabel)}</span>
    </article>
  `;
}


function ragReasonText(reason) {
  const reasons = {
    index_incomplete: "L'indice dei documenti non è completo. Prepara o aggiorna l'indice prima di usare la risposta generata.",
    no_retrieved_evidence: "Non sono state trovate evidenze sufficientemente pertinenti nei documenti indicizzati.",
    retrieved_evidence_insufficient: "Le evidenze recuperate non supportano una risposta affidabile.",
  };
  return reasons[reason] || "Non è disponibile una risposta affidabile per questa domanda.";
}

function ragCohortText(cohort) {
  if (!cohort) return "non specificata";
  const parts = [
    cohort.version_label ? `Versione ${cohort.version_label}` : null,
    cohort.edition ? `Edizione ${cohort.edition}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "versione/edizione non specificata";
}

function ragTrustLabel(document) {
  if (document?.official === true) return "Ufficiale";
  if (document?.source_kind === "community") return "Community";
  if (document?.source_kind === "manual_upload") return "Caricato dall'utente";
  return "Non ufficiale";
}

function ragConflictMarkup(conflicts) {
  if (!conflicts?.has_conflict) return "";
  const selected = ragCohortText(conflicts.selected_cohort);
  const excluded = (conflicts.excluded_cohorts || [])
    .map((cohort) => `<li>${escapeHtml(ragCohortText(cohort))}</li>`)
    .join("");
  return `
    <aside class="rag-conflict" role="note">
      <strong>Conflitto di versione rilevato</strong>
      <p>La risposta usa solo ${escapeHtml(selected)}. Le altre coorti non sono state mescolate.</p>
      ${excluded ? `<ul>${excluded}</ul>` : ""}
    </aside>
  `;
}

function ragCitationCard(citation) {
  const document = citation.document || {};
  const page = citation.page || {};
  const pageNumber = Number.isFinite(Number(page.number))
    ? Math.max(1, Math.trunc(Number(page.number)))
    : 1;
  const documentId = String(document.id || "");
  const language = String(document.language || "und").toUpperCase();
  const version = ragCohortText(document);
  const trust = ragTrustLabel(document);
  const source = document.source_provider || document.source_kind || "Fonte registrata";
  const evidenceCount = Array.isArray(citation.evidence) ? citation.evidence.length : 0;

  return `
    <article class="rag-citation-card" id="ragCitation${Number(citation.index) || 0}">
      <div class="rag-citation-head">
        <div>
          <p class="eyebrow">Citazione ${Number(citation.index) || "?"}</p>
          <strong>Pagina ${pageNumber}</strong>
        </div>
        <div class="document-badges">
          <span class="badge">${escapeHtml(language)}</span>
          <span class="badge ${document.official === true ? "document-official" : "document-unofficial"}">${escapeHtml(trust)}</span>
        </div>
      </div>
      <p class="rag-citation-meta">${escapeHtml(version)} · ${escapeHtml(document.document_type || "documento")} · ${escapeHtml(source)}</p>
      <p class="rag-citation-meta">${evidenceCount} ${evidenceCount === 1 ? "passaggio" : "passaggi"} usati per questa pagina</p>
      <div class="rag-citation-actions">
        <a class="button button-ghost"
           href="/api/documents/${encodeURIComponent(documentId)}/file#page=${pageNumber}"
           target="_blank" rel="noopener noreferrer">Apri PDF · pag. ${pageNumber}</a>
        <button class="button button-ghost rag-document-jump" type="button"
                data-document-id="${escapeHtml(documentId)}">Vai al documento</button>
      </div>
    </article>
  `;
}

function renderRagResult(payload) {
  if (!payload || !["answer", "not_found"].includes(payload.status)) {
    return `
      <section class="rag-state rag-state-error">
        <p class="eyebrow">Risposta non valida</p>
        <h3>Il backend ha restituito un formato inatteso</h3>
        <p>La risposta non viene mostrata perché non rispetta il contratto P7D.</p>
      </section>
    `;
  }
  const conflict = ragConflictMarkup(payload.conflicts);
  if (payload.status === "not_found") {
    const prepare = payload.reason === "index_incomplete"
      ? '<button class="button button-primary rag-prepare-index" type="button">Prepara indice</button>'
      : "";
    return `
      <section class="rag-state rag-state-not-found">
        <p class="eyebrow">Risposta non disponibile</p>
        <h3>Nessuna risposta affidabile</h3>
        <p>${escapeHtml(ragReasonText(payload.reason))}</p>
        ${prepare}
      </section>
      ${conflict}
    `;
  }

  const claims = (payload.claims || []).map((claim) => {
    const refs = (claim.citations || []).map((index) => `
      <button class="rag-citation-ref" type="button"
              data-citation-index="${Number(index)}"
              aria-label="Vai alla citazione ${Number(index)}">[${Number(index)}]</button>
    `).join("");
    const supports = (claim.supports || []).map((support) => `
      <blockquote class="rag-support">
        <span>Supporto [${Number(support.citation)}]</span>
        “${escapeHtml(support.quote)}”
      </blockquote>
    `).join("");
    return `
      <article class="rag-claim">
        <p>${escapeHtml(claim.text)} <span class="rag-claim-refs">${refs}</span></p>
        ${supports}
      </article>
    `;
  }).join("");

  const citations = (payload.citations || []).map(ragCitationCard).join("");
  const tier = payload.retrieval?.selected_tier?.name
    ? `Fonte selezionata: ${payload.retrieval.selected_tier.name}`
    : "Fonte selezionata dal retrieval";
  const generation = payload.generation || {};

  return `
    <section class="rag-answer">
      <div class="rag-answer-head">
        <div>
          <p class="eyebrow">Risposta dai documenti</p>
          <h3>Risposta</h3>
        </div>
        <span class="rag-answer-model">${escapeHtml(generation.model || "modello locale")}</span>
      </div>
      <div class="rag-claims">${claims}</div>
      <p class="rag-retrieval-meta">${escapeHtml(tier)}</p>
    </section>
    ${conflict}
    <section class="rag-citations" aria-label="Citazioni">
      <div class="rag-citations-head">
        <h3>Citazioni e pagine</h3>
        <span>${(payload.citations || []).length}</span>
      </div>
      <div class="rag-citation-list">${citations}</div>
    </section>
  `;
}

function bindRagResultActions(bggId, documentItems) {
  document.querySelectorAll(".rag-citation-ref").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.querySelector(`#ragCitation${button.dataset.citationIndex}`);
      if (!target) return;
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth";
      target.scrollIntoView({behavior, block: "center"});
      target.classList.add("rag-highlight");
      window.setTimeout(() => target.classList.remove("rag-highlight"), 1400);
    });
  });

  document.querySelectorAll(".rag-document-jump").forEach((button) => {
    button.addEventListener("click", () => {
      const target = Array.from(document.querySelectorAll(".game-document-card"))
        .find((card) => card.dataset.documentId === button.dataset.documentId);
      if (!target) {
        showToast("Documento non presente nell'elenco corrente.", true);
        return;
      }
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth";
      target.scrollIntoView({behavior, block: "center"});
      target.classList.add("rag-highlight");
      window.setTimeout(() => target.classList.remove("rag-highlight"), 1400);
    });
  });

  document.querySelectorAll(".rag-prepare-index").forEach((button) => {
    button.addEventListener("click", () => {
      void prepareRagIndex(bggId, documentItems);
    });
  });
}

function ragIndexFailureText(_item) {
  return "Assistente temporaneamente non disponibile.";
}

async function refreshRagIndexStatus(bggId, documentItems, {poll = true} = {}) {
  const status = document.querySelector("#ragIndexStatus");
  const retry = document.querySelector(".rag-prepare-index");
  const currentPath = window.location.pathname.replace(/\/+$/, "");
  if (!status || currentPath !== "/games/" + bggId) return;

  if (!documentItems.length) {
    status.className = "rag-index-status muted";
    status.textContent = "Aggiungi un regolamento per rendere disponibile l’assistente.";
    if (retry) retry.hidden = true;
    return;
  }

  try {
    const jobs = await Promise.all(
      documentItems.map((item) =>
        api("/api/document-index-jobs?document_id=" + encodeURIComponent(item.id) + "&limit=1")
      ),
    );
    const rows = jobs.flatMap((payload) => payload.items || []);
    if (rows.length < documentItems.length) {
      status.className = "rag-index-status";
      status.textContent = "Assistente in preparazione…";
      if (retry) retry.hidden = true;
      if (poll) window.setTimeout(() => void refreshRagIndexStatus(bggId, documentItems), 3000);
      return;
    }

    const failed = rows.filter((item) => item.status === "failed");
    const running = rows.filter((item) => item.status === "pending" || item.status === "running");
    const ready = rows.filter((item) => item.status === "succeeded");

    if (failed.length) {
      status.className = "rag-index-status error";
      status.textContent = ragIndexFailureText(failed[0]);
      if (retry) {
        retry.hidden = false;
        retry.disabled = false;
        retry.textContent = "Riprova preparazione";
      }
      return;
    }

    if (running.length) {
      status.className = "rag-index-status";
      status.textContent = "Assistente in preparazione…";
      if (retry) retry.hidden = true;
      if (poll) window.setTimeout(() => void refreshRagIndexStatus(bggId, documentItems), 3000);
      return;
    }

    if (ready.length === documentItems.length) {
      status.className = "rag-index-status success";
      status.textContent = "✓ Assistente disponibile";
      if (retry) retry.hidden = true;
      return;
    }

    status.className = "rag-index-status";
    status.textContent = "Assistente in preparazione…";
    if (retry) retry.hidden = true;
  } catch (_) {
    status.className = "rag-index-status error";
    status.textContent = "Assistente temporaneamente non disponibile.";
    if (retry) {
      retry.hidden = false;
      retry.disabled = false;
      retry.textContent = "Riprova preparazione";
    }
  }
}

async function prepareRagIndex(bggId, documentItems) {
  const panel = document.querySelector("#ragPanel");
  const status = document.querySelector("#ragIndexStatus");
  const retry = document.querySelector(".rag-prepare-index");
  if (!panel || !status || panel.dataset.indexBusy === "true") return;
  if (!documentItems.length) {
    showToast("Aggiungi prima un regolamento PDF.", true);
    return;
  }

  panel.dataset.indexBusy = "true";
  if (retry) {
    retry.disabled = true;
    retry.textContent = "Riprovo…";
  }
  status.className = "rag-index-status";
  status.textContent = "Riprovo la preparazione dell’assistente…";
  try {
    for (const item of documentItems) {
      try {
        await api(
          "/api/documents/" + encodeURIComponent(item.id) + "/auto-index/run",
          {method: "POST"},
        );
      } catch (error) {
        if (error.status !== 409) throw error;
      }
    }
    showToast("Assistente disponibile.");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    panel.dataset.indexBusy = "false";
    if (retry) retry.disabled = false;
    await refreshRagIndexStatus(bggId, documentItems, {poll: false});
  }
}

async function submitRagQuestion(bggId, documentItems) {
  const form = document.querySelector("#ragQueryForm");
  const result = document.querySelector("#ragResult");
  const submit = document.querySelector("#ragAsk");
  if (!form || !result || !submit || submit.disabled) return;

  const query = document.querySelector("#ragQuestion")?.value.trim() || "";
  if (!query) return;
  const payload = {
    query,
    language: document.querySelector("#ragLanguage")?.value || null,
    document_type: document.querySelector("#ragDocumentType")?.value || null,
    version_label: document.querySelector("#ragVersion")?.value.trim() || null,
    edition: document.querySelector("#ragEdition")?.value.trim() || null,
  };

  submit.disabled = true;
  submit.textContent = "Cerco…";
  result.innerHTML = '<div class="rag-loading" role="status">Cerco nei documenti e verifico le fonti…</div>';
  try {
    const answer = await api(`/api/games/${encodeURIComponent(bggId)}/answer`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    if (window.location.pathname.replace(/\/+$/, "") !== `/games/${bggId}`) return;
    result.innerHTML = renderRagResult(answer);
    bindRagResultActions(bggId, documentItems);
  } catch (error) {
    if (window.location.pathname.replace(/\/+$/, "") !== `/games/${bggId}`) return;
    result.innerHTML = `
      <section class="rag-state rag-state-error">
        <p class="eyebrow">Errore RAG</p>
        <h3>La domanda non può essere elaborata</h3>
        <p>${escapeHtml(error.message)}</p>
      </section>
    `;
  } finally {
    if (document.querySelector("#ragAsk")) {
      submit.disabled = false;
      submit.textContent = "Chiedi";
    }
  }
}

function setupRagPanel(bggId, documentItems) {
  const form = document.querySelector("#ragQueryForm");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitRagQuestion(bggId, documentItems);
  });
  document.querySelectorAll(".rag-prepare-index").forEach((button) => {
    button.disabled = !documentItems.length;
    button.addEventListener("click", () => {
      void prepareRagIndex(bggId, documentItems);
    });
  });
  void refreshRagIndexStatus(bggId, documentItems);
}

function descriptionSourcesText(description) {
  if (!description?.text) return "";
  const sources = description.sources || {};
  const parts = ["descrizione dell'editore e dati BGG"];
  if (sources.rulebook?.pages?.length) parts.push(`regolamento (pp. ${sources.rulebook.pages.join(", ")})`);
  if (sources.community?.comments_sampled) {
    parts.push(`sintesi di ${sources.community.comments_sampled} commenti BGG su ${sources.community.comments_total}`);
  }
  const author = [description.provider, description.model].filter(Boolean).join(" · ");
  return `Fonti: ${parts.join(" · ")}.${author ? ` Scritta da ${author}.` : ""}`;
}

function showDescriptionSources(description) {
  const node = document.querySelector("#gameDescriptionSources");
  const text = descriptionSourcesText(description);
  if (!node?.isConnected || !text) return;
  node.textContent = text;
  node.hidden = false;
}

// The description (and the AI text built from it) needs the BGG publisher text:
// fetch the BGG metadata first when it is not stored yet.
async function ensureDescriptionSource(bggId) {
  const status = await api(`/api/games/${bggId}/description-it`);
  if (status.source_available) return status;
  const metadata = await api(`/api/games/${bggId}/bgg-metadata/refresh`, {method: "POST"});
  const cover = document.querySelector(".game-summary-cover .detail-cover");
  if (cover?.isConnected && metadata.cover_url) {
    const placeholder = cover.querySelector(".cover-image, .cover-initials");
    if (placeholder) placeholder.outerHTML = `<img class="cover-image" src="${coverSrc(bggId)}" alt="" referrerpolicy="no-referrer">`;
  }
  return api(`/api/games/${bggId}/description-it`);
}

async function loadItalianTranslation(bggId) {
  const status = await ensureDescriptionSource(bggId);
  if (status.translation?.translated_text) return status.translation.translated_text;
  if (!status.source_available) return "";
  const translated = await api(`/api/games/${bggId}/description-it/translate`, {method: "POST"});
  return translated.translation?.translated_text || "";
}

function setDescriptionBusy(busy) {
  const button = document.querySelector("#regenerateDescription");
  if (!button?.isConnected) return;
  button.disabled = busy;
  const label = button.querySelector("span");
  if (label) label.textContent = busy ? "Scrittura in corso…" : "Rigenera descrizione";
}

async function regenerateGameDescription(bggId) {
  const node = document.querySelector("#gameDescriptionText");
  if (!node?.isConnected) return;
  setDescriptionBusy(true);
  node.setAttribute("aria-busy", "true");
  try {
    const result = await api(`/api/games/${bggId}/description-ai/generate?force=true`, {method: "POST"});
    const text = result.description?.text;
    if (text && node.isConnected) {
      node.textContent = text;
      node.dataset.source = "ai";
      showDescriptionSources(result.description);
      showToast("Descrizione rigenerata.");
    }
  } catch (error) {
    // The current text stays on screen: it is only replaced once a new one exists.
    showToast(`Rigenerazione non riuscita: ${error.message}`, true);
  } finally {
    node.removeAttribute("aria-busy");
    setDescriptionBusy(false);
  }
}

// The AI description is written the first time a game page is opened. Until it is
// ready the stored translation of the publisher text (if any) stays on screen; the
// translation is only produced as a fallback when the AI text cannot be written.
async function ensureGameDescription(bggId) {
  const node = document.querySelector("#gameDescriptionText");
  if (!node?.isConnected || navigator.webdriver || node.dataset.source === "ai") return;
  if (!node.dataset.source) {
    node.textContent = "Sto scrivendo la descrizione di questo gioco… può richiedere fino a un minuto.";
  }
  setDescriptionBusy(true);
  try {
    await ensureDescriptionSource(bggId);
    const generated = await api(`/api/games/${bggId}/description-ai/generate`, {method: "POST"});
    const text = generated.description?.text;
    if (text && node.isConnected) {
      node.textContent = text;
      node.dataset.source = "ai";
      showDescriptionSources(generated.description);
    }
  } catch (_) {
    try {
      const text = await loadItalianTranslation(bggId);
      if (text && node.isConnected && node.dataset.source !== "ai") {
        node.textContent = text;
        node.dataset.source = "translation";
      }
    } catch (__) {
      // Nothing more to try: the message below covers it.
    }
    if (node.isConnected && !node.dataset.source) {
      node.textContent = "Descrizione non disponibile al momento.";
    }
  } finally {
    setDescriptionBusy(false);
  }
}

function relevantExpansionCard(item) {
  return `
    <article class="relevant-expansion-card ${item.owned ? "is-owned" : "is-missing"}"
             data-expansion-id="${Number(item.bgg_id)}">
      <a class="relevant-expansion-cover" href="${escapeHtml(item.url)}"
         target="_blank" rel="noopener noreferrer">
        ${item.cover_url
          ? `<img src="${escapeHtml(coverSrc(item.bgg_id, item.cover_url))}" alt="Cover di ${escapeHtml(item.title)}" loading="lazy" referrerpolicy="no-referrer">`
          : `<span class="cover-initials">${escapeHtml(initials(item.title))}</span>`}
      </a>
      <div class="relevant-expansion-copy">
        <div class="relevant-expansion-title-row">
          <strong>${escapeHtml(item.title)}</strong>
          <span class="badge ${item.owned ? "is-owned" : "is-missing"}">
            ${item.owned ? "✓ Posseduta" : "Non posseduta"}
          </span>
        </div>
        <small>${item.year_published || "Anno —"}</small>
        <a class="external-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
          Apri su BGG ${icon("external")}
        </a>
      </div>
    </article>
  `;
}

async function loadRelevantExpansions(bggId) {
  const section = document.querySelector("#relevantExpansionsSection");
  const grid = document.querySelector("#relevantExpansionsGrid");
  if (!section || !grid) return;
  try {
    const payload = await api(`/api/games/${bggId}/expansions`);
    if (!section.isConnected || !grid.isConnected) return;
    const items = Array.isArray(payload.items) ? payload.items : [];
    if (!items.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    grid.innerHTML = items.map(relevantExpansionCard).join("");
    const selected = new URLSearchParams(window.location.search).get("expansion");
    if (selected) {
      const card = grid.querySelector(`[data-expansion-id="${CSS.escape(selected)}"]`);
      if (card) {
        card.classList.add("is-highlighted");
        card.scrollIntoView({behavior: "smooth", block: "center"});
      }
    }
  } catch (_) {
    section.hidden = true;
  }
}

async function renderDetail(bggId) {
  app.innerHTML = `
    <a class="detail-back" href="/" data-nav>← Torna alla ludoteca</a>
    <section class="game-page game-page-loading">
      <div class="game-summary-rail"><div class="skeleton"></div></div>
      <div class="game-main"><div class="skeleton"></div></div>
    </section>
  `;
  const requestedPath = window.location.pathname;
  try {
    const [game, documents, tutorials] = await Promise.all([
      api(`/api/games/${bggId}`),
      api(`/api/games/${bggId}/documents`),
      api(`/api/games/${bggId}/tutorial-videos`),
    ]);
    if (window.location.pathname !== requestedPath) return;

    const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
    const collection = game.collection || {};
    const bgg = game.bgg || {};
    const metadata = game.bgg_metadata || {};
    const documentItems = documents.items || [];
    const tutorialItems = tutorials.items || [];
    const rulebooks = documentItems.filter((item) => item.document_type === "rulebook");
    const italianDescription = String(game.description_it || "").trim();
    const aiDescription = String(game.description_ai?.text || "").trim();
    const descriptionSource = aiDescription ? "ai" : italianDescription ? "translation" : "";
    const description = aiDescription || italianDescription
      ? escapeHtml(aiDescription || italianDescription)
      : "Descrizione in preparazione…";
    const firstRulebook = rulebooks[0] || null;

    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna alla ludoteca</a>

      <section class="game-page game-centric-detail">
        <aside class="game-summary-rail" aria-label="Riepilogo gioco">
          <div class="game-summary-cover">
            <div class="detail-cover">
              ${metadata.cover_url
                ? `<img class="cover-image" src="${coverSrc(game.bgg_id)}" alt="Cover di ${escapeHtml(game.title)}" referrerpolicy="no-referrer">`
                : `<span class="cover-initials">${escapeHtml(initials(game.title))}</span>`}
              <div class="cover-rating-overlay" aria-label="Valutazione personale"
                   title="${game.progress?.rating ? `Il tuo voto: ${String(game.progress.rating).replace(".", ",")}/5` : "Non valutato"}">
                ${starRatingMarkup(game.progress?.rating, {interactive: true})}
              </div>
              ${bggRatingBadge(bgg)}
            </div>
          </div>

          <div class="game-summary-card">
            <div class="game-summary-badges">
              <span class="badge">${type}</span>
              ${collection.own ? '<span class="badge">✓ Posseduto</span>' : ""}
              ${game.year_published ? `<span class="badge">${game.year_published}</span>` : ""}
            </div>
            <dl class="game-summary-list game-facts-primary">
              ${playerChartMarkup(game, metadata.metadata?.player_poll)}
              <div><dt>Età ufficiale</dt><dd>${escapeHtml(ageText(game))}</dd></div>
              <div><dt>Durata</dt><dd>${escapeHtml(timeText(game))}</dd></div>
              <div><dt>Complessità</dt><dd>${bgg.average_weight ? `${formatNumber(bgg.average_weight, 2)} / 5` : "—"}</dd></div>
              <div><dt>Dipendenza lingua</dt><dd ${bgg.language_dependence ? `title="${escapeHtml(bgg.language_dependence)}"` : ""}>${escapeHtml(languageDependenceText(bgg.language_dependence))}</dd></div>
            </dl>
            <a class="external-link game-bgg-link"
               href="https://boardgamegeek.com/boardgame/${game.bgg_id}"
               target="_blank" rel="noopener noreferrer">Apri su BoardGameGeek ${icon("external")}</a>
          </div>
        </aside>

        <article class="game-main detail-main">
          <header class="game-header game-header-player">
            <div class="game-title-block">
              <h1>${escapeHtml(game.title)}</h1>
              <span class="game-title-meta">BGG #${game.bgg_id}</span>
            </div>
            <div class="game-primary-actions">
              <button class="game-state-icon ${game.progress?.played ? "played-button is-played" : "played-button"}"
                      id="togglePlayed" type="button"
                      aria-pressed="${game.progress?.played ? "true" : "false"}"
                      aria-label="${game.progress?.played ? "Rimuovi stato giocato" : "Segna come giocato"}"
                      title="${game.progress?.played ? "Giocato" : "Segna come giocato"}">
                <span aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="/static/icons.svg#i-check"/></svg></span>
              </button>
              <button class="game-state-icon ${game.progress?.completed ? "completion-button is-completed" : "completion-button"}"
                      id="toggleCompleted" type="button"
                      aria-pressed="${game.progress?.completed ? "true" : "false"}"
                      aria-label="${game.progress?.completed ? "Rimuovi completamento" : "Segna come completato"}"
                      title="${game.progress?.completed ? "Completato" : "Segna come completato"}">
                <span aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="/static/icons.svg#i-crown"/></svg></span>
              </button>
              ${game.progress?.completed ? `
                <label class="completion-date-editor" for="completionDate">
                  <span>Completato il</span>
                  <input id="completionDate" type="date"
                         value="${escapeHtml(game.progress.completed_at || "")}"
                         max="${new Date().toISOString().slice(0, 10)}">
                </label>
                <button class="button button-ghost completion-date-save" id="saveCompletionDate" type="button">Salva data</button>
              ` : ""}
            </div>
          </header>

          <section class="game-description-panel">
            <div class="game-description-text" id="gameDescriptionText" data-source="${descriptionSource}">${description}</div>
            <p class="game-description-sources" id="gameDescriptionSources" ${aiDescription ? "" : "hidden"}>${escapeHtml(descriptionSourcesText(game.description_ai))}</p>
            <div class="game-description-actions">
              <button class="button button-ghost" id="regenerateDescription" type="button"
                      title="Riscrive la descrizione con il prompt e i provider attuali">${icon("refresh")}<span>Rigenera descrizione</span></button>
            </div>
          </section>

          <section class="game-section game-plays-section" aria-labelledby="gamePlaysTitle">
            <div class="simple-rulebook-head">
              <h2 class="eyebrow section-eyebrow" id="gamePlaysTitle">Partite <small id="gamePlaysCount"></small></h2>
              <button class="button button-primary" id="gameAddPlay" type="button">${icon("plus")}<span>Registra partita</span></button>
            </div>
            <div class="game-plays-list" id="gamePlaysList"><div class="skeleton"></div></div>
          </section>

          <section class="game-section relevant-expansions-section" id="relevantExpansionsSection" aria-labelledby="relevantExpansionsTitle">
            <div class="simple-rulebook-head">
              <h2 class="eyebrow section-eyebrow" id="relevantExpansionsTitle">Espansioni</h2>
            </div>
            <div class="relevant-expansions-grid" id="relevantExpansionsGrid">
              <div class="skeleton"></div><div class="skeleton"></div>
            </div>
          </section>

          <section class="game-section tutorial-videos-section" aria-labelledby="tutorialVideosTitle">
            <div class="simple-rulebook-head">
              <h2 class="eyebrow section-eyebrow" id="tutorialVideosTitle">Video tutorial</h2>
              <button class="button button-ghost" id="tutorialDiscoveryAction" type="button">
                ${tutorials.configured ? (tutorialItems.length ? "Aggiorna video" : "Cerca video") : "Configura YouTube API"}
              </button>
            </div>
            ${tutorialItems.length
              ? `<div class="tutorial-video-grid">${tutorialItems.map(tutorialVideoCard).join("")}</div>`
              : `<div class="tutorial-video-empty">
                   ${tutorials.configured
                     ? "Nessun tutorial selezionato. Avvia la ricerca automatica per italiano e inglese."
                     : "Configura una YouTube Data API key per trovare automaticamente tutorial ufficiali e community."}
                 </div>`}
          </section>

          <section class="game-section rules-workspace rules-simple" aria-labelledby="rulesWorkspaceTitle">
            <div class="simple-rulebook-head">
              <h2 class="eyebrow section-eyebrow" id="rulesWorkspaceTitle">Regolamento</h2>
              <div class="simple-rulebook-status">
                <span class="rulebook-presence ${rulebooks.length ? "is-present" : "is-missing"}">
                  ${rulebooks.length ? "✓ Regolamento presente" : "Regolamento non presente"}
                </span>
                <span class="rag-index-status" id="ragIndexStatus" role="status">Controllo disponibilità assistente…</span>
                <button class="button button-ghost rag-prepare-index" type="button" hidden
                        ${documentItems.length ? "" : "disabled"}>Riprova preparazione</button>
              </div>
            </div>

            <div class="simple-rulebook-actions">
              <button class="button button-primary" id="rulebookSearchAction" type="button">Cerca automaticamente</button>
              <button class="button button-ghost" id="addDocument" type="button">Upload</button>
              ${firstRulebook ? `<a class="button button-ghost" href="/api/documents/${encodeURIComponent(firstRulebook.id)}/file" target="_blank" rel="noopener noreferrer">Apri</a>` : ""}
            </div>
            <p id="gameDiscoveryStatus" hidden></p>
            <div class="game-document-list visually-hidden" id="gameDocumentList" aria-hidden="true">
              ${documentItems.map(documentCard).join("")}
            </div>

            <section class="rag-panel rag-panel-secondary simple-rag" id="ragPanel" data-index-busy="false">
              <form class="rag-query-form" id="ragQueryForm">
                <label class="rag-question-field" for="ragQuestion">
                  <textarea id="ragQuestion" rows="3" maxlength="4000" required
                    placeholder="Scrivi qui la tua domanda sulle regole…"></textarea>
                </label>
                <div class="visually-hidden" aria-hidden="true">
                  <select id="ragLanguage"><option value="it" selected>Italiano</option><option value="en">English</option><option value="">Qualsiasi</option></select>
                  <select id="ragDocumentType"><option value="">Tutti i documenti</option><option value="rulebook">Regolamento</option></select>
                  <input id="ragVersion" type="text">
                  <input id="ragEdition" type="text">
                </div>
                <div class="rag-query-actions simple-rag-actions">
                  <button class="button button-primary" id="ragAsk" type="submit">Chiedi</button>
                </div>
              </form>
              <div class="rag-result" id="ragResult" aria-live="polite">
<div class="rag-empty" hidden></div>
              </div>
            </section>
          </section>

        </article>
      </section>
    `;

    document.querySelector("#togglePlayed")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const next = !Boolean(game.progress?.played);
        await api(`/api/games/${game.bgg_id}/personal-state`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({played: next}),
        });
        showToast(next ? "Gioco segnato come giocato." : "Stato giocato rimosso.");
        await renderDetail(game.bgg_id);
      } catch (error) {
        showToast(error.message, true);
        button.disabled = false;
      }
    });
    document.querySelectorAll(".cover-rating-overlay .personal-stars").forEach((group) => {
      const preview = (value) => {
        group.classList.toggle("is-previewing", value !== null);
        group.querySelectorAll(".personal-star-control").forEach((control, index) => {
          const star = index + 1;
          control.classList.toggle("is-preview", value !== null && value >= star);
          control.classList.toggle("is-preview-half", value !== null && value === star - 0.5);
        });
      };
      group.querySelectorAll("[data-personal-rating]").forEach((button) => {
        button.addEventListener("mouseenter", () => preview(Number(button.dataset.personalRating)));
        button.addEventListener("focus", () => preview(Number(button.dataset.personalRating)));
      });
      group.addEventListener("mouseleave", () => preview(null));
      group.addEventListener("focusout", (event) => {
        if (!group.contains(event.relatedTarget)) preview(null);
      });
    });
    document.querySelectorAll("[data-personal-rating]").forEach((button) => {
      button.addEventListener("click", async () => {
        const selected = Number(button.dataset.personalRating);
        const next = Number(game.progress?.rating || 0) === selected ? null : selected;
        try {
          await api(`/api/games/${game.bgg_id}/personal-state`, {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({rating: next}),
          });
          showToast(next ? `Valutazione personale: ${next}/5.` : "Valutazione personale rimossa.");
          await renderDetail(game.bgg_id);
        } catch (error) {
          showToast(error.message, true);
        }
      });
    });
    document.querySelector("#toggleCompleted")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const next = !Boolean(game.progress?.completed);
        await api(`/api/games/${game.bgg_id}/completion`, {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({completed: next}),
        });
        showToast(next ? "Gioco segnato come completato." : "Completamento rimosso; resta giocato se applicabile.");
        await renderDetail(game.bgg_id);
      } catch (error) {
        showToast(error.message, true);
        button.disabled = false;
      }
    });
    document.querySelector("#saveCompletionDate")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const input = document.querySelector("#completionDate");
      const completedAt = String(input?.value || "").trim();
      if (!completedAt) {
        showToast("Seleziona una data di completamento.", true);
        input?.focus();
        return;
      }
      button.disabled = true;
      try {
        await api(`/api/games/${game.bgg_id}/completion`, {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({completed: true, completed_at: completedAt}),
        });
        showToast("Data di completamento aggiornata.");
        await renderDetail(game.bgg_id);
      } catch (error) {
        showToast(error.message, true);
        button.disabled = false;
      }
    });
    document.querySelector("#addDocument")?.addEventListener("click", () => {
      openDocumentDialog(game.bgg_id, game.title);
    });
    setupRagPanel(game.bgg_id, documentItems);
    setupGameDiscovery(game.bgg_id, game.title);
    setupTutorialDiscovery(game.bgg_id, Boolean(tutorials.configured));
    document.querySelector("#regenerateDescription")?.addEventListener("click", () => {
      void regenerateGameDescription(game.bgg_id);
    });
    ensureGameDescription(game.bgg_id);
    void loadRelevantExpansions(game.bgg_id);
    void refreshGamePlays(game);
    document.querySelector("#gameAddPlay")?.addEventListener("click", () => {
      void openPlayDialog({
        bggId: game.bgg_id,
        title: game.title,
        // Logging a play can mark the game played or completed: reload the header too.
        onSaved: () => renderDetail(game.bgg_id),
      });
    });

    document.title = `${game.title} · BoardGameCompanion`;
  } catch (error) {
    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna alla ludoteca</a>
      <div class="empty">Impossibile caricare il gioco: ${escapeHtml(error.message)}</div>
    `;
    showToast(error.message, true);
  }
}

function setupTutorialDiscovery(bggId, configured) {
  const button = document.querySelector("#tutorialDiscoveryAction");
  if (!button) return;
  button.addEventListener("click", async () => {
    if (!configured) {
      void openSettingsDialog("general");
      return;
    }
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Ricerca video…";
    try {
      const result = await api(`/api/games/${bggId}/tutorial-videos/discover`, {
        method: "POST",
      });
      showToast(
        result.count
          ? `Tutorial aggiornati: ${result.count} video selezionati.`
          : "Nessun tutorial pertinente trovato.",
      );
      await renderDetail(bggId);
    } catch (error) {
      showToast(error.message, true);
      button.disabled = false;
      button.textContent = original;
    }
  });
}

async function setupGameDiscovery(bggId, gameTitle) {
  const status = document.querySelector("#gameDiscoveryStatus");
  const button = document.querySelector("#rulebookSearchAction");
  const gamePath = window.location.pathname;
  const googleUrl = googleRulebookSearchUrl(gameTitle);

  const setButtonState = (item) => {
    if (!button?.isConnected) return;
    const candidates = Number(item?.candidates_found || 0);
    const failures = Number(item?.provider_failures || 0);
    const completed = Boolean(item?.last_finished_at);
    const availability = item?.availability || null;
    const knownSourceMiss = completed && candidates === 0;
    const externalUrl = availability?.external_url || "";
    if (availability?.action === "open_external" && externalUrl) {
      button.dataset.mode = "external";
      button.dataset.externalUrl = externalUrl;
      button.innerHTML = `Apri manuale esterno ${icon("external")}`;
      return;
    }
    button.dataset.mode = knownSourceMiss && !availability ? "google" : "discovery";
    button.dataset.googleUrl = googleUrl;
    if (knownSourceMiss && availability) {
      button.textContent = "Riprova fonti ufficiali";
    } else if (knownSourceMiss) {
      button.innerHTML = `Cerca su Google ${icon("external")}`;
    } else if (failures > 0) {
      button.textContent = "Riprova ricerca automatica";
    } else if (candidates > 0) {
      button.textContent = "Aggiorna ricerca automatica";
    } else {
      button.textContent = "Cerca automaticamente";
    }
  };

  const refresh = async () => {
    if (!status?.isConnected || window.location.pathname !== gamePath) return;
    try {
      const [item, documents] = await Promise.all([
        api(`/api/games/${bggId}/rulebook-discovery`),
        api(`/api/games/${bggId}/documents`),
      ]);
      if (!status.isConnected || window.location.pathname !== gamePath) return;
      const stored = (documents.items || []).filter((value) => value.document_type === "rulebook");
      const italian = stored.filter((value) => String(value.language || "").split("-")[0] === "it");
      const fetched = stored.filter((value) => value.provenance?.ingest === "scheduled_rulebook_fetch");
      const candidates = Number(item.candidates_found || 0);
      const failures = Number(item.provider_failures || 0);
      const availability = item.availability || null;
      const availabilityText = availability?.label ? ` · Stato: ${availability.label}` : "";
      status.textContent = `PDF archiviati: ${stored.length} (${italian.length} IT; ${fetched.length} acquisiti automaticamente) · Fonti trovate: ${candidates} · Errori di ricerca: ${failures} · Ultima ricerca: ${item.last_finished_at || "mai"}${availabilityText}.`;
      if (availability?.detail) status.title = availability.detail;
      else status.removeAttribute("title");
      setButtonState(item);
    } catch (error) {
      if (status.isConnected) status.textContent = error.message;
      if (button?.isConnected) {
        button.dataset.mode = "discovery";
        button.textContent = "Riprova ricerca automatica";
      }
    }
  };

  button?.addEventListener("click", async () => {
    if (button.dataset.mode === "google") {
      const target = button.dataset.googleUrl || googleUrl;
      const opened = window.open(target, "_blank", "noopener,noreferrer");
      if (opened) opened.opener = null;
      return;
    }
    if (button.dataset.mode === "external") {
      const target = button.dataset.externalUrl;
      if (target) {
        const opened = window.open(target, "_blank", "noopener,noreferrer");
        if (opened) opened.opener = null;
      }
      return;
    }

    button.disabled = true;
    button.textContent = "Ricerca e acquisizione…";
    try {
      const result = await api(`/api/games/${bggId}/rulebook-acquire/run`, {method: "POST"});
      const discovery = result.discovery || {};
      const acquisition = result.acquisition || {};
      const found = Number(discovery.candidates_found || 0);
      const failures = Number(discovery.provider_failures || 0);
      const pending = (discovery.review_items || []).filter((value) => value.status === "pending").length;
      const runs = acquisition.results || [];
      const created = runs.filter((value) => value.outcome === "created").length;
      const unchanged = runs.filter((value) => value.outcome === "unchanged").length;
      const acquisitionFailed = runs.filter((value) => value.outcome === "failed").length;
      const availability = result.availability || discovery.availability || null;
      if (created) {
        showToast("Regolamento ufficiale acquisito. Indicizzazione avviata automaticamente.");
      } else if (unchanged) {
        showToast("Il regolamento ufficiale è già archiviato ed è stato verificato.");
      } else if (pending) {
        showToast(`Trovata ${pending === 1 ? "una fonte da verificare" : `${pending} fonti da verificare`}. Nessun PDF dubbio è stato scaricato automaticamente.`);
      } else if (acquisitionFailed) {
        showToast("Fonte ufficiale trovata, ma l'acquisizione del PDF non è riuscita. Puoi riprovare.", true);
      } else if (found) {
        showToast("Fonti trovate, ma nessuna soddisfa i criteri per l'acquisizione automatica.");
      } else if (availability?.label) {
        showToast(availability.label);
      } else if (failures) {
        showToast("Nessuna fonte trovata; alcune fonti note non hanno risposto. Premi di nuovo per cercare il PDF su Google.");
      } else {
        showToast("Nessuna fonte nota trovata. Premi di nuovo per cercare il PDF su Google.");
      }
      await refresh();
    } catch (error) {
      showToast(error.message, true);
      await refresh();
    } finally {
      button.disabled = false;
    }
  });
  await refresh();
}
async function renderDiscovery() {
  app.innerHTML = '<div class="empty">Caricamento discovery…</div>';
  try {
    const data = await api("/api/rulebook-discovery?limit=500");
    app.innerHTML = `
      <section class="admin-page review-page">
        <div class="review-page-head admin-page-head">
          <div><h1>Ricerca regolamenti</h1><p class="muted catalog-page-summary">Cerca fonti per i giochi del catalogo e segui gli esiti delle acquisizioni</p></div>
          <button class="button button-primary" id="runDiscoveryBatch" type="button">Cerca su 5 giochi</button>
        </div>
        <div class="update-list">
          ${data.items.map((item) => `<article class="update-card">
            <div><strong>${escapeHtml(item.title)}</strong> <span class="badge">BGG #${item.bgg_id}</span></div>
            <p class="muted">${escapeHtml(item.status)} · ultimo: ${escapeHtml(item.last_finished_at || "mai")} · fonti trovate: ${item.candidates_found} · da verificare: ${item.review_items_created}</p>
            <p class="muted">${(item.providers || []).map((value) => `${escapeHtml(value.provider)}: ${escapeHtml(value.outcome)} (${value.candidate_count})`).join(" · ") || "Nessun provider ancora interrogato"}</p>
            ${item.last_error ? `<p class="integration-error">${escapeHtml(item.last_error)}</p>` : ""}
            <a class="external-link" href="/games/${item.bgg_id}" data-nav>Apri gioco ${icon("arrow-right")}</a>
          </article>`).join("") || '<div class="empty">Nessun gioco nel catalogo.</div>'}
        </div>
      </section>`;
    document.querySelector("#runDiscoveryBatch")?.addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      try {
        const result = await api("/api/rulebook-discovery/run?limit=5", {method: "POST"});
        showToast(`Ricerca completata per ${result.attempted} giochi.`);
        await renderDiscovery();
      } catch (error) {
        showToast(error.message, true);
        event.currentTarget.disabled = false;
      }
    });
    document.title = "Ricerca regolamenti · BoardGameCompanion";
  } catch (error) {
    app.innerHTML = `<div class="empty">Impossibile caricare la ricerca regolamenti: ${escapeHtml(error.message)}</div>`;
  }
}

const REVIEW_PAGE_SIZE = 50;
let reviewPendingOffset = 0;
let reviewDecidedOffset = 0;


function reviewPager(data, section) {
  if (data.total <= data.limit) return "";
  const start = data.total ? data.offset + 1 : 0;
  const end = Math.min(data.offset + data.limit, data.total);
  const previousOffset = Math.max(0, data.offset - data.limit);
  const nextOffset = data.offset + data.limit;

  return `
    <div class="review-pagination">
      <span>${start}–${end} di ${data.total}</span>
      <div>
        <button class="button button-ghost review-page-button"
          data-review-section="${section}"
          data-review-offset="${previousOffset}"
          type="button" ${data.offset === 0 ? "disabled" : ""}>Precedente</button>
        <button class="button button-ghost review-page-button"
          data-review-section="${section}"
          data-review-offset="${nextOffset}"
          type="button" ${nextOffset >= data.total ? "disabled" : ""}>Successiva</button>
      </div>
    </div>
  `;
}


function reviewCard(item) {
  const candidate = item.candidate || {};
  const pending = item.status === "pending";
  const statusLabel = item.status === "approved"
    ? (item.decision_source === "policy" ? "Auto-approvato" : "Approvato")
    : item.status === "rejected" ? "Rifiutato" : "Da verificare";
  const source = String(candidate.source_kind || "unknown").replaceAll("_", " ");
  const reasons = (item.policy_reasons || [])
    .map((reason) => `<span class="review-reason">${escapeHtml(reason)}</span>`)
    .join("");

  return `
    <article class="review-card">
      <div class="review-card-head">
        <div>
          <p class="eyebrow">${escapeHtml(source)} · confidenza ${escapeHtml(candidate.confidence ?? "—")}</p>
          <h3><a href="/games/${item.bgg_id}" data-nav>${escapeHtml(item.game_title)}</a></h3>
        </div>
        <span class="review-status review-status-${escapeHtml(item.status)}">${statusLabel}</span>
      </div>
      <div class="review-meta">
        <span>${escapeHtml(candidate.language || "und")}</span>
        <span>${escapeHtml(candidate.document_type || "rulebook")}</span>
        <span>${candidate.official ? "ufficiale" : "non ufficiale"}</span>
      </div>
      <a class="review-url" href="${escapeHtml(candidate.url || "#")}" target="_blank" rel="noopener noreferrer">
        ${escapeHtml(candidate.url || "URL non disponibile")}
      </a>
      <div class="review-reasons">${reasons}</div>
      ${item.decision_note ? `<p class="review-note">${escapeHtml(item.decision_note)}</p>` : ""}
      ${pending ? `
        <div class="review-actions">
          <button class="button button-ghost review-decision" data-review-id="${item.id}" data-decision="rejected" type="button">Rifiuta</button>
          <button class="button button-primary review-decision" data-review-id="${item.id}" data-decision="approved" type="button">Approva</button>
        </div>
      ` : ""}
    </article>
  `;
}


async function decideReviewItem(reviewId, decision) {
  const buttons = document.querySelectorAll(`.review-decision[data-review-id="${reviewId}"]`);
  buttons.forEach((button) => { button.disabled = true; });
  try {
    await api(`/api/rulebook-reviews/${reviewId}/decision`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({decision}),
    });
    showToast(decision === "approved" ? "Candidato approvato." : "Candidato rifiutato.");
    await renderReviews();
  } catch (error) {
    showToast(error.message, true);
    if (error.status === 409) {
      await renderReviews();
      return;
    }
    buttons.forEach((button) => { button.disabled = false; });
  }
}


async function renderReviews({reset = false} = {}) {
  if (reset) {
    reviewPendingOffset = 0;
    reviewDecidedOffset = 0;
  }
  app.innerHTML = '<div class="empty">Caricamento fonti da verificare…</div>';
  try {
    const [pendingData, decidedData] = await Promise.all([
      api(`/api/rulebook-reviews?status=pending&limit=${REVIEW_PAGE_SIZE}&offset=${reviewPendingOffset}`),
      api(`/api/rulebook-reviews?status=decided&limit=${REVIEW_PAGE_SIZE}&offset=${reviewDecidedOffset}`),
    ]);

    if (pendingData.total === 0) {
      reviewPendingOffset = 0;
    } else if (reviewPendingOffset >= pendingData.total) {
      reviewPendingOffset = Math.floor((pendingData.total - 1) / REVIEW_PAGE_SIZE) * REVIEW_PAGE_SIZE;
      return renderReviews();
    }
    if (decidedData.total === 0) {
      reviewDecidedOffset = 0;
    } else if (reviewDecidedOffset >= decidedData.total) {
      reviewDecidedOffset = Math.floor((decidedData.total - 1) / REVIEW_PAGE_SIZE) * REVIEW_PAGE_SIZE;
      return renderReviews();
    }

    const corruptCount = (pendingData.corrupt_count || 0) + (decidedData.corrupt_count || 0);
    const corruptWarning = corruptCount
      ? `<div class="review-warning">${corruptCount} record corrotti sono stati esclusi da questa pagina.</div>`
      : "";

    app.innerHTML = `
      <section class="admin-page review-page">
        <div class="review-page-head admin-page-head">
          <div>
            <h1>Fonti da verificare</h1>
            <p class="muted catalog-page-summary">Esamina i candidati ai regolamenti e conferma quali fonti sono affidabili</p>
          </div>
          <span class="review-counter">${pendingData.total} da verificare</span>
        </div>

        ${corruptWarning}

        <h2 class="section-title">In attesa di decisione</h2>
        <div class="review-list">
          ${pendingData.items.length ? pendingData.items.map(reviewCard).join("") : '<div class="empty">Nessun candidato in attesa.</div>'}
        </div>
        ${reviewPager(pendingData, "pending")}

        <h2 class="section-title review-decided-title">Decisioni recenti</h2>
        <div class="review-list">
          ${decidedData.items.length ? decidedData.items.map(reviewCard).join("") : '<div class="empty">Nessuna decisione registrata.</div>'}
        </div>
        ${reviewPager(decidedData, "decided")}
      </section>
    `;

    document.querySelectorAll(".review-decision").forEach((button) => {
      button.addEventListener("click", () => {
        void decideReviewItem(button.dataset.reviewId, button.dataset.decision);
      });
    });
    document.querySelectorAll(".review-page-button").forEach((button) => {
      button.addEventListener("click", () => {
        const offset = Number(button.dataset.reviewOffset || 0);
        if (button.dataset.reviewSection === "pending") {
          reviewPendingOffset = offset;
        } else {
          reviewDecidedOffset = offset;
        }
        void renderReviews();
      });
    });
    document.title = "Fonti da verificare · BoardGameCompanion";
  } catch (error) {
    app.innerHTML = `<div class="empty">Impossibile caricare la coda: ${escapeHtml(error.message)}</div>`;
    showToast(error.message, true);
  }
}



const UPDATE_PAGE_SIZE = 50;
const UPDATE_REFRESH_MS = 30_000;
let updateOffset = 0;
let updateRefreshTimer = null;


function clearUpdateRefresh() {
  if (updateRefreshTimer !== null) {
    window.clearTimeout(updateRefreshTimer);
    updateRefreshTimer = null;
  }
}


function scheduleUpdateRefresh() {
  clearUpdateRefresh();
  if (!/^\/updates\/?$/.test(window.location.pathname)) return;
  updateRefreshTimer = window.setTimeout(() => {
    updateRefreshTimer = null;
    void renderUpdates();
  }, UPDATE_REFRESH_MS);
}


function formatUpdateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("it-IT", {
    dateStyle: "short",
    timeStyle: "short",
  });
}


function formatUpdateInterval(seconds) {
  const value = Number(seconds || 0);
  if (value < 3600) {
    const minutes = Math.max(1, Math.round(value / 60));
    return minutes === 1 ? "1 minuto" : `${minutes} minuti`;
  }
  if (value % 86400 === 0) {
    const days = value / 86400;
    return days === 1 ? "1 giorno" : `${days} giorni`;
  }
  const hours = Math.max(1, Math.round(value / 3600));
  return hours === 1 ? "1 ora" : `${hours} ore`;
}


function updateIntervalOptions(current) {
  const presets = [
    [86400, "Ogni giorno"],
    [604800, "Ogni 7 giorni"],
    [2592000, "Ogni 30 giorni"],
    [7776000, "Ogni 90 giorni"],
  ];
  const values = new Set(presets.map(([value]) => value));
  const options = presets.map(([value, label]) => (
    `<option value="${value}" ${Number(current) === value ? "selected" : ""}>${label}</option>`
  ));
  if (!values.has(Number(current))) {
    options.unshift(
      `<option value="${Number(current)}" selected>${escapeHtml(formatUpdateInterval(current))}</option>`
    );
  }
  return options.join("");
}


function updateStatus(target) {
  if (target.leased) return ["In esecuzione", "running"];
  if (!target.enabled) return ["In pausa", "paused"];
  if (target.last_outcome === "failed") return ["Errore", "failed"];
  if (target.last_outcome === "created") return ["Nuova versione", "created"];
  if (target.last_outcome === "unchanged") return ["Invariato", "unchanged"];
  return ["In attesa", "pending"];
}


function updateCard(target) {
  const [statusLabel, statusClass] = updateStatus(target);
  const source = String(target.source_kind || "unknown").replaceAll("_", " ");
  const failure = target.last_outcome === "failed" && target.last_failure_message
    ? `<div class="update-failure">${escapeHtml(target.last_failure_message)}</div>`
    : "";
  const hash = target.last_sha256
    ? `<span>SHA ${escapeHtml(target.last_sha256.slice(0, 12))}…</span>`
    : "";

  return `
    <article class="update-card" data-update-review-id="${escapeHtml(target.review_item_id)}">
      <div class="update-card-head">
        <div>
          <p class="eyebrow">${escapeHtml(source)} · ${escapeHtml(target.provider || "provider")}</p>
          <h3><a href="/games/${target.bgg_id}" data-nav>${escapeHtml(target.game_title)}</a></h3>
        </div>
        <span class="update-status update-status-${statusClass}">${statusLabel}</span>
      </div>
      <a class="review-url" href="${escapeHtml(target.url || "#")}" target="_blank" rel="noopener noreferrer">
        ${escapeHtml(target.url || "URL non disponibile")}
      </a>
      <div class="update-facts">
        <span>Prossimo check: <strong>${formatUpdateTime(target.next_check_at)}</strong></span>
        <span>Ultimo check: <strong>${formatUpdateTime(target.last_checked_at)}</strong></span>
        <span>Fallimenti consecutivi: <strong>${Number(target.consecutive_failures || 0)}</strong></span>
        ${hash}
      </div>
      ${failure}
      <div class="update-actions">
        <label class="update-interval-field">
          <span>Intervallo</span>
          <select class="update-interval" data-review-id="${escapeHtml(target.review_item_id)}" ${target.leased ? "disabled" : ""}>
            ${updateIntervalOptions(target.interval_seconds)}
          </select>
        </label>
        <button
          class="button button-ghost update-toggle"
          data-review-id="${escapeHtml(target.review_item_id)}"
          data-enabled="${target.enabled ? "true" : "false"}"
          type="button"
          ${target.leased ? "disabled" : ""}
        >${target.enabled ? "Pausa" : "Riprendi"}</button>
        <button
          class="button button-primary update-run"
          data-review-id="${escapeHtml(target.review_item_id)}"
          type="button"
          ${target.leased ? "disabled" : ""}
        >Controlla ora</button>
      </div>
    </article>
  `;
}


function updatePager(data) {
  if (data.total <= data.limit) return "";
  const start = data.total ? data.offset + 1 : 0;
  const end = Math.min(data.offset + data.limit, data.total);
  return `
    <div class="review-pagination">
      <span>${start}–${end} di ${data.total}</span>
      <div>
        <button class="button button-ghost update-page-button"
          data-update-offset="${Math.max(0, data.offset - data.limit)}"
          type="button" ${data.offset === 0 ? "disabled" : ""}>Precedente</button>
        <button class="button button-ghost update-page-button"
          data-update-offset="${data.offset + data.limit}"
          type="button" ${data.offset + data.limit >= data.total ? "disabled" : ""}>Successiva</button>
      </div>
    </div>
  `;
}


async function runUpdateNow(reviewId) {
  const button = document.querySelector(`.update-run[data-review-id="${reviewId}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "Controllo…";
  }
  try {
    const result = await api(`/api/rulebook-updates/${reviewId}/run`, {
      method: "POST",
    });
    const message = result.outcome === "failed"
      ? `Controllo completato con errore: ${result.failure_code || "errore"}.`
      : result.outcome === "created"
        ? "Nuova versione archiviata."
        : "Documento invariato.";
    showToast(message, result.outcome === "failed");
    await renderUpdates();
  } catch (error) {
    showToast(error.message, true);
    await renderUpdates();
  }
}


async function toggleUpdate(reviewId, enabled) {
  try {
    await api(`/api/rulebook-updates/${reviewId}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({enabled: !enabled}),
    });
    showToast(enabled ? "Aggiornamenti regolamenti in pausa." : "Aggiornamenti regolamenti riattivati.");
    await renderUpdates();
  } catch (error) {
    showToast(error.message, true);
  }
}


async function changeUpdateInterval(reviewId, intervalSeconds) {
  try {
    await api(`/api/rulebook-updates/${reviewId}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({interval_seconds: Number(intervalSeconds)}),
    });
    showToast("Intervallo aggiornato.");
    await renderUpdates();
  } catch (error) {
    showToast(error.message, true);
    await renderUpdates();
  }
}


async function renderUpdates({reset = false} = {}) {
  clearUpdateRefresh();
  if (reset) updateOffset = 0;
  app.innerHTML = '<div class="empty">Caricamento aggiornamenti rulebook…</div>';
  try {
    const data = await api(
      `/api/rulebook-updates?limit=${UPDATE_PAGE_SIZE}&offset=${updateOffset}`
    );
    if (data.total === 0) {
      updateOffset = 0;
    } else if (updateOffset >= data.total) {
      updateOffset = Math.floor((data.total - 1) / UPDATE_PAGE_SIZE) * UPDATE_PAGE_SIZE;
      return renderUpdates();
    }

    const worker = data.worker || {};
    const workerLabel = worker.enabled
      ? `Controllo automatico attivo · coda ogni ${escapeHtml(formatUpdateInterval(worker.poll_seconds || 60))}`
      : "Controllo automatico disattivato";
    const corruptWarning = data.corrupt_count
      ? `<div class="review-warning">${data.corrupt_count} target collegati a review corrotte sono stati esclusi da questa pagina.</div>`
      : "";

    app.innerHTML = `
      <section class="admin-page update-page">
        <div class="review-page-head admin-page-head">
          <div>
            <h1>Aggiornamenti regolamenti</h1>
            <p class="muted catalog-page-summary">Monitora le fonti approvate e controlla quando sono disponibili nuove versioni</p>
          </div>
          <span class="review-counter">${data.total} monitorati</span>
        </div>
        <div class="update-worker-state ${worker.enabled ? "" : "disabled"}">
          ${workerLabel}
        </div>
        ${corruptWarning}
        <div class="update-list">
          ${data.items.length
            ? data.items.map(updateCard).join("")
            : '<div class="empty">Nessun candidato approvato da monitorare.</div>'}
        </div>
        ${updatePager(data)}
      </section>
    `;

    document.querySelectorAll(".update-run").forEach((button) => {
      button.addEventListener("click", () => {
        void runUpdateNow(button.dataset.reviewId);
      });
    });
    document.querySelectorAll(".update-toggle").forEach((button) => {
      button.addEventListener("click", () => {
        void toggleUpdate(
          button.dataset.reviewId,
          button.dataset.enabled === "true",
        );
      });
    });
    document.querySelectorAll(".update-interval").forEach((select) => {
      select.addEventListener("change", () => {
        void changeUpdateInterval(select.dataset.reviewId, select.value);
      });
    });
    document.querySelectorAll(".update-page-button").forEach((button) => {
      button.addEventListener("click", () => {
        updateOffset = Number(button.dataset.updateOffset || 0);
        void renderUpdates();
      });
    });
    document.title = "Aggiornamenti regolamenti · BoardGameCompanion";
    scheduleUpdateRefresh();
  } catch (error) {
    app.innerHTML = `<div class="empty">Impossibile caricare gli aggiornamenti: ${escapeHtml(error.message)}</div>`;
    showToast(error.message, true);
    scheduleUpdateRefresh();
  }
}



// Assistente AI: conversation kept for the browser session, never on the server.
const ASSISTANT_STORAGE_KEY = "bgc.assistant";
const assistantExamples = [
  ["Un gioco semplice per 2 persone, massimo 45 minuti.", "library"],
  ["Suggeriscimi un cooperativo per 3-4 persone, non troppo impegnativo.", "library"],
  ["Crea una lista di giochi adatti a una serata con amici che non giocano spesso.", "library"],
  ["Che differenze ci sono tra Brass: Birmingham e Ark Nova? Quale mi consigli?", "all"],
];
const assistantState = (() => {
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(ASSISTANT_STORAGE_KEY) || "{}");
    return {
      scope: stored.scope === "all" ? "all" : "library",
      turns: Array.isArray(stored.turns) ? stored.turns.slice(-20) : [],
      busy: false,
    };
  } catch (_) {
    return {scope: "library", turns: [], busy: false};
  }
})();

function saveAssistantState() {
  try {
    window.sessionStorage.setItem(
      ASSISTANT_STORAGE_KEY,
      JSON.stringify({scope: assistantState.scope, turns: assistantState.turns}),
    );
  } catch (_) {
    // Storage full or disabled: the conversation just won't survive a reload.
  }
}

function assistantHistoryPayload() {
  return assistantState.turns
    .filter((turn) => !turn.error)
    .slice(-8)
    .map((turn) => {
      if (turn.role === "user") return {role: "user", text: turn.text};
      const titles = (turn.payload?.recommendations || []).map((item) => item.title);
      return {
        role: "assistant",
        text: [turn.payload?.answer || "", titles.length ? `Titoli proposti: ${titles.join(", ")}` : ""]
          .filter(Boolean).join("\n").slice(0, 3500),
      };
    });
}

function assistantRecommendationCard(item) {
  const game = {
    bgg_id: Number(item.bgg_id),
    title: item.title,
    players: item.players || {},
    play_time: item.minutes || {},
    collection: {own: Boolean(item.owned)},
  };
  const open = gameOpenAttributes(game, item.owned ? null : item);
  const facts = [
    playerText(game) !== "—" ? `${playerText(game)} gioc.` : "",
    timeText(game) !== "—" ? timeText(game) : "",
    item.weight ? `peso ${formatNumber(item.weight, 1)}` : "",
    item.rating ? `★ ${formatNumber(item.rating, 1)}` : "",
  ].filter(Boolean).join(" · ");
  const reference = {
    bgg_id: item.bgg_id, name: item.title, year_published: "", thumbnail_url: "", owned: Boolean(item.owned),
  };
  return `
    <article class="assistant-game">
      <${open.tag} class="assistant-game-open" ${open.attrs} aria-label="Apri ${escapeHtml(item.title)}">
        <span class="assistant-game-cover"><img src="${coverSrc(item.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer"><span>${escapeHtml(initials(item.title))}</span></span>
        <span class="assistant-game-copy">
          <strong>${escapeHtml(item.title)}</strong>
          ${facts ? `<small>${escapeHtml(facts)}</small>` : ""}
          <span class="assistant-game-reason">${escapeHtml(item.reason)}</span>
        </span>
      </${open.tag}>
      <span class="assistant-game-actions">${referenceActionButtons(reference)}</span>
    </article>
  `;
}

function assistantTurnMarkup(turn, index) {
  if (turn.role === "user") {
    return `<div class="assistant-message is-user"><p>${escapeHtml(turn.text)}</p></div>`;
  }
  if (turn.error) {
    return `<div class="assistant-message is-assistant"><div class="integration-error">${escapeHtml(turn.error)}</div></div>`;
  }
  const payload = turn.payload || {};
  const items = payload.recommendations || [];
  const owned = items.filter((item) => item.owned);
  const missing = items.filter((item) => !item.owned);
  const listBar = payload.list_name ? `
    <div class="assistant-list-bar">
      <span>${icon("list")}<span>Lista proposta: <strong>${escapeHtml(payload.list_name)}</strong> · ${items.length} ${items.length === 1 ? "gioco" : "giochi"}</span></span>
      <span class="assistant-list-actions">
        ${owned.length ? `<button class="button button-primary" type="button" data-assistant-create-list="${index}" ${turn.listCreated ? "disabled" : ""}>${turn.listCreated ? "Lista creata" : `Crea lista (${owned.length})`}</button>` : ""}
        ${missing.length ? `<button class="button button-ghost" type="button" data-assistant-wishlist="${index}" ${turn.wishlistAdded ? "disabled" : ""}>${turn.wishlistAdded ? "In wishlist" : `Non posseduti in wishlist (${missing.length})`}</button>` : ""}
        ${turn.listCreated ? `<a class="button button-ghost" href="/lists" data-nav>Apri Liste</a>` : ""}
      </span>
      ${owned.length && missing.length ? '<small class="muted">Le liste contengono solo giochi posseduti: gli altri possono andare in wishlist.</small>' : ""}
    </div>
  ` : "";
  return `
    <div class="assistant-message is-assistant">
      <p class="assistant-answer">${escapeHtml(payload.answer || "")}</p>
      ${items.length ? `<div class="assistant-games">${items.map(assistantRecommendationCard).join("")}</div>` : ""}
      ${listBar}
      ${payload.provider ? `<small class="assistant-provider">${escapeHtml(payload.scope === "all" ? "Ludoteca + catalogo BGG" : "Solo ludoteca")} · ${escapeHtml(payload.provider)}${payload.model ? ` · ${escapeHtml(payload.model)}` : ""}</small>` : ""}
    </div>
  `;
}

function renderAssistantThread() {
  const thread = document.querySelector("#assistantThread");
  if (!thread) return;
  if (!assistantState.turns.length && !assistantState.busy) {
    thread.innerHTML = `
      <div class="assistant-empty">
        <p>Chiedi un consiglio per la prossima partita, fai domande su un gioco, posseduto o no, o fatti preparare una lista.</p>
        <div class="assistant-examples" aria-label="Esempi">
          ${assistantExamples.map(([text, scope]) => `<button type="button" data-assistant-example="${escapeHtml(text)}" data-assistant-example-scope="${scope}">${escapeHtml(text)}</button>`).join("")}
        </div>
      </div>
    `;
  } else {
    thread.innerHTML = assistantState.turns.map(assistantTurnMarkup).join("")
      + (assistantState.busy ? '<div class="assistant-message is-assistant"><p class="assistant-thinking">Sto pensando…</p></div>' : "");
  }
  bindWishlistActions(thread);
  bindReferenceActions(thread);
  thread.querySelectorAll("[data-assistant-example]").forEach((button) => {
    button.addEventListener("click", () => {
      setAssistantScope(button.dataset.assistantExampleScope || "library");
      const input = document.querySelector("#assistantQuestion");
      if (!input) return;
      input.value = button.dataset.assistantExample || "";
      input.focus();
    });
  });
  thread.querySelectorAll("[data-assistant-create-list]").forEach((button) => {
    button.addEventListener("click", () => void createAssistantList(Number(button.dataset.assistantCreateList), button));
  });
  thread.querySelectorAll("[data-assistant-wishlist]").forEach((button) => {
    button.addEventListener("click", () => void addAssistantWishlist(Number(button.dataset.assistantWishlist), button));
  });
  const last = thread.lastElementChild;
  if (assistantState.turns.length) last?.scrollIntoView({block: "nearest", behavior: "smooth"});
}

function setAssistantScope(scope) {
  assistantState.scope = scope === "all" ? "all" : "library";
  saveAssistantState();
  document.querySelectorAll("[data-assistant-scope]").forEach((button) => {
    const active = button.dataset.assistantScope === assistantState.scope;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

async function createAssistantList(index, button) {
  const turn = assistantState.turns[index];
  const owned = (turn?.payload?.recommendations || []).filter((item) => item.owned);
  if (!turn || !owned.length) return;
  button.disabled = true;
  try {
    const created = await api("/api/lists", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: turn.payload.list_name, kind: "manual"}),
    });
    for (const item of owned) {
      await api(`/api/lists/${encodeURIComponent(created.id)}/items/${encodeURIComponent(item.bgg_id)}`, {method: "PUT"});
    }
    turn.listCreated = true;
    saveAssistantState();
    renderAssistantThread();
    showToast(`Lista «${turn.payload.list_name}» creata.`);
  } catch (error) {
    button.disabled = false;
    showToast(error.message, true);
  }
}

async function addAssistantWishlist(index, button) {
  const turn = assistantState.turns[index];
  const missing = (turn?.payload?.recommendations || []).filter((item) => !item.owned);
  if (!turn || !missing.length) return;
  button.disabled = true;
  try {
    await refreshWishlistIndex();
    for (const item of missing) {
      if (wishlistEntry("bgg", String(item.bgg_id))) continue;
      await api("/api/wishlist", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          source_kind: "bgg",
          source_key: String(item.bgg_id),
          title: item.title,
          bgg_id: Number(item.bgg_id),
          target_url: `https://boardgamegeek.com/boardgame/${Number(item.bgg_id)}`,
          metadata: {},
        }),
      });
    }
    await refreshWishlistIndex();
    turn.wishlistAdded = true;
    saveAssistantState();
    renderAssistantThread();
    showToast("Giochi aggiunti alla Wishlist.");
  } catch (error) {
    button.disabled = false;
    showToast(error.message, true);
  }
}

async function submitAssistantQuestion() {
  const input = document.querySelector("#assistantQuestion");
  const ask = document.querySelector("#assistantAsk");
  const query = String(input?.value || "").trim();
  if (!query || assistantState.busy) return;
  const history = assistantHistoryPayload();
  assistantState.turns.push({role: "user", text: query});
  assistantState.busy = true;
  input.value = "";
  if (ask) ask.disabled = true;
  renderAssistantThread();
  try {
    const payload = await api("/api/catalog/assistant", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query, scope: assistantState.scope, history}),
    });
    assistantState.turns.push({role: "assistant", payload});
  } catch (error) {
    assistantState.turns.push({role: "assistant", error: error.message});
  } finally {
    assistantState.busy = false;
    assistantState.turns = assistantState.turns.slice(-20);
    saveAssistantState();
    if (ask) ask.disabled = false;
    renderAssistantThread();
    if (input?.isConnected) input.focus();
  }
}

async function renderAssistant() {
  document.title = "Assistente AI · BoardGameCompanion";
  app.innerHTML = `
    <section class="page-header catalog-page-header">
      <div class="page-header-copy">
        <h1>Assistente AI</h1>
        <p class="muted catalog-page-summary">Consigli, domande e liste sui giochi da tavolo</p>
      </div>
      <div class="catalog-stats catalog-sort-pills" role="group" aria-label="Giochi considerati">
        <button type="button" class="stat" data-assistant-scope="library"><span>Solo ludoteca</span></button>
        <button type="button" class="stat" data-assistant-scope="all"><span>Ludoteca + catalogo BGG</span></button>
      </div>
    </section>
    <section class="catalog-workspace assistant-workspace" aria-label="Conversazione con l'assistente">
      <div class="assistant-thread" id="assistantThread" aria-live="polite"></div>
      <form class="assistant-composer" id="assistantForm">
        <label class="field assistant-question-field">
          <textarea id="assistantQuestion" rows="2" maxlength="2000" required aria-label="La tua domanda"
                    placeholder="Es. Un cooperativo per 2–3 persone, con deckbuilding e non troppo impegnativo."></textarea>
        </label>
        <div class="assistant-composer-actions">
          <button class="button button-ghost" id="assistantReset" type="button">Nuova conversazione</button>
          <button class="button button-primary" id="assistantAsk" type="submit">Chiedi</button>
        </div>
      </form>
    </section>
  `;
  setAssistantScope(assistantState.scope);
  document.querySelectorAll("[data-assistant-scope]").forEach((button) => {
    button.addEventListener("click", () => setAssistantScope(button.dataset.assistantScope));
  });
  const input = document.querySelector("#assistantQuestion");
  document.querySelector("#assistantForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitAssistantQuestion();
  });
  input?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void submitAssistantQuestion();
    }
  });
  document.querySelector("#assistantReset")?.addEventListener("click", () => {
    if (assistantState.busy) return;
    assistantState.turns = [];
    saveAssistantState();
    renderAssistantThread();
    input?.focus();
  });
  if (assistantState.turns.some((turn) => turn.payload?.recommendations?.length)) {
    await refreshWishlistIndex().catch(() => null);
  }
  renderAssistantThread();
}

function browseGameRow(game, index) {
  const rank = game.bgg?.rank && Number(game.bgg.rank) > 0 ? `#${formatNumber(game.bgg.rank, 0)}` : "—";
  return `
    <a class="browse-game-row" href="/games/${encodeURIComponent(game.bgg_id)}" data-nav>
      <span class="browse-rank">${index !== null ? index : rank}</span>
      <span class="browse-cover">
        ${game.bgg_metadata?.cover_url
          ? `<img src="${coverSrc(game.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<span>${escapeHtml(initials(game.title))}</span>`}
      </span>
      <span class="browse-game-title">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${escapeHtml(playerText(game))} gioc. · ${escapeHtml(timeText(game))}</small>
      </span>
      <span class="browse-score">${game.bgg?.average ? `★ ${formatNumber(game.bgg.average, 1)}` : "—"}</span>
    </a>
  `;
}

const rankingModes = [
  ["overall", "Migliori in assoluto"],
  ["outside_top", "Fuori dalla Top 500"],
  ["quality_time", "Qualità / tempo"],
  ["gateway", "Gateway"],
  ["expert", "Per esperti"],
  ["safe_choice", "Scelta sicura"],
  ["personal_favorites", "Preferiti personali"],
];
const RANKING_PAGE = 20;

function rankingParams() {
  const params = new URLSearchParams({
    mode: rankingState.mode,
    source: rankingState.source,
    limit: rankingState.expanded ? "100" : String(RANKING_PAGE),
  });
  [...rankingState.categoryGroups].forEach((value) => params.append("category_group", value));
  [...rankingState.mechanicGroups].forEach((value) => params.append("mechanic_group", value));
  for (const [key, value] of [
    ["category", rankingState.category],
    ["mechanic", rankingState.mechanic],
    ["ideal_players", rankingState.idealPlayers],
    ["max_minutes", rankingState.maxMinutes],
    ["weight", rankingState.weight],
    ["max_language", rankingState.maxLanguage],
  ]) {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  }
  return params;
}

function rankingModeTiles() {
  const libraryIncluded = rankingState.source !== "catalog";
  return rankingModes.map(([mode, label]) => {
    // Personal votes exist only for owned games.
    const disabled = mode === "personal_favorites" && !libraryIncluded;
    const active = rankingState.mode === mode;
    return `
      <button class="ranking-mode-tile ${active ? "is-active" : ""}" type="button" role="radio"
              aria-checked="${active}" data-ranking-mode="${mode}" ${disabled ? "disabled" : ""}>
        ${exploreGroupArt(`mode-${mode}`)}
        <strong>${escapeHtml(label)}</strong>
      </button>
    `;
  }).join("");
}

function rankingGameSummary(game) {
  const summary = String(game.gameplay_summary || "").trim();
  if (summary) return summary;
  return game.bgg_metadata?.description
    ? "Riassunto gameplay in preparazione…"
    : "";
}

async function ensureRankingGameplaySummaries(items) {
  if (navigator.webdriver) return;
  const missing = (items || []).filter(
    (item) =>
      !String(item.game?.gameplay_summary || "").trim()
      && (item.game?.source === "catalog"
        ? item.game?.has_description
        : String(item.game?.bgg_metadata?.description || "").trim())
  ).slice(0, 8);
  if (!missing.length) return;

  try {
    const payload = await api("/api/catalog/gameplay-summaries/ensure", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        bgg_ids: missing.map((item) => Number(item.game.bgg_id)),
      }),
    });
    for (const item of payload.items || []) {
      const summary = String(item.summary || "").trim();
      if (!summary) continue;
      document.querySelectorAll(
        `[data-ranking-summary-bgg="${CSS.escape(String(item.bgg_id))}"]`
      ).forEach((target) => {
        if (target.isConnected) target.textContent = summary;
      });
    }
  } catch (_) {
    // Ranking remains usable; cached summaries will be retried on a later visit.
  }
}

// Library games and catalog titles share one row shape for the ranking list.
function rankingGameView(game) {
  if (game.source === "catalog") {
    const asGame = referenceAsGame(game);
    return {
      game: asGame,
      href: `/bgg/${encodeURIComponent(game.bgg_id)}`,
      hasCover: Boolean(game.image_url || game.thumbnail_url),
      summary: rankingGameSummary({
        gameplay_summary: game.gameplay_summary,
        bgg_metadata: {description: game.has_description ? "available" : ""},
      }),
      catalog: true,
    };
  }
  return {
    game,
    href: `/games/${encodeURIComponent(game.bgg_id)}`,
    hasCover: Boolean(game.bgg_metadata?.cover_url),
    summary: rankingGameSummary(game),
    catalog: false,
  };
}

function rankingCover(view) {
  return view.hasCover
    ? `<img src="${coverSrc(view.game.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : `<span>${escapeHtml(initials(view.game.title))}</span>`;
}

function rankingMeta(game) {
  const rating = game.bgg?.average ? formatNumber(game.bgg.average, 1) : "—";
  return `${escapeHtml(playerText(game))} gioc. · ${escapeHtml(timeText(game))} · <span class="ranking-rating">★ ${escapeHtml(rating)}</span>`;
}

function rankingPodiumCard(item, index) {
  const view = rankingGameView(item.game);
  return `
    <a class="ranking-podium-card podium-${index}" href="${view.href}" data-nav>
      <span class="ranking-podium-cover">${rankingCover(view)}</span>
      <span class="ranking-position">${index}</span>
      <span class="ranking-podium-body">
        <strong>${escapeHtml(view.game.title)}</strong>
        <small>${rankingMeta(view.game)}${view.catalog ? ' · <em>Catalogo</em>' : ""}</small>
        ${view.summary ? `<span class="ranking-podium-summary" data-ranking-summary-bgg="${escapeHtml(view.game.bgg_id)}">${escapeHtml(view.summary)}</span>` : ""}
      </span>
    </a>
  `;
}

function rankingGameRow(item, index) {
  const view = rankingGameView(item.game);
  const factors = (item.factors || []).map(
    (factor) => `<span>${escapeHtml(factor)}</span>`
  ).join("");
  return `
    <a class="ranking-result-row" href="${view.href}" data-nav>
      <span class="ranking-result-cover">
        ${rankingCover(view)}
        <span class="ranking-position">${index}</span>
      </span>
      <span class="ranking-result-body">
        <span class="ranking-result-title">
          <strong>${escapeHtml(view.game.title)}</strong>
          ${view.catalog ? '<span class="ranking-source-tag">Catalogo</span>' : ""}
        </span>
        <small>${rankingMeta(view.game)}</small>
        ${view.summary ? `<span class="ranking-result-summary" data-ranking-summary-bgg="${escapeHtml(view.game.bgg_id)}">${escapeHtml(view.summary)}</span>` : ""}
        <span class="ranking-result-factors">${factors}</span>
      </span>
      <span class="ranking-score" title="${escapeHtml(item.reason || "Criterio della classifica")}">${formatNumber(item.score, 1)}</span>
    </a>
  `;
}

const rankingOptionGroups = [
  {apiKey: "ideal_players", stateKey: "idealPlayers", title: "Ideale in"},
  {apiKey: "max_minutes", stateKey: "maxMinutes", title: "Durata (min)"},
  {apiKey: "weight", stateKey: "weight", title: "Complessità"},
  {apiKey: "max_language", stateKey: "maxLanguage", title: "Dipendenza dalla lingua"},
];

function rankingOptionGroup(group, options) {
  const current = String(rankingState[group.stateKey] || "");
  return `
    <section class="explore-option-group">
      <h3>${escapeHtml(group.title)}</h3>
      <div class="explore-option-buttons">
        ${(options || []).map((option) => {
          const selected = Boolean(option.selected) || current === String(option.value);
          return `
            <button class="explore-option-button ${selected ? "is-selected" : ""}" type="button"
                    data-ranking-filter="${group.stateKey}" data-ranking-value="${escapeHtml(String(option.value))}"
                    aria-pressed="${selected}" title="${formatNumber(option.count, 0)} giochi">
              <span>${escapeHtml(String(option.label))}</span><small>${formatNumber(option.count, 0)}</small>
            </button>
          `;
        }).join("") || '<span class="explore-option-none">Nessun dato compatibile</span>'}
      </div>
    </section>
  `;
}

// Macro groups in the panel; a selected group reveals its entries to narrow to one.
function rankingFacetSection(kind, payload) {
  const groups = (kind === "category" ? payload.category_groups : payload.mechanic_groups) || [];
  const facets = (kind === "category" ? payload.categories : payload.mechanics) || [];
  const selectedGroups = kind === "category" ? rankingState.categoryGroups : rankingState.mechanicGroups;
  const selectedFacet = kind === "category" ? rankingState.category : rankingState.mechanic;
  const members = facets.filter((item) => selectedGroups.has(item.group) || item.name === selectedFacet);
  return `
    <section class="explore-option-group">
      <h3>${kind === "category" ? "Genere" : "Meccanica"}</h3>
      <div class="ranking-group-chips">
        ${groups.filter((group) => group.count > 0 || selectedGroups.has(group.key)).map((group) => `
          <button class="ranking-group-chip ${selectedGroups.has(group.key) ? "is-selected" : ""}" type="button"
                  data-ranking-group-kind="${kind}" data-ranking-group-key="${group.key}"
                  aria-pressed="${selectedGroups.has(group.key)}" title="${formatNumber(group.count, 0)} giochi">
            ${exploreGroupArt(group.key)}<span>${escapeHtml(group.label)}</span><small>${formatNumber(group.count, 0)}</small>
          </button>
        `).join("")}
      </div>
      ${members.length ? `
        <div class="ranking-member-chips">
          ${members.slice(0, 24).map((item) => `
            <button class="explore-facet-chip ${item.name === selectedFacet ? "is-selected" : ""}" type="button"
                    data-ranking-facet-kind="${kind}" data-ranking-facet="${escapeHtml(item.name)}"
                    aria-pressed="${item.name === selectedFacet}">
              <span>${escapeHtml(item.name)}</span><small>${formatNumber(item.count, 0)}</small>
            </button>
          `).join("")}
        </div>
      ` : ""}
    </section>
  `;
}

function rankingActiveFilterCount() {
  return [
    rankingState.category, rankingState.mechanic, rankingState.idealPlayers,
    rankingState.maxMinutes, rankingState.weight, rankingState.maxLanguage,
  ].filter(Boolean).length + rankingState.categoryGroups.size + rankingState.mechanicGroups.size;
}

function renderRankingFilters(payload) {
  const container = document.querySelector("#rankingFilterOptions");
  if (!container) return;
  const options = payload.options || {};
  container.innerHTML = [
    ...rankingOptionGroups.map((group) => rankingOptionGroup(group, options[group.apiKey])),
    rankingFacetSection("category", payload),
    rankingFacetSection("mechanic", payload),
  ].join("");
  const active = rankingActiveFilterCount();
  const toggleCount = document.querySelector("#rankingFilterToggleCount");
  if (toggleCount) toggleCount.textContent = active ? String(active) : "";
  const reset = document.querySelector("#rankingResetFilters");
  if (reset) reset.disabled = !active;

  const reload = () => {
    rankingState.expanded = false;
    refreshRankings();
  };
  container.querySelectorAll("[data-ranking-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.rankingFilter;
      const value = button.dataset.rankingValue || "";
      rankingState[key] = rankingState[key] === value ? "" : value;
      reload();
    });
  });
  container.querySelectorAll("[data-ranking-group-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const kind = button.dataset.rankingGroupKind;
      const groups = kind === "category" ? rankingState.categoryGroups : rankingState.mechanicGroups;
      const key = button.dataset.rankingGroupKey;
      if (groups.has(key)) {
        groups.delete(key);
        // A single entry chosen inside the group goes with it.
        const facet = ((kind === "category" ? payload.categories : payload.mechanics) || [])
          .find((item) => item.name === rankingState[kind]);
        if (facet?.group === key) rankingState[kind] = "";
      } else {
        groups.add(key);
      }
      reload();
    });
  });
  container.querySelectorAll("[data-ranking-facet]").forEach((button) => {
    button.addEventListener("click", () => {
      const kind = button.dataset.rankingFacetKind;
      const name = button.dataset.rankingFacet;
      rankingState[kind] = rankingState[kind] === name ? "" : name;
      reload();
    });
  });
}

function renderRankingPayload(payload) {
  const results = document.querySelector("#rankingResults");
  const count = document.querySelector("#rankingResultCount");
  const description = document.querySelector("#rankingCurrentDescription");
  const more = document.querySelector("#rankingMore");
  if (!results || !count || !description || !more) return;
  count.textContent = payload.total === 1
    ? "1 gioco classificato"
    : `${formatNumber(payload.total, 0)} giochi classificati`;
  description.textContent = payload.description || "";
  const items = payload.items || [];
  const podium = items.slice(0, 3);
  const rest = items.slice(3);
  results.innerHTML = items.length
    ? `
      <div class="ranking-podium">${podium.map((item, index) => rankingPodiumCard(item, index + 1)).join("")}</div>
      ${rest.length ? `<div class="ranking-list">${rest.map((item, index) => rankingGameRow(item, index + 4)).join("")}</div>` : ""}
    `
    : '<div class="empty">Nessun gioco soddisfa questa classifica e i filtri selezionati.</div>';
  const hidden = Math.max(0, Math.min(100, Number(payload.total || 0)) - items.length);
  more.hidden = hidden === 0 && !rankingState.expanded;
  more.textContent = rankingState.expanded ? "Mostra meno" : `Mostra altri ${formatNumber(hidden, 0)}`;
  renderRankingFilters(payload);
  runWhenIdle(() => {
    void ensureRankingGameplaySummaries(items);
  });
}

async function refreshRankings() {
  rankingRequestController?.abort();
  const controller = new AbortController();
  rankingRequestController = controller;
  const results = document.querySelector("#rankingResults");
  if (!results) return;

  const modes = document.querySelector("#rankingModes");
  if (modes) modes.innerHTML = rankingModeTiles();
  bindRankingModeTiles();
  results.classList.add("is-refreshing");
  results.setAttribute("aria-busy", "true");
  try {
    const [payload] = await Promise.all([
      api(`/api/catalog/rankings?${rankingParams()}`, {signal: controller.signal}),
      rankingState.source === "library" ? null : refreshWishlistIndex().catch(() => null),
    ]);
    if (controller.signal.aborted || !document.querySelector("#rankingResults")) return;
    renderRankingPayload(payload);
  } catch (error) {
    if (error.name === "AbortError") return;
    results.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  } finally {
    if (rankingRequestController === controller) {
      rankingRequestController = undefined;
      results.classList.remove("is-refreshing");
      results.removeAttribute("aria-busy");
    }
  }
}

function bindRankingModeTiles() {
  document.querySelectorAll("[data-ranking-mode]").forEach((button) => {
    button.onclick = () => {
      rankingState.mode = button.dataset.rankingMode;
      rankingState.expanded = false;
      refreshRankings();
    };
  });
}

function bindRankingControls() {
  bindSourceBoxes("ranking", rankingState, "bgc.rankingSource", () => {
    if (rankingState.source === "catalog" && rankingState.mode === "personal_favorites") {
      rankingState.mode = "overall";
    }
    rankingState.expanded = false;
    refreshRankings();
  });
  document.querySelector("#rankingMore")?.addEventListener("click", () => {
    rankingState.expanded = !rankingState.expanded;
    refreshRankings();
  });
  document.querySelector("#rankingFilterToggle")?.addEventListener("click", (event) => {
    const panel = document.querySelector("#rankingFilterPanel");
    const open = !panel?.classList.contains("is-open");
    panel?.classList.toggle("is-open", open);
    event.currentTarget.setAttribute("aria-expanded", String(open));
  });
  document.querySelector("#rankingResetFilters")?.addEventListener("click", () => {
    for (const key of ["category", "mechanic", "idealPlayers", "maxMinutes", "weight", "maxLanguage"]) {
      rankingState[key] = "";
    }
    rankingState.categoryGroups.clear();
    rankingState.mechanicGroups.clear();
    rankingState.expanded = false;
    refreshRankings();
  });
}

async function renderRankings() {
  app.innerHTML = `
    <section class="page-header catalog-page-header rankings-header">
      <div class="page-header-copy">
        <h1>Classifiche</h1>
        <p class="muted catalog-page-summary rankings-page-summary">
          <span>Confronta i giochi per voto, popolarità e altri criteri</span>
          <span aria-hidden="true">·</span>
          <span id="rankingResultCount" aria-live="polite">Caricamento…</span>
        </p>
      </div>
      <div class="explore-sources" role="group" aria-label="Dove cercare">${sourceBoxes("ranking", rankingState.source)}</div>
    </section>

    <div class="ranking-mode-grid" id="rankingModes" role="radiogroup" aria-label="Classifica">${rankingModeTiles()}</div>

    <section class="rankings-layout">
      <div class="rankings-main">
        <div class="ranking-current-head">
          <p class="muted" id="rankingCurrentDescription"></p>
          <button class="button button-ghost explore-filter-toggle" id="rankingFilterToggle" type="button"
                  aria-expanded="false" aria-controls="rankingFilterPanel">
            Filtri <span class="explore-filter-toggle-count" id="rankingFilterToggleCount"></span>
          </button>
        </div>
        <div class="ranking-results" id="rankingResults">${skeletons()}</div>
        <button class="button button-ghost ranking-more" id="rankingMore" type="button" hidden>Mostra altri</button>
      </div>

      <aside class="explore-filter-panel" id="rankingFilterPanel" aria-label="Filtri classifica">
        <div class="explore-filter-options" id="rankingFilterOptions"></div>
        <button class="button button-ghost explore-reset-optional" id="rankingResetFilters" type="button" disabled>Azzera filtri</button>
      </aside>
    </section>
  `;

  document.title = "Classifiche · BoardGameCompanion";
  bindRankingControls();
  await refreshRankings();
}

function completionAchievementMarkup(game) {
  const achievements = [{
    icon: game.progress?.completed ? "crown" : "diamond",
    label: game.progress?.completed ? "Completato" : "Giocato",
  }];
  const weight = Number(game.bgg?.average_weight || 0);
  const minutes = Number(
    game.play_time?.max || game.play_time?.playing || game.play_time?.min || 0
  );
  if (weight >= 3.5) achievements.push({icon: "gem", label: "Impresa"});
  if (minutes >= 120) achievements.push({icon: "hourglass", label: "Maratona"});
  return achievements.map((item) =>
    `<span class="trophy-achievement"><i aria-hidden="true">${icon(item.icon)}</i>${escapeHtml(item.label)}</span>`
  ).join("");
}

function trophyGameCard(game, {compact = false} = {}) {
  const cover = game.bgg_metadata?.cover_url
    ? `<img src="${coverSrc(game.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : `<span class="trophy-cover-fallback">${escapeHtml(initials(game.title))}</span>`;
  const milestoneAt = game.progress?.completed_at || game.progress?.played_at || null;
  const milestoneLabel = game.progress?.completed ? "Completato" : "Giocato";
  const milestoneDate = milestoneAt
    ? new Date(milestoneAt + "T12:00:00").toLocaleDateString("it-IT", {
        year: "numeric", month: "short", day: "numeric",
      })
    : null;
  return `
    <a class="trophy-card ${compact ? "is-compact" : ""}"
       href="/games/${encodeURIComponent(game.bgg_id)}" data-nav
       ${compact ? `title="${escapeHtml(game.title)}"` : ""}>
      <span class="trophy-crown" aria-hidden="true">${icon(game.progress?.completed ? "crown" : "diamond")}</span>
      <span class="trophy-cover">${cover}</span>
      <span class="trophy-card-body">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${milestoneDate
          ? `${milestoneLabel} · ${escapeHtml(milestoneDate)}`
          : milestoneLabel}</small>
        <span class="trophy-achievements">${completionAchievementMarkup(game)}</span>
      </span>
    </a>
  `;
}

async function refreshAchievementShowcase() {
  const showcase = document.querySelector("#achievementShowcase");
  const grid = document.querySelector("#achievementShowcaseGrid");
  if (!showcase || !grid) return;
  try {
    const payload = await api(
      "/api/games?owned=true&item_type=standalone&played=true&sort=played_desc&limit=4&offset=0"
    );
    if (!showcase.isConnected || !grid.isConnected) return;
    if (!payload.items.length) {
      showcase.hidden = true;
      return;
    }
    showcase.hidden = false;
    grid.innerHTML = payload.items.map((game) => trophyGameCard(game, {compact: true})).join("");
  } catch (_) {
    showcase.hidden = true;
  }
}

// ---------------------------------------------------------------------------
// Partite: diario delle partite, giochi giocati/completati e statistiche.
// ---------------------------------------------------------------------------
const PLAY_OUTCOMES = {won: "Vittoria", lost: "Sconfitta", draw: "Pareggio"};
const playsState = {view: "log", q: "", player: "", bggId: null};
let playDialog = null;
let playDialogContext = null;
let ownedGamesForPlays = null;

function todayIso() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function playDate(value, options = {day: "numeric", month: "short", year: "numeric"}) {
  if (!value) return "—";
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("it-IT", options);
}

function playDuration(minutes) {
  const value = Number(minutes) || 0;
  if (!value) return "";
  if (value < 60) return `${value} min`;
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

function playPlayersMarkup(play) {
  const players = Array.isArray(play.players) ? play.players : [];
  if (!players.length) {
    return play.player_count ? `<span class="play-chip">${formatNumber(play.player_count, 0)} giocatori</span>` : "";
  }
  return players.map((player) => `
    <span class="play-chip ${player.winner ? "is-winner" : ""}" ${player.winner ? 'title="Vincitore"' : ""}>
      ${player.winner ? `<i aria-hidden="true">${icon("crown")}</i>` : ""}${escapeHtml(player.name || "Giocatore")}${player.score ? `<small>${escapeHtml(player.score)}</small>` : ""}
    </span>
  `).join("") + (play.player_count > players.length
    ? `<span class="play-chip">+${formatNumber(play.player_count - players.length, 0)}</span>`
    : "");
}

function playRow(play, {showGame = true} = {}) {
  const facts = [
    play.outcome ? `<span class="play-outcome is-${play.outcome}">${PLAY_OUTCOMES[play.outcome]}</span>` : "",
    play.completed_game ? `<span class="play-outcome is-completed"><i aria-hidden="true">${icon("crown")}</i>Completato</span>` : "",
    play.duration_minutes ? `<span>${escapeHtml(playDuration(play.duration_minutes))}</span>` : "",
    play.location ? `<span>${escapeHtml(play.location)}</span>` : "",
  ].filter(Boolean).join("");
  return `
    <article class="play-row ${showGame ? "" : "is-game-scoped"}" data-play-id="${Number(play.id)}">
      ${showGame ? `
        <a class="play-row-cover" href="/games/${Number(play.bgg_id)}" data-nav aria-hidden="true" tabindex="-1">
          ${play.has_cover
            ? `<img src="${coverSrc(play.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
            : `<span>${escapeHtml(initials(play.title))}</span>`}
        </a>
      ` : ""}
      <time class="play-row-date" datetime="${escapeHtml(play.played_on)}">
        <strong>${escapeHtml(playDate(play.played_on, {day: "numeric"}))}</strong>
        <small>${escapeHtml(playDate(play.played_on, {month: "short"}))}</small>
      </time>
      <div class="play-row-body">
        <div class="play-row-head">
          ${showGame ? `<a class="play-row-title" href="/games/${Number(play.bgg_id)}" data-nav>${escapeHtml(play.title)}</a>` : ""}
          ${play.activity ? `<span class="play-row-activity">${escapeHtml(play.activity)}</span>` : ""}
          <span class="play-row-facts">${facts}</span>
        </div>
        <div class="play-row-players">${playPlayersMarkup(play)}</div>
        ${play.notes ? `<p class="play-row-notes">${escapeHtml(play.notes)}</p>` : ""}
      </div>
      <button class="icon-button play-row-edit" type="button" data-play-edit="${Number(play.id)}"
              aria-label="Modifica la partita del ${escapeHtml(playDate(play.played_on))}" title="Modifica">${icon("settings")}</button>
    </article>
  `;
}

function bindPlayRows(root, plays, onSaved) {
  root.querySelectorAll("[data-play-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const play = plays.find((item) => Number(item.id) === Number(button.dataset.playEdit));
      if (play) void openPlayDialog({play, onSaved});
    });
  });
}

async function loadOwnedGamesForPlays() {
  if (ownedGamesForPlays) return ownedGamesForPlays;
  const payload = await api("/api/games?owned=true&sort=title&limit=2000&offset=0");
  ownedGamesForPlays = (payload.items || []).map((game) => ({bgg_id: Number(game.bgg_id), title: game.title, item_type: game.item_type}));
  return ownedGamesForPlays;
}

function ensurePlayDialog() {
  if (playDialog) return playDialog;
  playDialog = document.createElement("dialog");
  playDialog.className = "dialog play-dialog";
  playDialog.setAttribute("aria-labelledby", "playDialogTitle");
  playDialog.innerHTML = `
    <form id="playForm" novalidate>
      <div class="dialog-head">
        <div>
          <p class="eyebrow">Partite</p>
          <h2 id="playDialogTitle">Registra partita</h2>
        </div>
        <button class="icon-button" id="closePlayDialog" type="button" aria-label="Chiudi">×</button>
      </div>
      <div class="play-form-grid">
        <label class="settings-field play-span-2" id="playGameField">
          <span>Gioco</span>
          <input id="playGame" type="text" list="playGameOptions" autocomplete="off" placeholder="Cerca nella ludoteca…" required>
          <datalist id="playGameOptions"></datalist>
        </label>
        <p class="play-game-fixed play-span-2" id="playGameFixed" hidden></p>
        <label class="settings-field">
          <span>Data</span>
          <input id="playDate" type="date" required>
        </label>
        <label class="settings-field">
          <span>Durata (minuti)</span>
          <input id="playDuration" type="number" min="1" max="10000" inputmode="numeric" placeholder="es. 90">
        </label>
        <fieldset class="play-players play-span-2">
          <legend>Giocatori</legend>
          <div class="play-copy-note" id="playCopyNote" hidden></div>
          <div class="play-player-head" aria-hidden="true"><span>Nome</span><span>Punti</span><span>Vince</span><span></span></div>
          <div id="playPlayerRows"></div>
          <datalist id="playPlayerNames"></datalist>
          <div class="play-player-actions">
            <button class="button button-ghost" id="playAddPlayer" type="button">${icon("plus")}<span>Giocatore</span></button>
            <label class="play-count-field">
              <span>Totale giocatori</span>
              <input id="playCount" type="number" min="1" max="99" inputmode="numeric">
            </label>
          </div>
        </fieldset>
        <label class="settings-field play-span-2">
          <span class="play-label-row">Cosa abbiamo fatto
            <button class="play-inline-action" id="playCopyActivity" type="button" hidden>Come l'ultima volta</button>
          </span>
          <input id="playActivity" type="text" maxlength="500" autocomplete="off" placeholder="Scenario, capitolo, missione, varianti…">
        </label>
        <label class="settings-field">
          <span>Esito</span>
          <select id="playOutcome">
            <option value="">—</option>
            ${Object.entries(PLAY_OUTCOMES).map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
          </select>
        </label>
        <label class="settings-field">
          <span>Luogo</span>
          <input id="playLocation" type="text" maxlength="120" list="playLocations" autocomplete="off" placeholder="es. Casa">
          <datalist id="playLocations"></datalist>
        </label>
        <label class="settings-field play-span-2">
          <span>Com'è andata</span>
          <textarea id="playNotes" rows="3" maxlength="4000" placeholder="Momenti chiave, regole da ricordare, impressioni…"></textarea>
        </label>
        <label class="play-check play-span-2">
          <input id="playCompleted" type="checkbox">
          <span>Con questa partita abbiamo completato il gioco (campagna, finale, tutte le missioni)</span>
        </label>
      </div>
      <div class="dialog-actions">
        <button class="button button-ghost play-delete" type="button" id="deletePlay" hidden>Elimina</button>
        <button class="button button-ghost" type="button" id="cancelPlayDialog">Annulla</button>
        <button class="button button-primary" type="submit" id="savePlay">Salva partita</button>
      </div>
    </form>
  `;
  document.body.append(playDialog);
  const close = () => playDialog.close();
  playDialog.querySelector("#closePlayDialog").addEventListener("click", close);
  playDialog.querySelector("#cancelPlayDialog").addEventListener("click", close);
  playDialog.querySelector("#playAddPlayer").addEventListener("click", () => {
    addPlayerRow({});
    playDialog.querySelector("#playPlayerRows .play-player-row:last-child input")?.focus();
  });
  playDialog.querySelector("#playGame").addEventListener("change", () => void onPlayGameChosen());
  playDialog.querySelector("#playCopyActivity").addEventListener("click", () => {
    playDialog.querySelector("#playActivity").value = playDialogContext?.defaults?.last_play?.activity || "";
  });
  playDialog.querySelector("#playForm").addEventListener("submit", (event) => {
    event.preventDefault();
    void savePlay();
  });
  playDialog.querySelector("#deletePlay").addEventListener("click", () => void deletePlay());
  return playDialog;
}

function addPlayerRow(player) {
  const rows = playDialog.querySelector("#playPlayerRows");
  const row = document.createElement("div");
  row.className = "play-player-row";
  row.innerHTML = `
    <input type="text" maxlength="60" list="playPlayerNames" autocomplete="off" aria-label="Nome giocatore" placeholder="Nome" value="${escapeHtml(player.name || "")}">
    <input type="text" maxlength="20" inputmode="decimal" aria-label="Punti" placeholder="—" value="${escapeHtml(player.score || "")}">
    <label class="play-winner" title="Vincitore"><input type="checkbox" aria-label="Vincitore" ${player.winner ? "checked" : ""}><span aria-hidden="true">${icon("crown")}</span></label>
    <button class="icon-button" type="button" aria-label="Rimuovi giocatore">×</button>
  `;
  row.querySelector("button").addEventListener("click", () => {
    row.remove();
    syncPlayerCount();
  });
  row.querySelector("input").addEventListener("input", syncPlayerCount);
  rows.append(row);
  syncPlayerCount();
}

function playerRowsData() {
  return [...playDialog.querySelectorAll(".play-player-row")].map((row) => {
    const [name, score] = row.querySelectorAll("input[type=text]");
    return {
      name: name.value.trim(),
      score: score.value.trim() || null,
      winner: row.querySelector("input[type=checkbox]").checked,
    };
  }).filter((player) => player.name || player.score || player.winner);
}

function syncPlayerCount() {
  const count = playDialog.querySelector("#playCount");
  const named = playerRowsData().length;
  if (!count.dataset.touched || Number(count.value) < named) count.value = named ? String(named) : "";
}

function setPlayers(players) {
  playDialog.querySelector("#playPlayerRows").innerHTML = "";
  for (const player of players) addPlayerRow(player);
  if (!players.length) addPlayerRow({});
}

// Players, place and activity are copied from the last play: of this game, else any.
function applyPlayDefaults(defaults, {copy}) {
  playDialogContext.defaults = defaults;
  playDialog.querySelector("#playPlayerNames").innerHTML = (defaults.player_names || [])
    .map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
  playDialog.querySelector("#playLocations").innerHTML = (defaults.locations || [])
    .map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
  const last = defaults.last_play;
  const note = playDialog.querySelector("#playCopyNote");
  const copyActivity = playDialog.querySelector("#playCopyActivity");
  copyActivity.hidden = !(defaults.same_game && last?.activity);
  copyActivity.textContent = last?.activity ? `Come l'ultima volta: ${last.activity}` : "Come l'ultima volta";
  if (!copy) {
    note.hidden = true;
    return;
  }
  if (!last) {
    note.hidden = true;
    setPlayers([]);
    return;
  }
  setPlayers((last.players || []).map((player) => ({name: player.name})));
  const count = playDialog.querySelector("#playCount");
  if (last.player_count) {
    count.value = String(last.player_count);
    count.dataset.touched = "1";
  }
  if (!playDialog.querySelector("#playLocation").value) playDialog.querySelector("#playLocation").value = last.location || "";
  note.hidden = false;
  note.innerHTML = `
    <span>Giocatori ripresi dall'ultima partita${defaults.same_game ? "" : ` (${escapeHtml(last.title)})`} del ${escapeHtml(playDate(last.played_on))}.</span>
    <button class="play-inline-action" type="button" id="playClearCopy">Svuota</button>
  `;
  note.querySelector("#playClearCopy").addEventListener("click", () => {
    delete count.dataset.touched;
    setPlayers([]);
    note.hidden = true;
  });
}

async function onPlayGameChosen() {
  const input = playDialog.querySelector("#playGame");
  const games = ownedGamesForPlays || [];
  const value = input.value.trim().toLowerCase();
  const game = games.find((item) => item.title.toLowerCase() === value);
  input.setCustomValidity(game ? "" : "Scegli un gioco della ludoteca");
  if (!game || playDialogContext.bggId === game.bgg_id) return;
  playDialogContext.bggId = game.bgg_id;
  try {
    applyPlayDefaults(await api(`/api/plays/defaults?bgg_id=${game.bgg_id}`), {copy: true});
  } catch (_) {}
}

async function openPlayDialog({bggId = null, title = "", play = null, onSaved = null} = {}) {
  ensurePlayDialog();
  playDialogContext = {bggId: play ? Number(play.bgg_id) : (bggId ? Number(bggId) : null), play, onSaved, defaults: null};
  const form = playDialog.querySelector("#playForm");
  form.reset();
  delete playDialog.querySelector("#playCount").dataset.touched;
  playDialog.querySelector("#playDialogTitle").textContent = play ? "Modifica partita" : "Registra partita";
  playDialog.querySelector("#deletePlay").hidden = !play;
  playDialog.querySelector("#playCopyNote").hidden = true;
  const dateInput = playDialog.querySelector("#playDate");
  dateInput.max = todayIso();
  dateInput.value = play?.played_on || todayIso();
  const fixed = Boolean(playDialogContext.bggId);
  playDialog.querySelector("#playGameField").hidden = fixed;
  const fixedLabel = playDialog.querySelector("#playGameFixed");
  fixedLabel.hidden = !fixed;
  fixedLabel.innerHTML = fixed ? `<span>Gioco</span><strong>${escapeHtml(play?.title || title || `BGG #${playDialogContext.bggId}`)}</strong>` : "";
  playDialog.querySelector("#playGame").required = !fixed;
  if (play) {
    setPlayers(play.players || []);
    const count = playDialog.querySelector("#playCount");
    count.value = play.player_count ? String(play.player_count) : "";
    if (play.player_count) count.dataset.touched = "1";
    playDialog.querySelector("#playDuration").value = play.duration_minutes || "";
    playDialog.querySelector("#playActivity").value = play.activity || "";
    playDialog.querySelector("#playOutcome").value = play.outcome || "";
    playDialog.querySelector("#playLocation").value = play.location || "";
    playDialog.querySelector("#playNotes").value = play.notes || "";
    playDialog.querySelector("#playCompleted").checked = Boolean(play.completed_game);
  } else {
    setPlayers([]);
  }
  openDialog(playDialog, {focus: fixed ? dateInput : playDialog.querySelector("#playGame")});
  try {
    const [defaults] = await Promise.all([
      api(`/api/plays/defaults${playDialogContext.bggId ? `?bgg_id=${playDialogContext.bggId}` : ""}`),
      fixed ? null : loadOwnedGamesForPlays().then((games) => {
        playDialog.querySelector("#playGameOptions").innerHTML = games
          .map((game) => `<option value="${escapeHtml(game.title)}"></option>`).join("");
      }),
    ]);
    applyPlayDefaults(defaults, {copy: !play});
  } catch (error) {
    showToast(error.message, true);
  }
}

async function savePlay() {
  const form = playDialog.querySelector("#playForm");
  if (!playDialogContext.bggId) {
    await onPlayGameChosen();
    if (!playDialogContext.bggId) {
      form.reportValidity();
      return;
    }
  }
  const dateInput = playDialog.querySelector("#playDate");
  if (!dateInput.value) {
    dateInput.reportValidity();
    return;
  }
  const number = (selector) => {
    const value = Number(playDialog.querySelector(selector).value);
    return Number.isInteger(value) && value > 0 ? value : null;
  };
  const text = (selector) => playDialog.querySelector(selector).value.trim() || null;
  const players = playerRowsData();
  const payload = {
    played_on: dateInput.value,
    players,
    player_count: number("#playCount") || (players.length || null),
    duration_minutes: number("#playDuration"),
    activity: text("#playActivity"),
    outcome: playDialog.querySelector("#playOutcome").value || null,
    location: text("#playLocation"),
    notes: text("#playNotes"),
    completed_game: playDialog.querySelector("#playCompleted").checked,
  };
  const button = playDialog.querySelector("#savePlay");
  button.disabled = true;
  try {
    const play = playDialogContext.play
      ? await api(`/api/plays/${playDialogContext.play.id}`, {
          method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
        })
      : await api(`/api/games/${playDialogContext.bggId}/plays`, {
          method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
        });
    playDialog.close();
    showToast(playDialogContext.play ? "Partita aggiornata." : `Partita a ${play.title} registrata.`);
    await playDialogContext.onSaved?.(play);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function deletePlay() {
  const play = playDialogContext?.play;
  if (!play || !window.confirm(`Eliminare la partita a ${play.title} del ${playDate(play.played_on)}?`)) return;
  try {
    await api(`/api/plays/${play.id}`, {method: "DELETE"});
    playDialog.close();
    showToast("Partita eliminata.");
    await playDialogContext.onSaved?.(null);
  } catch (error) {
    showToast(error.message, true);
  }
}

// Section of the Ludoteca game page: last plays and quick logging.
async function refreshGamePlays(game) {
  const target = document.querySelector("#gamePlaysList");
  const count = document.querySelector("#gamePlaysCount");
  if (!target) return;
  try {
    const payload = await api(`/api/plays?bgg_id=${game.bgg_id}&limit=5`);
    if (!target.isConnected) return;
    const imported = Number(game.progress?.imported_num_plays || 0);
    count.textContent = payload.total
      ? `${formatNumber(payload.total, 0)} ${payload.total === 1 ? "partita" : "partite"}`
      : (imported ? `${formatNumber(imported, 0)} su BGG` : "");
    target.innerHTML = payload.items.length
      ? payload.items.map((play) => playRow(play, {showGame: false})).join("")
        + (payload.total > payload.items.length
          ? `<a class="play-more" href="/plays?game=${game.bgg_id}" data-nav>Tutte le ${formatNumber(payload.total, 0)} partite ${icon("arrow-right")}</a>`
          : "")
      : `<p class="play-empty">Nessuna partita registrata${imported ? ` qui (BGG ne riporta ${formatNumber(imported, 0)})` : ""}. Registra la prossima per tenere traccia di giocatori, scenari ed esiti.</p>`;
    bindPlayRows(target, payload.items, () => refreshGamePlays(game));
  } catch (error) {
    target.innerHTML = `<p class="play-empty">${escapeHtml(error.message)}</p>`;
  }
}

function playMonthChart(months) {
  const now = new Date();
  const series = Array.from({length: 12}, (_, index) => {
    const date = new Date(now.getFullYear(), now.getMonth() - 11 + index, 1);
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    return {key, label: date.toLocaleDateString("it-IT", {month: "narrow"}), title: date.toLocaleDateString("it-IT", {month: "long", year: "numeric"}),
      plays: Number((months || []).find((item) => item.month === key)?.plays || 0)};
  });
  const max = Math.max(1, ...series.map((item) => item.plays));
  return `
    <ol class="play-months" aria-label="Partite negli ultimi 12 mesi">
      ${series.map((item) => `
        <li title="${escapeHtml(`${item.title}: ${item.plays} partite`)}">
          <span class="play-month-bar" style="--h:${Math.round((item.plays / max) * 100)}%"><b>${item.plays || ""}</b></span>
          <small aria-hidden="true">${escapeHtml(item.label)}</small>
        </li>
      `).join("")}
    </ol>
  `;
}

function playedGameCard(game, stats) {
  const plays = stats?.plays || 0;
  const lastPlayed = stats?.last_played_on || game.progress?.played_at;
  const lines = [
    plays ? `${formatNumber(plays, 0)} ${plays === 1 ? "partita" : "partite"}` : "Giocato",
    lastPlayed ? `${plays ? "ultima " : ""}${playDate(lastPlayed)}` : "",
  ].filter(Boolean).join(" · ");
  return `
    <a class="trophy-card" href="/games/${encodeURIComponent(game.bgg_id)}" data-nav>
      <span class="trophy-crown" aria-hidden="true">${icon(game.progress?.completed ? "crown" : "diamond")}</span>
      <span class="trophy-cover">${game.bgg_metadata?.cover_url
        ? `<img src="${coverSrc(game.bgg_id)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : `<span class="trophy-cover-fallback">${escapeHtml(initials(game.title))}</span>`}</span>
      <span class="trophy-card-body">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${escapeHtml(lines)}</small>
        <span class="trophy-achievements">${completionAchievementMarkup(game)}</span>
      </span>
    </a>
  `;
}

async function refreshPlaysPage() {
  const list = document.querySelector("#playsList");
  if (!list) return;
  const params = new URLSearchParams({limit: "200"});
  if (playsState.q) params.set("q", playsState.q);
  if (playsState.player) params.set("player", playsState.player);
  if (playsState.bggId) params.set("bgg_id", String(playsState.bggId));
  try {
    const [summary, plays, games] = await Promise.all([
      api("/api/plays/summary"),
      api(`/api/plays?${params.toString()}`),
      api("/api/games?owned=true&played=true&sort=played_desc&limit=500&offset=0"),
    ]);
    if (!list.isConnected) return;
    const completed = (games.items || []).filter((game) => game.progress?.completed);
    document.querySelector("#playsStatPlays").textContent = formatNumber(summary.plays, 0);
    document.querySelector("#playsStatGames").textContent = formatNumber((games.items || []).length, 0);
    document.querySelector("#playsStatCompleted").textContent = formatNumber(completed.length, 0);
    document.querySelector("#playsStatYear").textContent = formatNumber(summary.this_year, 0);
    document.querySelector("#playsSummary").textContent = summary.last_played_on
      ? `Ultima partita il ${playDate(summary.last_played_on)}${summary.minutes ? ` ${playDuration(summary.minutes)} di gioco registrate` : ""}`
      : "Registra le partite per costruire il tuo diario di gioco";
    const playerSelect = document.querySelector("#playsPlayer");
    playerSelect.innerHTML = `<option value="">Tutti i giocatori</option>${summary.players
      .map((player) => `<option value="${escapeHtml(player.name)}" ${player.name === playsState.player ? "selected" : ""}>${escapeHtml(player.name)}</option>`).join("")}`;

    document.querySelector("#playsSide").innerHTML = `
      <section class="plays-side-block">
        <h2>Ultimi 12 mesi</h2>
        ${playMonthChart(summary.months)}
      </section>
      <section class="plays-side-block">
        <h2>Giocatori</h2>
        ${summary.players.length ? `<ol class="plays-leaderboard">${summary.players.map((player) => `
          <li><button type="button" data-plays-player="${escapeHtml(player.name)}" class="${player.name === playsState.player ? "is-active" : ""}">
            <span>${escapeHtml(player.name)}</span>
            <small>${formatNumber(player.plays, 0)} partite${player.wins ? ` · <b>${formatNumber(player.wins, 0)}</b> vittorie` : ""}</small>
          </button></li>`).join("")}</ol>`
          : '<p class="play-empty">I nomi dei giocatori registrati compariranno qui.</p>'}
      </section>
      ${completed.length ? `
        <section class="plays-side-block">
          <h2>Completati</h2>
          <div class="plays-completed">${completed.slice(0, 6).map((game) => trophyGameCard(game, {compact: true})).join("")}</div>
        </section>
      ` : ""}
    `;
    document.querySelectorAll("[data-plays-player]").forEach((button) => {
      button.addEventListener("click", () => {
        playsState.player = playsState.player === button.dataset.playsPlayer ? "" : button.dataset.playsPlayer;
        playsState.view = "log";
        void renderPlays();
      });
    });

    const filterGame = playsState.bggId ? (games.items || []).find((game) => Number(game.bgg_id) === playsState.bggId) : null;
    const filters = [
      filterGame || playsState.bggId ? `<button type="button" class="active-facet-chip" data-plays-clear="game">${escapeHtml(filterGame?.title || plays.items[0]?.title || `BGG #${playsState.bggId}`)} <span aria-hidden="true">×</span></button>` : "",
      playsState.player ? `<button type="button" class="active-facet-chip" data-plays-clear="player">${escapeHtml(playsState.player)} <span aria-hidden="true">×</span></button>` : "",
    ].join("");
    document.querySelector("#playsFilters").innerHTML = filters;
    // Filters narrow the diary only; the games view always lists every played game.
    document.querySelector("#playsFilters").hidden = !filters || playsState.view === "games";
    document.querySelectorAll("[data-plays-clear]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.playsClear === "game") {
          playsState.bggId = null;
          history.replaceState({}, "", "/plays");
        } else {
          playsState.player = "";
        }
        void renderPlays();
      });
    });

    if (playsState.view === "games") {
      const statsById = new Map(summary.games_played.map((item) => [Number(item.bgg_id), item]));
      list.className = "trophy-wall plays-games";
      list.innerHTML = (games.items || []).length
        ? games.items.map((game) => playedGameCard(game, statsById.get(Number(game.bgg_id)))).join("")
        : `<div class="empty trophy-empty"><strong>Nessun gioco giocato.</strong><span>Registra una partita o segna un gioco come giocato dalla sua scheda.</span></div>`;
      return;
    }
    list.className = "plays-log";
    if (!plays.items.length) {
      list.innerHTML = `<div class="empty trophy-empty">
        <strong>${summary.plays ? "Nessuna partita corrisponde ai filtri." : "Nessuna partita registrata."}</strong>
        <span>${summary.plays ? "Cambia la ricerca o rimuovi i filtri." : "Con “Registra partita” tieni traccia di data, giocatori, scenario ed esito: i giocatori si ricopiano da soli nella partita successiva."}</span>
      </div>`;
      return;
    }
    let month = "";
    list.innerHTML = plays.items.map((play) => {
      const key = play.played_on.slice(0, 7);
      const heading = key !== month
        ? `<h2 class="plays-month">${escapeHtml(playDate(`${key}-01`, {month: "long", year: "numeric"}))}</h2>`
        : "";
      month = key;
      return heading + playRow(play);
    }).join("") + (plays.total > plays.items.length
      ? `<p class="play-empty">Mostrate le ultime ${formatNumber(plays.items.length, 0)} di ${formatNumber(plays.total, 0)} partite: usa la ricerca per trovare le altre.</p>`
      : "");
    bindPlayRows(list, plays.items, () => refreshPlaysPage());
  } catch (error) {
    list.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function renderPlays() {
  if (/^\/completed\/?$/.test(window.location.pathname)) {
    history.replaceState({}, "", "/plays");
    playsState.view = "games";
  }
  const params = new URLSearchParams(window.location.search);
  playsState.bggId = Number(params.get("game")) || null;
  document.title = "Partite · BoardGameCompanion";
  app.innerHTML = `
    <section class="page-header catalog-page-header plays-header">
      <div class="page-header-copy">
        <h1>Partite</h1>
        <p class="muted catalog-page-summary" id="playsSummary" aria-live="polite">Caricamento…</p>
      </div>
      <section class="catalog-stats" aria-label="Riepilogo partite">
        <div class="stat"><strong id="playsStatPlays">—</strong><span>Partite</span></div>
        <div class="stat"><strong id="playsStatGames">—</strong><span>Giochi giocati</span></div>
        <div class="stat"><strong id="playsStatCompleted">—</strong><span>Completati</span></div>
        <div class="stat"><strong id="playsStatYear">—</strong><span>Quest'anno</span></div>
      </section>
    </section>

    <section class="catalog-workspace plays-workspace" aria-label="Partite">
      <section class="toolbar catalog-simple-search" aria-label="Filtra partite">
        <label class="field search-field">
          <input id="playsQuery" type="search" autocomplete="off" placeholder="Cerca gioco, giocatore, scenario, note…"
                 aria-label="Cerca nelle partite" value="${escapeHtml(playsState.q)}">
        </label>
        <label class="field plays-player-field">
          <select id="playsPlayer" aria-label="Giocatore"><option value="">Tutti i giocatori</option></select>
        </label>
        <div class="catalog-view-switch catalog-filter-view plays-view-switch" role="group" aria-label="Vista">
          <button class="view-switch-button ${playsState.view === "log" ? "is-active" : ""}" type="button" data-plays-view="log"
                  aria-pressed="${playsState.view === "log"}">${icon("list")}<span>Diario</span></button>
          <button class="view-switch-button ${playsState.view === "games" ? "is-active" : ""}" type="button" data-plays-view="games"
                  aria-pressed="${playsState.view === "games"}">${icon("catalog")}<span>Giochi</span></button>
        </div>
        <button class="button button-primary plays-add" id="playsAdd" type="button">${icon("plus")}<span>Registra partita</span></button>
      </section>
      <div class="plays-filters" id="playsFilters" hidden></div>
      <div class="plays-layout">
        <div class="plays-log" id="playsList">${skeletons()}</div>
        <aside class="plays-side" id="playsSide" aria-label="Statistiche"></aside>
      </div>
    </section>
  `;
  let searchTimer = null;
  const query = document.querySelector("#playsQuery");
  query.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      playsState.q = query.value.trim();
      if (playsState.view !== "log") {
        playsState.view = "log";
        void renderPlays();
        return;
      }
      void refreshPlaysPage();
    }, 300);
  });
  document.querySelector("#playsPlayer").addEventListener("change", (event) => {
    playsState.player = event.target.value;
    playsState.view = "log";
    void renderPlays();
  });
  document.querySelectorAll("[data-plays-view]").forEach((button) => {
    button.addEventListener("click", () => {
      playsState.view = button.dataset.playsView;
      void renderPlays();
    });
  });
  document.querySelector("#playsAdd").addEventListener("click", () => {
    const game = playsState.bggId ? {bggId: playsState.bggId} : {};
    void openPlayDialog({...game, onSaved: () => refreshPlaysPage()});
  });
  await refreshPlaysPage();
}

const discoverySources = [
  ["library", "Ludoteca", "shelf", "Giochi base posseduti"],
  ["catalog", "Catalogo", "globe", "Catalogo BGG non posseduto"],
];

function sourceFlags(source) {
  return {library: source !== "catalog", catalog: source !== "library"};
}

// Ludoteca/Catalogo checkboxes shared by Esplora and Classifiche.
function sourceBoxes(scope, source) {
  const flags = sourceFlags(source);
  return discoverySources.map(([key, label, iconName, hint]) => `
    <button class="explore-source-box ${flags[key] ? "is-active" : ""}" type="button"
            role="checkbox" aria-checked="${flags[key]}" data-${scope}-source="${key}" title="${hint}">
      <span class="explore-source-icon" aria-hidden="true">${icon(iconName)}</span>
      <strong>${label}</strong>
      <span class="explore-source-check" aria-hidden="true">${icon("check")}</span>
    </button>
  `).join("");
}

function bindSourceBoxes(scope, target, storageKey, onChange) {
  const selector = `[data-${scope}-source]`;
  document.querySelectorAll(selector).forEach((button) => {
    button.addEventListener("click", () => {
      const flags = sourceFlags(target.source);
      const key = button.getAttribute(`data-${scope}-source`);
      flags[key] = !flags[key];
      // At least one box stays checked: unchecking the last one switches to the other.
      if (!flags.library && !flags.catalog) flags[key === "library" ? "catalog" : "library"] = true;
      target.source = flags.library && flags.catalog ? "both" : (flags.library ? "library" : "catalog");
      window.localStorage.setItem(storageKey, target.source);
      document.querySelectorAll(selector).forEach((item) => {
        const active = flags[item.getAttribute(`data-${scope}-source`)];
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-checked", String(active));
      });
      onChange();
    });
  });
}

function exploreParams() {
  const params = new URLSearchParams({
    source: exploreState.source,
    limit: exploreState.expandedResults ? "250" : "12",
  });
  [...exploreState.categories].forEach((value) => params.append("category", value));
  [...exploreState.mechanics].forEach((value) => params.append("mechanic", value));
  [...exploreState.categoryGroups].forEach((value) => params.append("category_group", value));
  [...exploreState.mechanicGroups].forEach((value) => params.append("mechanic_group", value));
  for (const [key, value] of [
    ["supports_players", exploreState.supportsPlayers],
    ["ideal_players", exploreState.idealPlayers],
    ["player_age", exploreState.playerAge],
    ["weight", exploreState.weight],
    ["max_minutes", exploreState.maxMinutes],
    ["min_rating", exploreState.minRating],
    ["max_language", exploreState.maxLanguage],
  ]) {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  }
  return params;
}

function exploreGroupLabels(payload) {
  const labels = {};
  for (const group of [...(payload?.category_groups || []), ...(payload?.mechanic_groups || [])]) {
    labels[group.key] = group.label;
  }
  return labels;
}

function exploreSelectionChips(payload) {
  const labels = exploreGroupLabels(payload);
  const chips = [
    ...[...exploreState.categoryGroups].map((name) => ({kind: "category-group", name, label: labels[name] || name})),
    ...[...exploreState.categories].map((name) => ({kind: "category", name, label: name})),
    ...[...exploreState.mechanicGroups].map((name) => ({kind: "mechanic-group", name, label: labels[name] || name})),
    ...[...exploreState.mechanics].map((name) => ({kind: "mechanic", name, label: name})),
  ];
  return chips.map((item) => `
    <button class="explore-selection-chip ${item.kind.endsWith("group") ? "is-group" : ""}" type="button"
            data-explore-remove-kind="${item.kind}" data-explore-remove-name="${escapeHtml(item.name)}"
            aria-label="Rimuovi ${escapeHtml(item.label)}">
      ${item.kind.endsWith("group") ? exploreGroupArt(item.name) : ""}
      <strong>${escapeHtml(item.label)}</strong><span aria-hidden="true">×</span>
    </button>
  `).join("");
}

function exploreSelectionSets(kind) {
  return kind === "category"
    ? {items: exploreState.categories, groups: exploreState.categoryGroups}
    : {items: exploreState.mechanics, groups: exploreState.mechanicGroups};
}

function exploreGroupTile(group, kind, facets) {
  const {groups} = exploreSelectionSets(kind);
  const selected = groups.has(group.key);
  const open = exploreState.openGroup[kind] === group.key;
  const members = facets.filter((item) => item.group === group.key);
  const chosen = members.filter((item) => item.selected).length;
  const empty = !group.count && !selected && !chosen;
  return `
    <button class="explore-group-tile ${selected ? "is-selected" : ""} ${open ? "is-open" : ""}" type="button"
            data-explore-group="${group.key}" aria-expanded="${open}" ${empty ? "disabled" : ""}>
      ${exploreGroupArt(group.key)}
      <span class="explore-group-text">
        <strong>${escapeHtml(group.label)}</strong>
        <small>${formatNumber(group.count, 0)} giochi · ${formatNumber(members.length, 0)} voci${chosen ? ` · ${chosen} scelte` : ""}</small>
      </span>
      <span class="explore-group-caret" aria-hidden="true">${icon(open ? "caret-up" : "caret-down")}</span>
    </button>
  `;
}

function exploreFacetChip(item, kind) {
  return `
    <button class="explore-facet-chip ${item.selected ? "is-selected" : ""}" type="button"
            data-explore-kind="${kind}" data-explore-name="${escapeHtml(item.name)}"
            aria-pressed="${item.selected ? "true" : "false"}">
      <span>${escapeHtml(item.name)}</span><small>${formatNumber(item.count, 0)}</small>
    </button>
  `;
}

const EXPLORE_MEMBER_PREVIEW = 12;

function exploreGroupDrawer(group, kind, facets) {
  const {groups} = exploreSelectionSets(kind);
  const members = facets.filter((item) => item.group === group.key);
  const visible = exploreState.showAllMembers ? members : members.slice(0, EXPLORE_MEMBER_PREVIEW);
  const hidden = members.length - visible.length;
  const selected = groups.has(group.key);
  return `
    <div class="explore-group-drawer" id="exploreGroupDrawer">
      <div class="explore-group-drawer-head">
        <strong>${escapeHtml(group.label)}</strong>
        <button class="explore-group-select ${selected ? "is-selected" : ""}" type="button"
                data-explore-group-select="${group.key}" aria-pressed="${selected}">
          ${icon(selected ? "check" : "plus")}<span>${selected ? "Gruppo selezionato" : "Qualsiasi voce del gruppo"}</span>
        </button>
      </div>
      <div class="explore-facet-chips">
        ${visible.map((item) => exploreFacetChip(item, kind)).join("") || '<span class="muted">Nessuna voce compatibile con la selezione.</span>'}
        ${hidden > 0 ? `<button class="explore-more-chip" type="button" data-explore-show-all>+ altre ${formatNumber(hidden, 0)}</button>` : ""}
        ${exploreState.showAllMembers && members.length > EXPLORE_MEMBER_PREVIEW ? '<button class="explore-more-chip" type="button" data-explore-show-all>Mostra meno</button>' : ""}
      </div>
    </div>
  `;
}

function renderExploreFacets(payload) {
  const container = document.querySelector("#exploreGroups");
  if (!container) return;
  const kind = exploreState.activeTab;
  const facets = (kind === "category" ? payload.categories : payload.mechanics) || [];
  const groups = (kind === "category" ? payload.category_groups : payload.mechanic_groups) || [];
  const query = exploreState.facetQuery.trim().toLocaleLowerCase("it");

  if (query) {
    const matches = facets.filter((item) => item.name.toLocaleLowerCase("it").includes(query));
    container.innerHTML = `
      <div class="explore-group-drawer is-search">
        <div class="explore-facet-chips">
          ${matches.map((item) => exploreFacetChip(item, kind)).join("") || '<span class="muted">Nessuna voce trovata.</span>'}
        </div>
      </div>
    `;
  } else {
    const visibleGroups = groups.filter((group) =>
      group.key !== "other" || facets.some((item) => item.group === "other"));
    const openKey = exploreState.openGroup[kind];
    const openGroup = visibleGroups.find((group) => group.key === openKey);
    container.innerHTML = `
      <div class="explore-group-grid">
        ${visibleGroups.map((group) => exploreGroupTile(group, kind, facets)).join("")}
      </div>
      ${openGroup ? exploreGroupDrawer(openGroup, kind, facets) : ""}
    `;
  }

  container.querySelectorAll("[data-explore-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.exploreGroup;
      exploreState.openGroup[kind] = exploreState.openGroup[kind] === key ? "" : key;
      exploreState.showAllMembers = false;
      renderExploreFacets(payload);
    });
  });
  container.querySelector("[data-explore-group-select]")?.addEventListener("click", (event) => {
    const {groups: selected} = exploreSelectionSets(kind);
    const key = event.currentTarget.dataset.exploreGroupSelect;
    if (selected.has(key)) selected.delete(key);
    else selected.add(key);
    exploreState.expandedResults = false;
    refreshExplore();
  });
  container.querySelectorAll("[data-explore-show-all]").forEach((button) => {
    button.addEventListener("click", () => {
      exploreState.showAllMembers = !exploreState.showAllMembers;
      renderExploreFacets(payload);
    });
  });
  container.querySelectorAll("[data-explore-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      const {items} = exploreSelectionSets(button.dataset.exploreKind);
      const name = button.dataset.exploreName;
      if (items.has(name)) items.delete(name);
      else items.add(name);
      exploreState.expandedResults = false;
      refreshExplore();
    });
  });
}

const exploreOptionalGroups = [
  {apiKey: "supports_players", stateKey: "supportsPlayers", title: "Giocatori"},
  {apiKey: "ideal_players", stateKey: "idealPlayers", title: "Ideale in"},
  {apiKey: "player_age", stateKey: "playerAge", title: "Età minima"},
  {apiKey: "max_minutes", stateKey: "maxMinutes", title: "Durata (min)"},
  {apiKey: "weight", stateKey: "weight", title: "Complessità"},
  {apiKey: "min_rating", stateKey: "minRating", title: "Voto BGG"},
  {apiKey: "max_language", stateKey: "maxLanguage", title: "Dipendenza dalla lingua"},
];

function exploreOptionalGroup(group, options) {
  const current = String(exploreState[group.stateKey] || "");
  const buttons = Array.isArray(options) ? options : [];
  return `
    <section class="explore-option-group ${buttons.length ? "" : "is-empty"}">
      <h3>${escapeHtml(group.title)}</h3>
      <div class="explore-option-buttons">
        ${buttons.map((option) => {
          const selected = Boolean(option.selected) || current === String(option.value);
          return `
            <button class="explore-option-button ${selected ? "is-selected" : ""}"
                    type="button"
                    data-explore-option-key="${group.apiKey}"
                    data-explore-option-state="${group.stateKey}"
                    data-explore-option-value="${escapeHtml(String(option.value))}"
                    aria-pressed="${selected ? "true" : "false"}"
                    title="${formatNumber(option.count, 0)} giochi compatibili">
              <span>${escapeHtml(String(option.label))}</span>
              <small>${formatNumber(option.count, 0)}</small>
            </button>
          `;
        }).join("") || '<span class="explore-option-none">Nessun dato compatibile</span>'}
      </div>
    </section>
  `;
}

function exploreActiveOptionalCount() {
  return exploreOptionalGroups.filter((group) => String(exploreState[group.stateKey] || "")).length;
}

function renderExploreOptionalFilters(payload) {
  const container = document.querySelector("#exploreFilterOptions");
  if (!container) return;
  const options = payload.options || {};
  container.innerHTML = exploreOptionalGroups
    .map((group) => exploreOptionalGroup(group, options[group.apiKey] || []))
    .join("");
  const active = exploreActiveOptionalCount();
  const toggleCount = document.querySelector("#exploreFilterToggleCount");
  if (toggleCount) toggleCount.textContent = active ? String(active) : "";
  const reset = document.querySelector("#exploreResetOptional");
  if (reset) reset.disabled = !active;

  container.querySelectorAll("[data-explore-option-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const stateKey = button.dataset.exploreOptionState;
      const value = String(button.dataset.exploreOptionValue || "");
      exploreState[stateKey] = String(exploreState[stateKey] || "") === value ? "" : value;
      exploreState.expandedResults = false;
      refreshExplore();
    });
  });
}

function exploreResultCard(game) {
  if (game.source === "catalog") {
    return gameCard(referenceAsGame(game), [], {reference: game});
  }
  return gameCard(game, []);
}

function renderExplorePayload(payload) {
  currentExplorePayload = payload;
  const visibleGames = exploreState.expandedResults
    ? (payload.games || [])
    : (payload.games || []).slice(0, 12);

  const selections = document.querySelector("#exploreSelections");
  const resultCount = document.querySelector("#exploreResultCount");
  const resultGrid = document.querySelector("#exploreResultGrid");
  const resultMore = document.querySelector("#exploreResultMore");
  if (!selections || !resultCount || !resultGrid || !resultMore) return;

  const chips = exploreSelectionChips(payload);
  selections.hidden = !chips;
  selections.innerHTML = chips
    ? `
      <div class="explore-selection-chips">${chips}</div>
      <button class="button button-ghost explore-clear-selections" id="exploreClearSelections" type="button">Azzera</button>
    `
    : "";

  for (const [kind, groups] of [["category", payload.category_groups], ["mechanic", payload.mechanic_groups]]) {
    const counter = document.querySelector(`[data-explore-tab="${kind}"] small`);
    if (counter) {
      const count = (groups || []).filter((group) => group.count > 0).length;
      counter.textContent = formatNumber(count, 0);
    }
  }
  renderExploreFacets(payload);

  resultCount.textContent = Number(payload.total) === 1
    ? "1 gioco corrispondente"
    : `${formatNumber(payload.total, 0)} giochi corrispondenti`;
  resultGrid.innerHTML = visibleGames.length
    ? visibleGames.map(exploreResultCard).join("")
    : '<div class="empty catalog-empty">Nessun gioco soddisfa contemporaneamente tutti i criteri.</div>';
  bindBggCatalogCards(resultGrid);

  const hiddenCount = Math.max(0, Number(payload.total || 0) - visibleGames.length);
  resultMore.hidden = hiddenCount === 0 && !exploreState.expandedResults;
  resultMore.textContent = exploreState.expandedResults
    ? "Mostra meno"
    : `Mostra altri ${formatNumber(Math.min(hiddenCount, 238), 0)}`;

  renderExploreOptionalFilters(payload);

  selections.querySelectorAll("[data-explore-remove-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      const [kind, isGroup] = button.dataset.exploreRemoveKind.split("-");
      const sets = exploreSelectionSets(kind);
      (isGroup ? sets.groups : sets.items).delete(button.dataset.exploreRemoveName);
      exploreState.expandedResults = false;
      refreshExplore();
    });
  });

  document.querySelector("#exploreClearSelections")?.addEventListener("click", () => {
    exploreState.categories.clear();
    exploreState.mechanics.clear();
    exploreState.categoryGroups.clear();
    exploreState.mechanicGroups.clear();
    exploreState.expandedResults = false;
    refreshExplore();
  });

  resultMore.onclick = () => {
    if (!exploreState.expandedResults) {
      exploreState.expandedResults = true;
      refreshExplore();
      return;
    }
    exploreState.expandedResults = false;
    renderExplorePayload(payload);
  };
}

async function refreshExplore() {
  const groups = document.querySelector("#exploreGroups");
  const resultGrid = document.querySelector("#exploreResultGrid");
  if (!groups || !resultGrid) return;

  exploreRequestController?.abort();
  const controller = new AbortController();
  exploreRequestController = controller;
  const layout = document.querySelector(".explore-layout");
  layout?.classList.add("is-refreshing");
  layout?.setAttribute("aria-busy", "true");
  if (!currentExplorePayload) {
    resultGrid.innerHTML = skeletons();
  }

  try {
    const [payload] = await Promise.all([
      api(`/api/catalog/explore?${exploreParams()}`, {signal: controller.signal}),
      exploreState.source === "library" ? null : refreshWishlistIndex().catch(() => null),
    ]);
    if (controller.signal.aborted || !document.querySelector("#exploreGroups")) return;
    renderExplorePayload(payload);
  } catch (error) {
    if (error.name === "AbortError") return;
    groups.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    resultGrid.innerHTML = "";
    showToast(error.message, true);
  } finally {
    if (exploreRequestController === controller) {
      exploreRequestController = undefined;
      const liveLayout = document.querySelector(".explore-layout");
      liveLayout?.classList.remove("is-refreshing");
      liveLayout?.removeAttribute("aria-busy");
    }
  }
}

function bindExploreControls() {
  bindSourceBoxes("explore", exploreState, "bgc.exploreSource", () => {
    exploreState.expandedResults = false;
    refreshExplore();
  });

  document.querySelectorAll("[data-explore-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      exploreState.activeTab = button.dataset.exploreTab;
      exploreState.showAllMembers = false;
      document.querySelectorAll("[data-explore-tab]").forEach((item) => {
        const active = item.dataset.exploreTab === exploreState.activeTab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      const input = document.querySelector("#exploreFacetQuery");
      if (input) input.placeholder = exploreState.activeTab === "category" ? "Cerca un genere…" : "Cerca una meccanica…";
      if (currentExplorePayload) renderExploreFacets(currentExplorePayload);
    });
  });

  const input = document.querySelector("#exploreFacetQuery");
  input?.addEventListener("input", () => {
    exploreState.facetQuery = String(input.value || "");
    if (currentExplorePayload) renderExploreFacets(currentExplorePayload);
  });

  document.querySelector("#exploreFilterToggle")?.addEventListener("click", (event) => {
    const panel = document.querySelector(".explore-filter-panel");
    const open = !panel?.classList.contains("is-open");
    panel?.classList.toggle("is-open", open);
    event.currentTarget.setAttribute("aria-expanded", String(open));
  });

  document.querySelector("#exploreResetOptional")?.addEventListener("click", () => {
    for (const group of exploreOptionalGroups) exploreState[group.stateKey] = "";
    exploreState.expandedResults = false;
    refreshExplore();
  });
}

async function renderExplore(initialTab = null) {
  currentExplorePayload = null;
  if (initialTab === "category" || initialTab === "mechanic") {
    exploreState.activeTab = initialTab;
  }
  const tab = exploreState.activeTab;
  app.innerHTML = `
    <section class="page-header catalog-page-header explore-page-header">
      <div class="page-header-copy">
        <h1>Esplora</h1>
        <p class="muted catalog-page-summary rankings-page-summary">
          <span>Trova giochi per genere, meccaniche e caratteristiche che ti interessano</span>
          <span aria-hidden="true">·</span>
          <span id="exploreResultCount" aria-live="polite">Caricamento…</span>
        </p>
      </div>
      <div class="explore-sources" role="group" aria-label="Dove cercare">${sourceBoxes("explore", exploreState.source)}</div>
    </section>

    <section class="explore-layout">
      <div class="explore-main">
        <section class="explore-selection-bar" id="exploreSelections" aria-label="Criteri selezionati" hidden></section>

        <section class="toolbar explore-facet-toolbar" aria-label="Generi e meccaniche">
          <div class="catalog-stats catalog-sort-pills explore-tabs" role="tablist" aria-label="Tipo di criterio">
            ${[["category", "Generi"], ["mechanic", "Meccaniche"]].map(([value, label]) => `
              <button class="stat ${tab === value ? "is-active" : ""}" type="button" role="tab"
                      data-explore-tab="${value}" aria-selected="${tab === value}">
                <span>${label}</span><small></small>
              </button>
            `).join("")}
          </div>
          <label class="field search-field explore-facet-search">
            <input id="exploreFacetQuery" type="search" autocomplete="off" maxlength="80"
                   placeholder="${tab === "category" ? "Cerca un genere…" : "Cerca una meccanica…"}"
                   aria-label="Cerca tra generi e meccaniche" value="${escapeHtml(exploreState.facetQuery)}">
          </label>
          <button class="button button-ghost explore-filter-toggle" id="exploreFilterToggle" type="button"
                  aria-expanded="false" aria-controls="exploreFilterPanel">
            Parametri <span class="explore-filter-toggle-count" id="exploreFilterToggleCount"></span>
          </button>
        </section>

        <section class="explore-groups" id="exploreGroups" aria-live="polite"></section>

        <section class="explore-results-section" aria-labelledby="exploreGamesTitle">
          <div class="explore-results-head">
            <h2 id="exploreGamesTitle">Giochi corrispondenti</h2>
            <button class="button button-ghost" id="exploreResultMore" type="button" hidden>Mostra altri</button>
          </div>
          <div class="catalog-results catalog-results-cards catalog-columns-4 explore-result-grid" id="exploreResultGrid">${skeletons()}</div>
        </section>
      </div>

      <aside class="explore-filter-panel" id="exploreFilterPanel" aria-label="Parametri">
        <div class="explore-filter-options" id="exploreFilterOptions"></div>
        <button class="button button-ghost explore-reset-optional" id="exploreResetOptional" type="button" disabled>Azzera parametri</button>
      </aside>
    </section>
  `;

  bindExploreControls();
  document.title = "Esplora · BoardGameCompanion";
  await refreshExplore();
}

const suggestionsState = {
  sort: "for_you",
  view: "new",
  count: ["5", "10", "20", "50"].includes(window.localStorage.getItem("bgc.suggestionsCount"))
    ? window.localStorage.getItem("bgc.suggestionsCount")
    : "10",
};

const crowdfundingState = {
  sort: "top",
  platform: "all",
};

function crowdfundingTimeLabel(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "";
  if (value < 3600) return `${Math.max(1, Math.ceil(value / 60))} min`;
  if (value < 86400) return `${Math.ceil(value / 3600)} h`;
  return `${Math.ceil(value / 86400)} giorni`;
}

function crowdfundingStatusLabel(item) {
  if (item.status === "ending_soon") return "In scadenza";
  if (item.status === "upcoming") return "Upcoming";
  if (item.status === "ended") return "Terminata";
  return "Attiva";
}

function crowdfundingCard(item) {
  const funds = formatCampaignMoney(item.funds, item.currency);
  const platform = String(item.platform || "gamefound").toLowerCase();
  const sourceKey = String(item.project_url || item.id || item.title || "");
  const wishlist = wishlistEntry("crowdfunding", sourceKey);
  const goal = Number(item.goal) > 0 ? formatCampaignMoney(item.goal, item.currency) : "—";
  const percent = item.funding_percent === null || item.funding_percent === undefined
    ? "—"
    : `${formatNumber(item.funding_percent, 0)}%`;
  const remaining = crowdfundingTimeLabel(item.remaining_seconds);
  const status = crowdfundingStatusLabel(item);
  const score = item.top_score === null || item.top_score === undefined
    ? ""
    : ` · Top ${formatNumber(Number(item.top_score) * 100, 0)}`;
  return `
    <article class="crowdfunding-card">
      <a class="crowdfunding-cover" href="${escapeHtml(item.project_url || "#")}" target="_blank" rel="noopener noreferrer">
        ${item.image_url
          ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<span class="cover-initials">${escapeHtml(initials(item.title))}</span>`}
        <span class="crowdfunding-platform">${escapeHtml(platform === "kickstarter" ? "Kickstarter" : "Gamefound")}</span>
        <span class="crowdfunding-status ${item.status === "ending_soon" ? "is-ending" : ""}">${escapeHtml(status)}</span>
      </a>
      <div class="crowdfunding-card-body">
        <div>
          <p class="crowdfunding-creator">${escapeHtml(item.creator || "Creator non indicato")}</p>
          <h3>${escapeHtml(item.title)}</h3>
        </div>
        <p class="crowdfunding-description">${escapeHtml(item.description || "Nessuna descrizione disponibile.")}</p>
        <div class="crowdfunding-money-row">
          <div><span>Raccolto</span><strong>${escapeHtml(funds)}</strong></div>
          <div><span>Goal</span><strong>${escapeHtml(goal)}</strong></div>
          <div><span>Finanziato</span><strong>${escapeHtml(percent)}</strong></div>
        </div>
        <div class="crowdfunding-meta-row">
          <span><strong>${formatNumber(item.backer_count, 0)}</strong> backer</span>
          ${remaining ? `<span><strong>${escapeHtml(remaining)}</strong> rimasti</span>` : ""}
          <span class="crowdfunding-score">${escapeHtml(score.replace(/^ · /, ""))}</span>
        </div>
        <div class="crowdfunding-card-actions">
          <a class="button button-primary crowdfunding-open" href="${escapeHtml(item.project_url || "#")}" target="_blank" rel="noopener noreferrer">
            Apri campagna ${icon("external")}
          </a>
          <button class="button button-ghost wishlist-action ${wishlist ? "is-active" : ""}"
                  type="button"
                  data-wishlist-source-kind="crowdfunding"
                  data-wishlist-source-key="${escapeHtml(sourceKey)}"
                  data-wishlist-item-id="${escapeHtml(wishlist?.id || "")}"
                  data-wishlist-title="${escapeHtml(item.title || "")}"
                  data-wishlist-cover="${escapeHtml(item.image_url || "")}"
                  data-wishlist-target="${escapeHtml(item.project_url || "")}"
                  data-wishlist-platform="${escapeHtml(platform)}">
            ${wishlist ? `${icon("heart-fill")}<span>In Wishlist</span>` : `${icon("heart")}<span>Wishlist</span>`}
          </button>
        </div>
      </div>
    </article>
  `;
}

function crowdfundingProviderNotice(payload) {
  const gamefound = payload.providers?.gamefound || {};
  const kickstarter = payload.providers?.kickstarter || {};
  const notices = [];
  if (gamefound.status === "stale") {
    notices.push("Gamefound temporaneamente non aggiornabile: mostro gli ultimi dati disponibili.");
  } else if (gamefound.status === "error") {
    notices.push("Gamefound non è al momento disponibile.");
  }
  if (crowdfundingState.platform !== "gamefound") {
    if (kickstarter.status === "configuration_required") {
      notices.push(
        'Kickstarter non è configurato. <button class="button button-ghost" id="configureApifyFromCrowdfunding" type="button">Configura</button>'
      );
    } else if (kickstarter.status === "stale") {
      notices.push("Kickstarter temporaneamente non aggiornabile: mostro gli ultimi dati disponibili.");
    } else if (kickstarter.status === "error") {
      notices.push("Kickstarter non è al momento disponibile.");
    }
  }
  return notices.length
    ? `<div class="crowdfunding-source-note">${notices.map((text) => (
        text.includes('id="configureApifyFromCrowdfunding"')
          ? `<p>${text}</p>`
          : `<p>${escapeHtml(text)}</p>`
      )).join("")}</div>`
    : "";
}


const SUGGESTION_CATEGORIES = [
  ["for_you", "Per te", "I candidati più vicini ai gusti della tua ludoteca"],
  ["novelty", "Fuori dagli schemi", "Meccaniche che nella tua ludoteca mancano"],
  ["trending", "Di tendenza", "I titoli più seguiti in questo momento su BGG"],
  ["bgg", "I più amati", "Le valutazioni BGG più alte"],
  ["gems", "Gemme nascoste", "Votati molto bene, ma ancora poco conosciuti"],
  ["recent", "Novità", "Usciti negli ultimi anni"],
  ["light", "Partite veloci", "Leggeri e entro l'ora di gioco"],
  ["heavy", "Sfide impegnative", "Complessità BGG elevata"],
  ["duo", "In due", "Ideali in due giocatori"],
];
const SUGGESTION_COUNTS = ["5", "10", "20", "50"];
const SUGGESTION_PAGE = 10;

function suggestionSkeletons(count) {
  return Array.from({length: Math.max(1, Math.min(3, count))}, () => '<div class="skeleton suggestion-skeleton"></div>').join("");
}

// Player counts as in the game page: ideal, recommended and not recommended chips.
function suggestionPlayersMarkup(game, poll) {
  const rows = playerChartRows(game, poll);
  if (!rows.length || !rows.some((row) => row.verdict)) {
    return `<div><dt>Giocatori</dt><dd>${escapeHtml(playerText(game))}</dd></div>`;
  }
  return `
    <div class="suggestion-players">
      <dt>Giocatori</dt>
      <dd>
        <ol class="player-chart-counts">
          ${rows.map((row) => `
            <li class="player-chart-count is-${row.verdict || "unknown"}" title="${escapeHtml(`${row.label} giocatori: ${PLAYER_VERDICTS[row.verdict] || "nessun dato"}`)}">${escapeHtml(row.label)}</li>
          `).join("")}
        </ol>
      </dd>
    </div>
  `;
}

function suggestionCard(item, index, {proposedView = false} = {}) {
  const players = item.players || {};
  const playTime = item.play_time || {};
  const bgg = item.bgg || {};
  const overview = item.overview || {};
  const title = item.title || `BGG #${item.bgg_id}`;
  const game = {
    players: {min: players.min, max: players.max},
    play_time: {playing: playTime.playing, min: playTime.min, max: playTime.max},
  };
  const weight = Number(bgg.average_weight) > 0 ? formatNumber(bgg.average_weight, 2) : "—";
  const playerGame = {
    players: {min: players.min, max: players.max},
    bgg: {best_players: players.best, recommended_players: players.recommended},
  };
  const tags = [
    ...(Array.isArray(overview.setting) ? overview.setting : []),
    ...(Array.isArray(overview.mechanics) && overview.mechanics.length
      ? overview.mechanics
      : (Array.isArray(item.mechanics) ? item.mechanics.slice(0, 6) : [])),
  ];
  const overviewText = item.game_summary_it || overview.summary || "Descrizione non disponibile.";
  const whyText = item.why_it_fits || item.reason || "È un candidato verificato BGG non presente nella tua ludoteca.";
  const subtitle = [
    item.year_published || "",
    Number(bgg.rank) > 0 ? `#${formatNumber(bgg.rank, 0)} BGG` : "",
    item.hot_rank ? `Hotness BGG #${formatNumber(item.hot_rank, 0)}` : "",
  ].filter(Boolean).join(" · ");
  const actions = referenceActionButtons({
    bgg_id: item.bgg_id,
    name: title,
    year_published: item.year_published,
    image_url: item.cover_url || "",
    owned: false,
    in_catalog: false,
  });
  return `
    <article class="suggestion-card" data-suggestion-id="${Number(item.bgg_id)}">
      <div class="suggestion-side">
        <a class="suggestion-cover" href="/bgg/${Number(item.bgg_id)}" data-nav aria-label="Apri ${escapeHtml(title)}">
          <span class="card-corner"><span class="card-rank">#${index + 1}</span></span>
          ${item.cover_url
            ? `<img src="${escapeHtml(coverSrc(item.bgg_id, item.cover_url))}" alt="Cover di ${escapeHtml(title)}" loading="lazy" referrerpolicy="no-referrer">`
            : `<span class="cover-initials">${escapeHtml(initials(title))}</span>`}
          ${bggRatingBadge({average: Number(bgg.average) > 0 ? Number(bgg.average) : null, users_rated: bgg.users_rated})}
        </a>
        ${tags.length ? `<div class="suggestion-tags" aria-label="Generi e meccaniche">${tags.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="suggestion-body">
        <header class="suggestion-heading">
          <div class="suggestion-title">
            <h2><a href="/bgg/${Number(item.bgg_id)}" data-nav>${escapeHtml(title)}</a></h2>
            ${subtitle ? `<span class="muted">${escapeHtml(subtitle)}</span>` : ""}
          </div>
          <div class="suggestion-heading-actions">
            ${proposedView ? `
              <button class="button button-ghost suggestion-restore" type="button" data-suggestion-restore="${Number(item.bgg_id)}">
                ${icon("refresh")}<span>Ripristina</span>
              </button>
            ` : ""}
            <a class="suggestion-bgg-link" href="https://boardgamegeek.com/boardgame/${Number(item.bgg_id)}"
               target="_blank" rel="noopener noreferrer" aria-label="Apri ${escapeHtml(title)} su BoardGameGeek" title="Apri su BoardGameGeek">
              <span class="suggestion-bgg-mark">BGG</span><span aria-hidden="true">${icon("external")}</span>
            </a>
            ${actions}
          </div>
        </header>
        <dl class="suggestion-facts-row">
          ${suggestionPlayersMarkup(playerGame, players.poll)}
          <div><dt>Età</dt><dd>${escapeHtml(ageText({bgg: {recommended_age: item.age}}))}</dd></div>
          <div><dt>Durata</dt><dd>${escapeHtml(timeText(game))}</dd></div>
          <div><dt>Complessità</dt><dd>${weight === "—" ? "—" : `${weight} / 5`}</dd></div>
          <div><dt>Lingua</dt><dd title="${escapeHtml(item.language_dependence || "")}">${escapeHtml(languageDependenceText(item.language_dependence))}</dd></div>
        </dl>
        <div class="suggestion-editorial">
          <section class="suggestion-copy-block">
            <h3>Il gioco</h3>
            <p>${escapeHtml(overviewText)}</p>
          </section>
          <section class="suggestion-copy-block suggestion-why">
            <h3>Potrebbe piacerti perché</h3>
            <p>${escapeHtml(whyText)}</p>
          </section>
        </div>
      </div>
    </article>
  `;
}

function suggestionsSummaryText(payload) {
  const parts = [];
  const candidates = Number(payload.candidate_count) || 0;
  if (candidates) parts.push(`${formatNumber(candidates, 0)} candidati non posseduti`);
  if (payload.generated_at) {
    const date = new Date(payload.generated_at);
    if (!Number.isNaN(date.getTime())) {
      parts.push(`analisi del ${date.toLocaleDateString("it-IT", {day: "numeric", month: "short"})}`);
    }
  }
  if (payload.cache_state === "stale") parts.push("BGG non raggiungibile: ultimi dati disponibili");
  return parts.join(" · ");
}

let suggestionsLoadToken = 0;

async function renderSuggestions({forceRefresh = false} = {}) {
  document.title = "Suggerimenti · BoardGameCompanion";
  const proposedView = suggestionsState.view === "proposed";
  const category = SUGGESTION_CATEGORIES.find(([key]) => key === suggestionsState.sort) || SUGGESTION_CATEGORIES[0];
  app.innerHTML = `
    <section class="page-header catalog-page-header suggestions-header">
      <div class="page-header-copy">
        <h1>Suggerimenti</h1>
        <p class="muted catalog-page-summary rankings-page-summary">
          <span>Scopri giochi in linea con i tuoi gusti e amplia la tua ludoteca</span>
          <span aria-hidden="true">·</span>
          <span id="suggestionsSummary" aria-live="polite">Analisi del profilo e dei candidati BGG…</span>
        </p>
      </div>
      <div class="catalog-stats catalog-sort-pills" role="group" aria-label="Suggerimenti da mostrare">
        <button type="button" class="stat ${proposedView ? "" : "is-active"}" data-suggestions-view="new" aria-pressed="${!proposedView}">
          <strong id="suggestionsNewCount">—</strong><span>Da scoprire</span>
        </button>
        <button type="button" class="stat ${proposedView ? "is-active" : ""}" data-suggestions-view="proposed" aria-pressed="${proposedView}">
          <strong id="suggestionsProposedCount">—</strong><span>Già proposti</span>
        </button>
      </div>
    </section>

    <section class="catalog-workspace suggestions-workspace" aria-label="Suggerimenti">
      <div class="suggestion-categories" role="group" aria-label="Categoria">
        ${SUGGESTION_CATEGORIES.map(([key, label, hint]) => `
          <button type="button" class="suggestion-category ${key === category[0] ? "is-active" : ""}" data-suggestions-sort="${key}"
                  aria-pressed="${key === category[0]}" title="${escapeHtml(hint)}">
            <span>${escapeHtml(label)}</span><small data-suggestions-category-count="${key}"></small>
          </button>
        `).join("")}
      </div>
      <div class="toolbar suggestions-toolbar">
        <div class="suggestions-profile" id="suggestionsProfile"></div>
        <label class="catalog-density-field">
          <span class="catalog-density-label">Mostra</span>
          <select id="suggestionsCount" aria-label="Numero di suggerimenti">
            ${SUGGESTION_COUNTS.map((value) => `<option value="${value}" ${suggestionsState.count === value ? "selected" : ""}>${value}</option>`).join("")}
          </select>
        </label>
        ${proposedView
          ? `<button class="button button-ghost" id="suggestionsRestoreAll" type="button">${icon("refresh")}<span>Ripristina tutti</span></button>`
          : `<button class="button button-primary" id="suggestionsAlternatives" type="button" title="Metti da parte questi titoli e proponine altri">${icon("sparkle")}<span>Proponi altri</span></button>`}
        <button class="button button-ghost icon-only" id="suggestionsRefresh" type="button"
                aria-label="Aggiorna i candidati da BGG" title="Aggiorna i candidati da BGG">${icon("refresh")}</button>
      </div>
      <div id="suggestionsGrid" class="suggestions-grid" aria-live="polite">
        ${suggestionSkeletons(Number(suggestionsState.count) || 10)}
      </div>
    </section>
  `;

  document.querySelector("#suggestionsRefresh")?.addEventListener("click", () => {
    void renderSuggestions({forceRefresh: true});
  });
  document.querySelectorAll("[data-suggestions-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      suggestionsState.sort = button.dataset.suggestionsSort || "for_you";
      void renderSuggestions();
    });
  });
  document.querySelectorAll("[data-suggestions-view]").forEach((button) => {
    button.addEventListener("click", () => {
      suggestionsState.view = button.dataset.suggestionsView === "proposed" ? "proposed" : "new";
      void renderSuggestions();
    });
  });
  document.querySelector("#suggestionsCount")?.addEventListener("change", (event) => {
    suggestionsState.count = SUGGESTION_COUNTS.includes(event.target.value) ? event.target.value : "10";
    window.localStorage.setItem("bgc.suggestionsCount", suggestionsState.count);
    void renderSuggestions();
  });
  document.querySelector("#suggestionsAlternatives")?.addEventListener("click", async (event) => {
    const ids = [...document.querySelectorAll("#suggestionsGrid [data-suggestion-id]")]
      .map((card) => Number(card.dataset.suggestionId))
      .filter(Boolean);
    if (!ids.length) return;
    event.currentTarget.disabled = true;
    try {
      await api("/api/catalog/suggestions/proposed", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({bgg_ids: ids, sort: suggestionsState.sort}),
      });
      showToast(`${ids.length} titoli spostati in “Già proposti”: puoi ripristinarli quando vuoi.`);
      await renderSuggestions();
    } catch (error) {
      event.currentTarget.disabled = false;
      showToast(error.message, true);
    }
  });
  document.querySelector("#suggestionsRestoreAll")?.addEventListener("click", async () => {
    try {
      const result = await api("/api/catalog/suggestions/proposed/restore", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({}),
      });
      showToast(`${formatNumber(result.restored || 0, 0)} titoli ripristinati.`);
      suggestionsState.view = "new";
      await renderSuggestions();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  const token = ++suggestionsLoadToken;
  const grid = document.querySelector("#suggestionsGrid");
  const summary = document.querySelector("#suggestionsSummary");
  const wanted = Number(suggestionsState.count) || 10;
  const fetchPage = (offset, refresh) => {
    const params = new URLSearchParams({
      limit: String(Math.min(SUGGESTION_PAGE, wanted - offset)),
      offset: String(offset),
      sort: category[0],
      view: suggestionsState.view,
    });
    if (refresh) params.set("refresh", "true");
    return api(`/api/catalog/suggestions?${params.toString()}`);
  };
  const bindCards = (root) => {
    bindWishlistActions(root);
    bindReferenceActions(root);
    root.querySelectorAll("[data-suggestion-restore]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await api("/api/catalog/suggestions/proposed/restore", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bgg_ids: [Number(button.dataset.suggestionRestore)]}),
          });
          showToast("Titolo ripristinato tra i suggerimenti.");
          await renderSuggestions();
        } catch (error) {
          button.disabled = false;
          showToast(error.message, true);
        }
      });
    });
  };

  try {
    const [payload] = await Promise.all([
      fetchPage(0, forceRefresh),
      refreshWishlistIndex().catch(() => null),
    ]);
    if (token !== suggestionsLoadToken) return;
    const counts = payload.category_counts || {};
    document.querySelector("#suggestionsNewCount").textContent = formatNumber(counts.for_you || 0, 0);
    document.querySelector("#suggestionsProposedCount").textContent = formatNumber(payload.proposed_count || 0, 0);
    document.querySelectorAll("[data-suggestions-category-count]").forEach((node) => {
      node.textContent = formatNumber(counts[node.dataset.suggestionsCategoryCount] || 0, 0);
    });
    summary.textContent = suggestionsSummaryText(payload);
    const topMechanics = Array.isArray(payload.profile?.top_mechanics)
      ? payload.profile.top_mechanics.slice(0, 3).map((entry) => entry?.[0]).filter(Boolean)
      : [];
    const profile = document.querySelector("#suggestionsProfile");
    profile.innerHTML = topMechanics.length
      ? `<span class="suggestions-profile-label">Il tuo profilo</span>${topMechanics.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}`
      : "";

    const total = Math.min(wanted, Number(payload.total_available) || 0);
    let items = Array.isArray(payload.items) ? payload.items : [];
    if (!items.length) {
      grid.innerHTML = proposedView
        ? '<div class="empty-state"><strong>Nessun titolo messo da parte</strong><p class="muted">Con “Proponi altri” i suggerimenti mostrati finiscono qui e si possono ripristinare.</p></div>'
        : (payload.proposed_count
          ? '<div class="empty-state"><strong>Hai visto tutti i candidati di questa categoria</strong><p class="muted">Ripristina i titoli in “Già proposti” o scegli un’altra categoria.</p></div>'
          : '<div class="empty-state"><strong>Nessun candidato disponibile</strong><p class="muted">Riprova con Aggiorna o verifica il token BGG nelle Impostazioni.</p></div>');
      const button = document.querySelector("#suggestionsAlternatives");
      if (button) button.disabled = true;
      return;
    }
    grid.innerHTML = items.map((item, index) => suggestionCard(item, index, {proposedView})).join("")
      + (total > items.length ? suggestionSkeletons(total - items.length) : "");
    bindCards(grid);
    // Further pages arrive in small batches, so long lists show up progressively.
    for (let offset = items.length; offset < total; offset += SUGGESTION_PAGE) {
      const page = await fetchPage(offset, false);
      if (token !== suggestionsLoadToken) return;
      const pageItems = Array.isArray(page.items) ? page.items : [];
      if (!pageItems.length) break;
      const fragment = document.createElement("div");
      fragment.innerHTML = pageItems.map((item, index) => suggestionCard(item, items.length + index, {proposedView})).join("");
      bindCards(fragment);
      grid.querySelectorAll(".skeleton").forEach((node) => node.remove());
      grid.append(...fragment.children);
      items = items.concat(pageItems);
      if (offset + SUGGESTION_PAGE < total) grid.insertAdjacentHTML("beforeend", suggestionSkeletons(total - offset - SUGGESTION_PAGE));
    }
    grid.querySelectorAll(".skeleton").forEach((node) => node.remove());
  } catch (error) {
    if (token !== suggestionsLoadToken) return;
    grid.innerHTML = `<div class="empty-state"><strong>Impossibile generare i suggerimenti</strong><p class="muted">${escapeHtml(error.message)}</p></div>`;
  }
}

const bggCatalogSorts = [
  ["rank", "Classifica BGG"],
  ["votes", "Più votati"],
  ["rating", "Voto medio"],
  ["newest", "Più recenti"],
  ["title", "Titolo"],
];
const bggCatalogPageSizes = ["20", "50", "100", "200"];
const storedBggCatalogPageSize = window.localStorage.getItem("bgc.bggCatalogPageSize");
const bggCatalogState = {
  q: "",
  sort: "rank",
  itemType: "",
  offset: 0,
  total: 0,
  pageSize: bggCatalogPageSizes.includes(storedBggCatalogPageSize) ? storedBggCatalogPageSize : "50",
};
let bggCatalogRequestController;
let bggCatalogSearchTimer;
let currentBggCatalogItems = null;

function bindBggCatalogCards(root) {
  bindWishlistActions(root);
  bindReferenceActions(root);
}

function renderBggCatalogItems() {
  const grid = document.querySelector("#bggCatalogGrid");
  if (!grid || !currentBggCatalogItems) return;
  const listView = state.catalogView === "list";
  grid.className = `catalog-results bgg-catalog-results ${listView ? "catalog-results-list" : `catalog-results-cards catalog-columns-${state.cardsPerRow}`}`;
  if (!currentBggCatalogItems.length) {
    grid.innerHTML = bggCatalogState.q
      ? '<div class="empty catalog-empty">Nessun gioco trovato. Prova con il titolo originale o con meno parole.</div>'
      : '<div class="empty catalog-empty">Catalogo BGG vuoto: copia il dump <code>boardgames_ranks.csv</code> nella cartella di import, viene importato automaticamente. Soglie e stato sono nelle Impostazioni.</div>';
    return;
  }
  const rows = currentBggCatalogItems.map((item) => [referenceAsGame(item), item]);
  grid.innerHTML = listView
    ? `
      <div class="catalog-list-head">
        <span>Gioco</span><span>Giocatori</span><span>Età</span><span>Durata</span><span>Peso</span><span>BGG</span><span aria-hidden="true"></span>
      </div>
      ${rows.map(([game, item]) => gameListRow(game, [], false, {reference: item})).join("")}
    `
    : rows.map(([game, item]) => gameCard(game, [], {reference: item})).join("");
  bindBggCatalogCards(grid);
}

function renderBggCatalogPagination() {
  const container = document.querySelector("#bggCatalogPagination");
  if (!container) return;
  const limit = Number(bggCatalogState.pageSize);
  const page = Math.floor(bggCatalogState.offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(bggCatalogState.total / limit));
  container.hidden = pages <= 1;
  if (pages <= 1) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `
    <button class="button button-ghost" type="button" data-bgg-catalog-page="-1" ${page <= 1 ? "disabled" : ""}>← Precedente</button>
    <span class="muted">Pagina ${formatNumber(page, 0)} di ${formatNumber(pages, 0)} · ${limit} per pagina</span>
    <button class="button button-ghost" type="button" data-bgg-catalog-page="1" ${page >= pages ? "disabled" : ""}>Successiva →</button>
  `;
  container.querySelectorAll("[data-bgg-catalog-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const step = Number(button.dataset.bggCatalogPage);
      bggCatalogState.offset = Math.max(0, bggCatalogState.offset + step * limit);
      void loadBggCatalog();
      window.scrollTo({top: 0, behavior: "smooth"});
    });
  });
}

async function loadBggCatalog() {
  const grid = document.querySelector("#bggCatalogGrid");
  const summary = document.querySelector("#bggCatalogSummary");
  if (!grid || !summary) return;
  bggCatalogRequestController?.abort();
  const controller = new AbortController();
  bggCatalogRequestController = controller;
  grid.innerHTML = skeletons();
  try {
    const params = new URLSearchParams({
      sort: bggCatalogState.sort,
      limit: bggCatalogState.pageSize,
      offset: String(bggCatalogState.offset),
    });
    if (bggCatalogState.q) params.set("q", bggCatalogState.q);
    if (bggCatalogState.itemType) params.set("item_type", bggCatalogState.itemType);
    const [payload] = await Promise.all([
      api(`/api/reference/browse?${params}`, {signal: controller.signal}),
      refreshWishlistIndex().catch(() => null),
    ]);
    if (controller.signal.aborted || !grid.isConnected) return;
    currentBggCatalogItems = Array.isArray(payload.items) ? payload.items : [];
    bggCatalogState.total = Number(payload.total) || 0;
    const totalText = `${formatNumber(bggCatalogState.total, 0)} ${bggCatalogState.total === 1 ? "gioco" : "giochi"}`;
    summary.textContent = bggCatalogState.q
      ? `${totalText} per “${bggCatalogState.q}”`
      : `${totalText} nel catalogo BGG`;
    renderBggCatalogItems();
    renderBggCatalogPagination();
  } catch (error) {
    if (error.name === "AbortError") return;
    grid.innerHTML = `<div class="empty catalog-empty">Catalogo non disponibile: ${escapeHtml(error.message)}</div>`;
    showToast(error.message, true);
  } finally {
    if (bggCatalogRequestController === controller) bggCatalogRequestController = undefined;
  }
}

async function renderBggCatalog() {
  document.title = "Catalogo · BoardGameCompanion";
  currentBggCatalogItems = null;
  const cardsView = state.catalogView === "cards";
  app.innerHTML = `
    <section class="page-header catalog-page-header">
      <div class="page-header-copy">
        <h1>Catalogo</h1>
        <p class="muted catalog-page-summary rankings-page-summary">
          <span>Sfoglia i giochi su BoardGameGeek e trova il prossimo da aggiungere alla tua ludoteca</span>
          <span aria-hidden="true">·</span>
          <span id="bggCatalogSummary" aria-live="polite">Caricamento…</span>
        </p>
      </div>
      <div class="catalog-stats catalog-sort-pills" role="group" aria-label="Ordina catalogo">
        ${bggCatalogSorts.map(([value, label]) => `<button type="button" class="stat ${bggCatalogState.sort === value ? "is-active" : ""}" data-bgg-catalog-sort="${value}" aria-pressed="${bggCatalogState.sort === value}"><span>${label}</span></button>`).join("")}
      </div>
    </section>

    <section class="catalog-workspace" aria-label="Catalogo BGG">
      <section class="toolbar catalog-simple-search" aria-label="Ricerca catalogo">
        <label class="field search-field">
          <input id="bggCatalogQuery" type="search" autocomplete="off" enterkeyhint="search" maxlength="200"
                 placeholder="Cerca un gioco…" aria-label="Cerca nel catalogo BoardGameGeek"
                 value="${escapeHtml(bggCatalogState.q)}">
        </label>
        <label class="field catalog-type-field">
          <select id="bggCatalogType" aria-label="Tipo">
            <option value="">Tutti i tipi</option>
            <option value="standalone" ${bggCatalogState.itemType === "standalone" ? "selected" : ""}>Giochi base</option>
            <option value="expansion" ${bggCatalogState.itemType === "expansion" ? "selected" : ""}>Espansioni</option>
          </select>
        </label>
        <div class="catalog-view-switch catalog-filter-view" aria-label="Vista catalogo">
          <button class="view-switch-button ${cardsView ? "is-active" : ""}" id="bggCardViewButton" type="button"
                  aria-label="Card" title="Card" aria-pressed="${cardsView}">${icon("catalog")}</button>
          <button class="view-switch-button ${cardsView ? "" : "is-active"}" id="bggListViewButton" type="button"
                  aria-label="Lista" title="Lista" aria-pressed="${!cardsView}">${icon("list")}</button>
        </div>
        <div class="catalog-density-fields">
          <label class="catalog-density-field" id="bggCardsPerRowField" ${cardsView ? "" : "hidden"}>
            <span class="catalog-density-label">Righe</span>
            <select id="bggCardsPerRow" aria-label="Card per riga">
              ${[3, 4, 5].map((value) => `<option value="${value}" ${state.cardsPerRow === value ? "selected" : ""}>${value}</option>`).join("")}
            </select>
          </label>
          <label class="catalog-density-field">
            <span class="catalog-density-label">Pagina</span>
            <select id="bggCatalogPageSize" aria-label="Titoli per pagina">
              ${bggCatalogPageSizes.map((value) => `<option value="${value}" ${bggCatalogState.pageSize === value ? "selected" : ""}>${value}</option>`).join("")}
            </select>
          </label>
        </div>
      </section>
      <section class="catalog-results catalog-results-cards catalog-columns-${state.cardsPerRow}" id="bggCatalogGrid"></section>
      <nav class="pagination" id="bggCatalogPagination" aria-label="Paginazione" hidden></nav>
    </section>
  `;
  const reload = () => {
    bggCatalogState.offset = 0;
    void loadBggCatalog();
  };
  const input = document.querySelector("#bggCatalogQuery");
  input?.addEventListener("input", () => {
    window.clearTimeout(bggCatalogSearchTimer);
    bggCatalogSearchTimer = window.setTimeout(() => {
      const value = String(input.value || "").trim();
      if (value === bggCatalogState.q) return;
      bggCatalogState.q = value;
      reload();
    }, 300);
  });
  document.querySelector("#bggCatalogType")?.addEventListener("change", (event) => {
    bggCatalogState.itemType = event.target.value;
    reload();
  });
  document.querySelectorAll("[data-bgg-catalog-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      bggCatalogState.sort = button.dataset.bggCatalogSort || "rank";
      document.querySelectorAll("[data-bgg-catalog-sort]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      reload();
    });
  });
  const setView = (view) => {
    if (state.catalogView === view) return;
    state.catalogView = view;
    window.localStorage.setItem("bgc.catalogView", view);
    const cards = view === "cards";
    for (const [id, active] of [["#bggCardViewButton", cards], ["#bggListViewButton", !cards]]) {
      const button = document.querySelector(id);
      button?.classList.toggle("is-active", active);
      button?.setAttribute("aria-pressed", String(active));
    }
    const field = document.querySelector("#bggCardsPerRowField");
    if (field) field.hidden = !cards;
    renderBggCatalogItems();
  };
  document.querySelector("#bggCardViewButton")?.addEventListener("click", () => setView("cards"));
  document.querySelector("#bggListViewButton")?.addEventListener("click", () => setView("list"));
  document.querySelector("#bggCardsPerRow")?.addEventListener("change", (event) => {
    const value = Number(event.target.value);
    if (![3, 4, 5].includes(value)) return;
    state.cardsPerRow = value;
    window.localStorage.setItem("bgc.catalogColumns", String(value));
    renderBggCatalogItems();
  });
  document.querySelector("#bggCatalogPageSize")?.addEventListener("change", (event) => {
    if (!bggCatalogPageSizes.includes(event.target.value)) return;
    bggCatalogState.pageSize = event.target.value;
    window.localStorage.setItem("bgc.bggCatalogPageSize", event.target.value);
    reload();
  });
  await loadBggCatalog();
}

async function renderCrowdfunding({forceRefresh = false} = {}) {
  document.title = "Crowdfunding · BoardGameCompanion";
  const sortOptions = [
    ["top", "Top"],
    ["funds", "Più finanziati"],
    ["backers", "Più backer"],
    ["ending", "In scadenza"],
    ["upcoming", "Upcoming"],
  ];
  const platformOptions = [
    ["all", "Tutti"],
    ["gamefound", "Gamefound"],
    ["kickstarter", "Kickstarter"],
  ];
  app.innerHTML = `
    <section class="crowdfunding-page">
      <header class="page-header browse-header crowdfunding-header">
        <div class="page-header-copy">
          <h1>Crowdfunding</h1>
          <p class="muted catalog-page-summary">Scopri i giochi da tavolo in campagna su Kickstarter e Gamefound</p>
        </div>
        <button class="button button-ghost" id="crowdfundingRefresh" type="button">${icon("refresh")}<span>Aggiorna</span></button>
      </header>
      <div class="crowdfunding-toolbar">
        <div class="suggestion-categories" role="group" aria-label="Classifica">
          ${sortOptions.map(([value, label]) => `<button type="button" class="suggestion-category ${crowdfundingState.sort === value ? "is-active" : ""}" data-crowdfunding-sort="${value}">${label}</button>`).join("")}
        </div>
        <div class="suggestion-categories crowdfunding-platform-filter" role="group" aria-label="Piattaforma">
          ${platformOptions.map(([value, label]) => `<button type="button" class="suggestion-category ${crowdfundingState.platform === value ? "is-active" : ""}" data-crowdfunding-platform="${value}">${label}</button>`).join("")}
        </div>
      </div>
      <div id="crowdfundingSummary" class="crowdfunding-summary"></div>
      <div id="crowdfundingGrid" class="crowdfunding-grid" aria-live="polite">
        ${skeletons()}
      </div>
    </section>
  `;

  const grid = document.querySelector("#crowdfundingGrid");
  const summary = document.querySelector("#crowdfundingSummary");
  const refreshButton = document.querySelector("#crowdfundingRefresh");

  document.querySelectorAll("[data-crowdfunding-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      crowdfundingState.sort = button.dataset.crowdfundingSort;
      void renderCrowdfunding();
    });
  });
  document.querySelectorAll("[data-crowdfunding-platform]").forEach((button) => {
    button.addEventListener("click", () => {
      crowdfundingState.platform = button.dataset.crowdfundingPlatform;
      void renderCrowdfunding();
    });
  });
  refreshButton?.addEventListener("click", () => void renderCrowdfunding({forceRefresh: true}));

  try {
    const status = crowdfundingState.sort === "upcoming" ? "upcoming" : "active";
    const params = new URLSearchParams({
      sort: crowdfundingState.sort,
      platform: crowdfundingState.platform,
      status,
      limit: "60",
    });
    if (forceRefresh) params.set("refresh", "true");
    const [payload] = await Promise.all([
      api(`/api/crowdfunding?${params.toString()}`),
      refreshWishlistIndex().catch(() => null),
    ]);
    const items = Array.isArray(payload.items) ? payload.items : [];
    const rankingText = payload.ranking?.[crowdfundingState.sort];
    summary.innerHTML = `
      <div>
        <strong>${formatNumber(payload.total_matching || 0, 0)} progetti</strong>
        <span class="muted">${rankingText ? escapeHtml(rankingText) : "Dati aggiornati dalla cache locale."}</span>
      </div>
    ` + crowdfundingProviderNotice(payload);

    document.querySelector("#configureApifyFromCrowdfunding")?.addEventListener("click", () => {
      void openSettingsDialog("crowdfunding");
    });

    if (!items.length) {
      const gamefoundOnlyUpcoming = crowdfundingState.sort === "upcoming"
        && crowdfundingState.platform === "gamefound"
        && payload.providers?.gamefound?.supports_upcoming === false;
      const kickstarterNeedsConfig = crowdfundingState.sort === "upcoming"
        && crowdfundingState.platform !== "gamefound"
        && payload.providers?.kickstarter?.status === "configuration_required";
      grid.innerHTML = `
        <div class="empty-state crowdfunding-empty">
          <strong>${gamefoundOnlyUpcoming
            ? "Upcoming non esposti dalla Public API Gamefound"
            : kickstarterNeedsConfig
              ? "Configura Kickstarter/Apify per gli upcoming"
              : "Nessun progetto disponibile"}</strong>
          <p class="muted">${gamefoundOnlyUpcoming
            ? "La Public API documentata di Gamefound espone al momento solo le campagne attive."
            : kickstarterNeedsConfig
              ? "Configura Kickstarter nelle Impostazioni per visualizzare anche le campagne upcoming."
              : "Prova un’altra piattaforma o classifica."}</p>
          ${kickstarterNeedsConfig
            ? '<button class="button button-primary" id="configureApifyFromEmpty" type="button">Configura Kickstarter</button>'
            : ""}
        </div>
      `;
      document.querySelector("#configureApifyFromEmpty")?.addEventListener("click", () => {
        void openSettingsDialog("crowdfunding");
      });
      return;
    }
    grid.innerHTML = items.map(crowdfundingCard).join("");
    bindWishlistActions(grid);
  } catch (error) {
    grid.innerHTML = `<div class="empty-state crowdfunding-empty"><strong>Impossibile caricare il crowdfunding</strong><p class="muted">${escapeHtml(error.message)}</p></div>`;
  }
}

function wishlistFactsMarkup(item) {
  const meta = item.metadata || {};
  if (item.source_kind !== "bgg") {
    return meta.platform ? `<p class="muted">Piattaforma: ${escapeHtml(meta.platform)}</p>` : "";
  }
  const players = meta.players || {};
  const playersText = players.min && players.max
    ? (players.min === players.max ? `${players.min}` : `${players.min}–${players.max}`)
    : "—";
  const timeText = meta.playing_time ? `${meta.playing_time} min` : "—";
  const weightText = Number.isFinite(Number(meta.weight)) ? Number(meta.weight).toFixed(1) : "—";
  const ratingText = Number.isFinite(Number(meta.bgg_rating)) ? Number(meta.bgg_rating).toFixed(1) : "—";
  return `
    <dl class="wishlist-facts">
      <div><dt>Giocatori</dt><dd>${escapeHtml(playersText)}</dd></div>
      <div><dt>Durata</dt><dd>${escapeHtml(timeText)}</dd></div>
      <div><dt>Peso</dt><dd>${escapeHtml(weightText)}</dd></div>
      <div><dt>BGG</dt><dd>${escapeHtml(ratingText)}</dd></div>
    </dl>`;
}

const euroFormat = new Intl.NumberFormat("it-IT", {style: "currency", currency: "EUR"});

function wishlistPriceMarkup(item) {
  const prices = item.metadata?.prices;
  const checked = prices?.checked_at
    ? new Date(prices.checked_at).toLocaleDateString("it-IT")
    : "";
  let summary = "";
  if (prices?.best) {
    const best = prices.best;
    const others = (prices.offers || []).map((offer) => `
      <li>
        <a href="${escapeHtml(safeExternalHref(offer.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(offer.shop)}</a>
        <span>${escapeHtml(euroFormat.format(offer.price_eur))}${offer.availability === "out_of_stock" ? " · esaurito" : ""}</span>
      </li>`).join("");
    summary = `
      <div class="wishlist-price-best">
        <span class="wishlist-price-label">Miglior prezzo in Italia</span>
        <a class="wishlist-price-value" href="${escapeHtml(safeExternalHref(best.url))}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(euroFormat.format(best.price_eur))} <small>${escapeHtml(best.shop)}</small>
        </a>
      </div>
      <details class="wishlist-offers">
        <summary>Tutte le offerte (${(prices.offers || []).length})</summary>
        <ul>${others}</ul>
      </details>
      <small class="muted">Prezzo indicativo da ricerca web, aggiornato il ${escapeHtml(checked)}. Verifica sul sito.</small>`;
  } else if (prices) {
    summary = `<small class="muted">Nessun prezzo verificato trovato il ${escapeHtml(checked)}.</small>`;
  }
  return `
    <div class="wishlist-price">
      ${summary}
      <button class="button button-ghost" type="button" data-wishlist-price-refresh="${escapeHtml(item.id)}">
        ${icon("refresh")}<span>${prices ? "Aggiorna prezzi" : "Cerca prezzi"}</span>
      </button>
    </div>`;
}

function bindWishlistPriceActions(root) {
  root.querySelectorAll("[data-wishlist-price-refresh]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.querySelector("span").textContent = "Cerco…";
      try {
        await api(`/api/wishlist/${encodeURIComponent(button.dataset.wishlistPriceRefresh)}/prices`, {method: "POST"});
        await renderWishlist();
      } catch (error) {
        showToast(error.message, true);
        button.disabled = false;
        button.querySelector("span").textContent = "Cerca prezzi";
      }
    });
  });
}

function shopLinksMarkup(title) {
  const query = `${title} gioco da tavolo`;
  const shops = [
    ["Amazon.it", `https://www.amazon.it/s?k=${encodeURIComponent(query)}`],
    ["eBay.it", `https://www.ebay.it/sch/i.html?_nkw=${encodeURIComponent(query)}`],
    ["Google.it", `https://www.google.it/search?q=${encodeURIComponent(`${query} prezzo`)}`],
  ];
  return `
    <nav class="wishlist-shops" aria-label="Cerca prezzi in Italia per ${escapeHtml(title)}">
      <span class="wishlist-shops-label">Cerca manualmente</span>
      ${shops.map(([label, href]) => `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`).join("")}
    </nav>`;
}

async function renderWishlist() {
  document.title = "Wishlist · BoardGameCompanion";
  app.innerHTML = `
    <section class="page-header browse-header">
      <div>
        <h1>Wishlist</h1>
        <p class="muted catalog-page-summary">Ritrova i giochi che hai salvato per valutarli o acquistarli in seguito</p>
      </div>
    </section>
    <section class="wishlist-grid" id="wishlistGrid">${skeletons()}</section>
  `;
  const grid = document.querySelector("#wishlistGrid");
  try {
    const payload = await refreshWishlistIndex();
    const items = payload.items || [];
    grid.innerHTML = items.length
      ? items.map((item) => {
          const isCrowdfunding = item.source_kind === "crowdfunding";
          const sourceLabel = isCrowdfunding ? "Crowdfunding" : "BoardGameGeek";
          const target = safeExternalHref(
            item.target_url || (item.bgg_id ? `https://boardgamegeek.com/boardgame/${item.bgg_id}` : ""),
          );
          return `
            <article class="wishlist-card">
              <a class="wishlist-cover" href="${escapeHtml(target)}" target="_blank" rel="noopener noreferrer">
                ${item.cover_url
                  ? `<img src="${escapeHtml(coverSrc(item.bgg_id, item.cover_url))}" alt="Cover di ${escapeHtml(item.title)}" loading="lazy" referrerpolicy="no-referrer">`
                  : `<span class="cover-initials">${escapeHtml(initials(item.title))}</span>`}
              </a>
              <div class="wishlist-card-body">
                <p class="eyebrow">${escapeHtml(sourceLabel)}</p>
                <h2>${escapeHtml(item.title)}</h2>
                <p class="muted">${item.year_published || "Anno non disponibile"}</p>
                ${wishlistFactsMarkup(item)}
                ${wishlistPriceMarkup(item)}
                ${shopLinksMarkup(item.title)}
                <div class="wishlist-card-actions">
                  <a class="button button-primary" href="${escapeHtml(target)}" target="_blank" rel="noopener noreferrer">${isCrowdfunding ? "Apri progetto" : "Scheda BGG"} ${icon("external")}</a>
                  <button class="button button-ghost wishlist-action is-active"
                          type="button"
                          data-wishlist-source-kind="${escapeHtml(item.source_kind)}"
                          data-wishlist-source-key="${escapeHtml(item.source_key)}"
                          data-wishlist-item-id="${escapeHtml(item.id)}"
                          data-wishlist-title="${escapeHtml(item.title)}">
                    ${icon("heart-fill")}<span>In Wishlist</span>
                  </button>
                </div>
              </div>
            </article>
          `;
        }).join("")
      : '<div class="empty"><strong>Wishlist vuota.</strong><span>Aggiungi titoli da Suggerimenti o Crowdfunding.</span></div>';
    bindWishlistActions(grid);
    bindWishlistPriceActions(grid);
    const focus = new URLSearchParams(window.location.search).get("focus");
    if (focus) {
      const card = Array.from(grid.querySelectorAll(".wishlist-card")).find((item) => {
        const button = item.querySelector("[data-wishlist-item-id]");
        return button?.dataset.wishlistItemId === focus;
      });
      if (card) {
        card.classList.add("is-highlighted");
        card.scrollIntoView({behavior: "smooth", block: "center"});
      }
    }
  } catch (error) {
    grid.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function smartListFilterSummary(filters = {}) {
  const labels = [];
  if (filters.supports_players) labels.push(`${filters.supports_players} giocatori`);
  if (filters.ideal_players) labels.push(`ideale in ${filters.ideal_players}`);
  if (filters.recommended_players) labels.push(`raccomandato in ${filters.recommended_players}`);
  if (filters.max_minutes) labels.push(`≤ ${filters.max_minutes} min`);
  if (filters.weight) labels.push(String(filters.weight));
  if (filters.personal_rating_min) labels.push(`tu ≥ ${filters.personal_rating_min}★`);
  if (filters.played === true) labels.push("giocati");
  if (filters.played === false) labels.push("mai giocati");
  if (filters.category) labels.push(String(filters.category));
  if (filters.mechanic) labels.push(String(filters.mechanic));
  return labels.length ? labels.join(" · ") : "Tutta la ludoteca";
}

async function renderLists() {
  document.title = "Raccolte · BoardGameCompanion";
  app.innerHTML = `
    <section class="page-header browse-header lists-header">
      <div>
        <h1>Raccolte</h1>
        <p class="muted catalog-page-summary">Crea raccolte manuali o dinamiche per organizzare i giochi secondo i tuoi criteri</p>
      </div>
    </section>
    <section class="list-builder-card">
      <form id="createGameListForm">
        <div class="list-builder-head">
          <label><span>Nome lista</span><input id="gameListName" type="text" maxlength="200" required placeholder="Es. Brevi in 2"></label>
          <label><span>Tipo</span>
            <select id="gameListKind">
              <option value="smart">Dinamica</option>
              <option value="manual">Manuale</option>
            </select>
          </label>
          <button class="button button-primary" type="submit">Crea lista</button>
        </div>
        <div class="list-builder-filters" id="smartListFields">
          <label><span>Giocatori</span><input id="listSupportsPlayers" type="number" min="1" max="30"></label>
          <label><span>Ideale in</span><input id="listIdealPlayers" type="number" min="1" max="30"></label>
          <label><span>Raccomandato in</span><input id="listRecommendedPlayers" type="number" min="1" max="30"></label>
          <label><span>Max minuti</span><input id="listMaxMinutes" type="number" min="1" max="1440"></label>
          <label><span>Complessità</span>
            <select id="listWeight"><option value="">Qualsiasi</option><option value="light">Leggera</option><option value="medium">Media</option><option value="heavy">Impegnativa</option></select>
          </label>
          <label><span>Voto personale minimo</span>
            <select id="listPersonalRating"><option value="">Qualsiasi</option><option value="0.5">0,5★</option><option value="1">1★</option><option value="1.5">1,5★</option><option value="2">2★</option><option value="2.5">2,5★</option><option value="3">3★</option><option value="3.5">3,5★</option><option value="4">4★</option><option value="4.5">4,5★</option><option value="5">5★</option></select>
          </label>
          <label><span>Stato</span>
            <select id="listPlayed"><option value="">Qualsiasi</option><option value="true">Giocati</option><option value="false">Mai giocati</option></select>
          </label>
          <label><span>Rating BGG minimo</span><input id="listBggRating" type="number" min="0" max="10" step="0.1"></label>
          <label><span>Categoria</span><input id="listCategory" type="text" maxlength="500"></label>
          <label><span>Meccanica</span><input id="listMechanic" type="text" maxlength="500"></label>
        </div>
      </form>
    </section>
    <section class="saved-lists-layout">
      <aside class="saved-lists-panel">
        <div class="section-heading"><h2>Le tue liste</h2><span id="savedListCount" class="muted"></span></div>
        <div id="savedLists">${skeletons()}</div>
      </aside>
      <div class="saved-list-results" id="savedListResults">
        <div class="empty"><strong>Seleziona una lista.</strong><span>I risultati verranno calcolati sui dati attuali.</span></div>
      </div>
    </section>
  `;

  const kind = document.querySelector("#gameListKind");
  const fields = document.querySelector("#smartListFields");
  kind?.addEventListener("change", () => {
    fields.hidden = kind.value !== "smart";
  });

  const refreshListIndex = async () => {
    const payload = await api("/api/lists");
    const target = document.querySelector("#savedLists");
    const count = document.querySelector("#savedListCount");
    const items = payload.items || [];
    count.textContent = `${items.length} liste`;
    target.innerHTML = items.length
      ? items.map((item) => `
          <article class="saved-list-card" data-list-id="${escapeHtml(item.id)}">
            <button class="saved-list-open" type="button" data-open-list="${escapeHtml(item.id)}">
              <span class="saved-list-icon" aria-hidden="true">${icon(item.kind === "smart" ? "bolt" : "list")}</span>
              <span><strong>${escapeHtml(item.name)}</strong><small>${item.kind === "smart" ? escapeHtml(smartListFilterSummary(item.filters)) : "Lista manuale"}</small></span>
            </button>
            <button class="icon-button saved-list-delete" type="button" data-delete-list="${escapeHtml(item.id)}" aria-label="Elimina ${escapeHtml(item.name)}">×</button>
          </article>
        `).join("")
      : '<div class="empty"><span>Nessuna lista salvata.</span></div>';

    const openList = async (listId) => {
      const result = document.querySelector("#savedListResults");
      result.innerHTML = skeletons();
      try {
        const resolved = await api(`/api/lists/${encodeURIComponent(listId)}/games?limit=250`);
        const list = resolved.list;
        const games = resolved.items || [];
        result.innerHTML = `
          <header class="saved-list-result-head">
            <div><p class="eyebrow">${list.kind === "smart" ? "Lista dinamica" : "Lista manuale"}</p><h2>${escapeHtml(list.name)}</h2><p class="muted">${list.kind === "smart" ? escapeHtml(smartListFilterSummary(list.filters)) : "Titoli scelti manualmente"}</p></div>
            <strong>${formatNumber(resolved.total || 0, 0)} giochi</strong>
          </header>
          ${list.kind === "manual" ? `
            <div class="manual-list-add">
              <label><span>Aggiungi un gioco posseduto</span><input id="manualListSearch" type="search" placeholder="Cerca per titolo…" autocomplete="off"></label>
              <div id="manualListSearchResults"></div>
            </div>
          ` : ""}
          <div class="catalog-grid saved-list-game-grid">${games.length ? games.map((game) => gameCard(game)).join("") : '<div class="empty"><span>Nessun gioco corrisponde alla lista.</span></div>'}</div>
        `;
        if (list.kind === "manual") {
          const input = document.querySelector("#manualListSearch");
          const searchTarget = document.querySelector("#manualListSearchResults");
          let timer;
          input?.addEventListener("input", () => {
            window.clearTimeout(timer);
            timer = window.setTimeout(async () => {
              const q = String(input.value || "").trim();
              if (!q) { searchTarget.innerHTML = ""; return; }
              try {
                const search = await api(`/api/games?q=${encodeURIComponent(q)}&owned=true&limit=6`);
                const candidates = search.items || [];
                searchTarget.innerHTML = candidates.map((game) => `
                  <button class="manual-list-search-item" type="button" data-add-bgg="${game.bgg_id}">
                    <strong>${escapeHtml(game.title)}</strong><small>${game.year_published || "—"}</small><span>${icon("plus")}</span>
                  </button>
                `).join("") || '<span class="muted">Nessun gioco trovato.</span>';
                searchTarget.querySelectorAll("[data-add-bgg]").forEach((button) => {
                  button.addEventListener("click", async () => {
                    await api(`/api/lists/${encodeURIComponent(listId)}/items/${button.dataset.addBgg}`, {method: "PUT"});
                    showToast("Gioco aggiunto alla lista.");
                    await openList(listId);
                  });
                });
              } catch (error) {
                searchTarget.innerHTML = `<span class="muted">${escapeHtml(error.message)}</span>`;
              }
            }, 180);
          });
          result.querySelectorAll(".game-card-wrap").forEach((card) => {
            const bggId = card.dataset.gameId;
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "manual-list-remove";
            remove.textContent = "×";
            remove.title = "Rimuovi dalla lista";
            remove.addEventListener("click", async () => {
              await api(`/api/lists/${encodeURIComponent(listId)}/items/${bggId}`, {method: "DELETE"});
              await openList(listId);
            });
            card.append(remove);
          });
        }
      } catch (error) {
        result.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
      }
    };

    target.querySelectorAll("[data-open-list]").forEach((button) => {
      button.addEventListener("click", () => void openList(button.dataset.openList));
    });
    const focusedId = new URLSearchParams(window.location.search).get("focus");
    if (focusedId && items.some((item) => item.id === focusedId)) {
      await openList(focusedId);
    }
    target.querySelectorAll("[data-delete-list]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api(`/api/lists/${encodeURIComponent(button.dataset.deleteList)}`, {method: "DELETE"});
          showToast("Lista eliminata.");
          await refreshListIndex();
        } catch (error) {
          showToast(error.message, true);
        }
      });
    });
  };

  document.querySelector("#createGameListForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const listKind = document.querySelector("#gameListKind").value;
    const numberOrNull = (id) => {
      const value = String(document.querySelector(id)?.value || "").trim();
      return value ? Number(value) : null;
    };
    const filters = listKind === "smart" ? {
      owned: true,
      supports_players: numberOrNull("#listSupportsPlayers"),
      ideal_players: numberOrNull("#listIdealPlayers"),
      recommended_players: numberOrNull("#listRecommendedPlayers"),
      max_minutes: numberOrNull("#listMaxMinutes"),
      weight: document.querySelector("#listWeight").value || null,
      personal_rating_min: numberOrNull("#listPersonalRating"),
      played: document.querySelector("#listPlayed").value === ""
        ? null
        : document.querySelector("#listPlayed").value === "true",
      min_rating: numberOrNull("#listBggRating"),
      category: document.querySelector("#listCategory").value.trim() || null,
      mechanic: document.querySelector("#listMechanic").value.trim() || null,
    } : {};
    Object.keys(filters).forEach((key) => filters[key] === null && delete filters[key]);
    try {
      await api("/api/lists", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          name: document.querySelector("#gameListName").value.trim(),
          kind: listKind,
          filters,
        }),
      });
      showToast("Lista creata.");
      form.reset();
      fields.hidden = false;
      await refreshListIndex();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  try {
    await refreshListIndex();
  } catch (error) {
    document.querySelector("#savedLists").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function route() {
  catalogRequestController?.abort();
  exploreRequestController?.abort();
  rankingRequestController?.abort();
  bggCatalogRequestController?.abort();
  closeSidebar();
  updateShellNavigation();
  if (!/^\/updates\/?$/.test(window.location.pathname)) {
    clearUpdateRefresh();
  }
  if (/^\/reviews\/?$/.test(window.location.pathname)) {
    await renderReviews({reset: true});
    return;
  }
  if (/^\/updates\/?$/.test(window.location.pathname)) {
    await renderUpdates({reset: true});
    return;
  }
  if (/^\/discovery\/?$/.test(window.location.pathname)) {
    await renderDiscovery();
    return;
  }
  const referenceMatch = window.location.pathname.match(/^\/bgg\/(\d+)\/?$/);
  if (referenceMatch) {
    await renderReferenceDetail(Number(referenceMatch[1]));
    return;
  }
  if (/^\/bgg\/?$/.test(window.location.pathname)) {
    await renderBggCatalog();
    return;
  }
  if (/^\/rankings\/?$/.test(window.location.pathname)) {
    await renderRankings();
    return;
  }
  if (/^\/suggestions\/?$/.test(window.location.pathname)) {
    await renderSuggestions();
    return;
  }
  if (/^\/crowdfunding\/?$/.test(window.location.pathname)) {
    await renderCrowdfunding();
    return;
  }
  if (/^\/lists\/?$/.test(window.location.pathname)) {
    await renderLists();
    return;
  }
  if (/^\/wishlist\/?$/.test(window.location.pathname)) {
    await renderWishlist();
    return;
  }
  if (/^\/assistant\/?$/.test(window.location.pathname)) {
    await renderAssistant();
    return;
  }
  if (/^\/(?:plays|completed)\/?$/.test(window.location.pathname)) {
    await renderPlays();
    return;
  }
  if (/^\/play-next\/?$/.test(window.location.pathname) || /^\/new\/?$/.test(window.location.pathname)) {
    history.replaceState({}, "", "/");
  }
  if (/^\/explore\/?$/.test(window.location.pathname)) {
    await renderExplore();
    return;
  }
  if (/^\/categories\/?$/.test(window.location.pathname)) {
    await renderExplore("category");
    return;
  }
  if (/^\/mechanics\/?$/.test(window.location.pathname)) {
    await renderExplore("mechanic");
    return;
  }

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
  if (settingsDialog?.open && link.closest("#settingsDialog")) settingsDialog.close();
  if (globalSearchDialog?.open) globalSearchDialog.close();
  if (notificationDialog?.open) notificationDialog.close();
  history.pushState({}, "", url.pathname + url.search);
  closeSidebar();
  route();
  window.scrollTo({top: 0});
});

window.addEventListener("popstate", route);

sidebarToggle?.addEventListener("click", () => {
  setSidebarOpen(!document.body.classList.contains("sidebar-open"));
});
sidebarBackdrop?.addEventListener("click", closeSidebar);
window.addEventListener("resize", () => {
  if (window.innerWidth > 1040) closeSidebar();
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (globalSearchBar?.offsetParent) globalSearchBar.focus();
    else openGlobalSearchDialog();
    return;
  }
  if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
    closeSidebar();
  }
});

globalSearchForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = String(globalSearchBar?.value || "").trim();
  if (globalSearchInput) globalSearchInput.value = query;
  hideGlobalSearchPopover();
  openGlobalSearchDialog();
  void performGlobalSearch(query, globalSearchResults);
});
globalSearchBar?.addEventListener("input", () => {
  window.clearTimeout(globalSearchTimer);
  const query = String(globalSearchBar.value || "").trim();
  if (!query) {
    latestGlobalSearchQuery = "";
    hideGlobalSearchPopover();
    return;
  }
  globalSearchPopover.hidden = false;
  globalSearchTimer = window.setTimeout(() => void performGlobalSearch(query, globalSearchPopover), 160);
});
globalSearchBar?.addEventListener("focus", () => {
  if (globalSearchBar.value.trim() && globalSearchPopover?.childElementCount) globalSearchPopover.hidden = false;
});
globalSearchBar?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    hideGlobalSearchPopover();
    globalSearchBar.blur();
  }
});
globalSearchPopover?.addEventListener("click", (event) => {
  if (event.target.closest("a")) hideGlobalSearchPopover();
});
document.addEventListener("pointerdown", (event) => {
  if (globalSearchForm && !globalSearchForm.contains(event.target)) hideGlobalSearchPopover();
});
mobileSearchButton?.addEventListener("click", openGlobalSearchDialog);
closeGlobalSearch?.addEventListener("click", closeGlobalSearchDialog);
bindDialogCancel(globalSearchDialog, closeGlobalSearchDialog);
globalSearchInput?.addEventListener("input", () => {
  window.clearTimeout(globalSearchTimer);
  const query = String(globalSearchInput.value || "").trim();
  globalSearchTimer = window.setTimeout(() => void performGlobalSearch(query, globalSearchResults), 160);
});
notificationButton?.addEventListener("click", () => void openNotificationCenter());
mobileNotificationButton?.addEventListener("click", () => void openNotificationCenter());
closeNotificationDialog?.addEventListener("click", () => closeDialog(notificationDialog));
bindDialogCancel(notificationDialog);
void refreshNotificationBadge();

closeScanner.addEventListener("click", closeScannerDialog);
scannerDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeScannerDialog();
});
scannerDialog.addEventListener("close", resetScanner);
scannerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!scannerBarcode.value.trim()) return;
  scannerDetectionLocked = true;
  stopScannerCamera();
  void lookupScannerBarcode();
});
toggleCamera.addEventListener("click", () => {
  void startScannerCamera();
});
scannerPhoto?.addEventListener("change", () => {
  const file = scannerPhoto.files?.[0];
  if (file) void decodeScannerPhoto(file);
});

copyForm.addEventListener("submit", (event) => {
  void saveCopyEditor(event);
});
closeCopyDialogButton.addEventListener("click", closeCopyEditor);
cancelCopyDialog.addEventListener("click", closeCopyEditor);
copyDialog.addEventListener("cancel", (event) => {
  if (copyBusy) {
    event.preventDefault();
    return;
  }
  editingCopyId = null;
  editingCopyBggId = null;
});
copyDialog.addEventListener("close", () => {
  copyForm.reset();
  copyResult.hidden = true;
  copyResult.textContent = "";
  editingCopyId = null;
  editingCopyBggId = null;
  setCopyBusy(false);
});

documentForm.addEventListener("submit", (event) => {
  void saveDocumentUpload(event);
});
closeDocumentDialogButton.addEventListener("click", closeDocumentDialog);
cancelDocumentDialog.addEventListener("click", closeDocumentDialog);
documentDialog.addEventListener("cancel", (event) => {
  if (documentBusy) {
    event.preventDefault();
  }
});
documentDialog.addEventListener("close", resetDocumentDialog);
documentFile.addEventListener("change", () => {
  documentFileName.textContent = documentFile.files?.[0]?.name || "Nessun file selezionato";
});

settingsButton.addEventListener("click", () => {
  closeSidebar();
  void openSettingsDialog("general");
});
settingsCollapseExpansions?.addEventListener("change", (event) => {
  state.collapseExpansions = Boolean(event.currentTarget.checked);
  state.expandedGameGroups.clear();
  state.offset = 0;
  window.localStorage.setItem("bgc.collapseExpansions", state.collapseExpansions ? "true" : "false");
  if (window.location.pathname === "/") {
    void refreshCatalog();
  }
});
settingsTabs.forEach((tab) => {
  tab.addEventListener("click", () => setSettingsTab(tab.dataset.settingsTab));
});

closeSettings.addEventListener("click", closeSettingsDialog);
cancelSettings.addEventListener("click", closeSettingsDialog);

settingsDialog.addEventListener("cancel", (event) => {
  if (settingsBusy) {
    event.preventDefault();
  }
});

settingsDialog.addEventListener("close", () => {
  settingsForm.reset();
  settingsResult.hidden = true;
  settingsResult.textContent = "";
  currentBggSettings = null;
  currentRagSettings = null;
  currentYoutubeSettings = null;
  currentCrowdfundingSettings = null;
});

settingsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void persistSettings({verifyAfter: false});
});

saveTestSettings.addEventListener("click", () => {
  void persistSettings({verifyAfter: true});
});

bggSyncSettingsNow.addEventListener("click", () => {
  void runManualBggSync();
});

document.querySelector("#catalogBggSync")?.addEventListener("click", () => {
  void runCatalogBggSync();
});

async function wakeLmstudioHost() {
  if (!lmstudioWakeButton || lmstudioWakeButton.disabled) return;
  lmstudioWakeButton.disabled = true;
  lmstudioWakeButton.classList.add("is-busy");
  try {
    const result = await api("/api/system/lmstudio/wake", {method: "POST"});
    showToast(
      result.already_ready
        ? "LM Studio è già raggiungibile."
        : "Segnale Wake-on-LAN inviato al PC di LM Studio.",
    );
  } catch (error) {
    showToast(error.message, true);
  } finally {
    lmstudioWakeButton.disabled = false;
    lmstudioWakeButton.classList.remove("is-busy");
  }
}

lmstudioWakeButton?.addEventListener("click", () => {
  void wakeLmstudioHost();
});

bggClearToken.addEventListener("change", () => {
  bggApplicationToken.disabled =
    bggClearToken.checked || Boolean(currentBggSettings?.overrides?.application_token);
  if (bggClearToken.checked) bggApplicationToken.value = "";
});

lmstudioClearApiKey.addEventListener("change", () => {
  lmstudioApiKey.disabled = lmstudioClearApiKey.checked;
  if (lmstudioClearApiKey.checked) lmstudioApiKey.value = "";
});

geminiClearApiKey.addEventListener("change", () => {
  geminiApiKey.disabled = geminiClearApiKey.checked;
  if (geminiClearApiKey.checked) geminiApiKey.value = "";
});

youtubeClearApiKey.addEventListener("change", () => {
  youtubeApiKey.disabled =
    youtubeClearApiKey.checked || Boolean(currentYoutubeSettings?.overrides?.api_key);
  if (youtubeClearApiKey.checked) youtubeApiKey.value = "";
});

apifyClearToken.addEventListener("change", () => {
  apifyToken.disabled =
    apifyClearToken.checked || Boolean(currentCrowdfundingSettings?.overrides?.apify_token);
  if (apifyClearToken.checked) apifyToken.value = "";
});

verifyApifyToken.addEventListener("click", () => {
  void saveAndVerifyApify();
});

importButton.addEventListener("click", () => {
  closeSidebar();
  if (settingsDialog?.open) settingsDialog.close();
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
