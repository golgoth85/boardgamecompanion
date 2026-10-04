const app = document.querySelector("#app");
const appSidebar = document.querySelector("#appSidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const sidebarBackdrop = document.querySelector("#sidebarBackdrop");
const mobileSectionTitle = document.querySelector("#mobileSectionTitle");

const shellSectionLabels = {
  catalog: "Ludoteca",
  rankings: "Classifiche",
  explore: "Esplora",
  completed: "Completati",
  reviews: "Fonti da verificare",
  updates: "Aggiornamenti regolamenti",
  discovery: "Ricerca regolamenti",
};

function shellRouteKey(pathname = window.location.pathname) {
  if (/^\/rankings\/?$/.test(pathname)) return "rankings";
  if (/^\/completed\/?$/.test(pathname)) return "completed";
  if (/^\/(?:explore|categories|mechanics)\/?$/.test(pathname)) return "explore";
  if (/^\/reviews\/?$/.test(pathname)) return "reviews";
  if (/^\/updates\/?$/.test(pathname)) return "updates";
  if (/^\/discovery\/?$/.test(pathname)) return "discovery";
  return "catalog";
}

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
const importSidebarButton = document.querySelector("#importSidebarButton");
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
const scannerButton = document.querySelector("#scannerButton");
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
const settingsForm = document.querySelector("#settingsForm");
const closeSettings = document.querySelector("#closeSettings");
const cancelSettings = document.querySelector("#cancelSettings");
const saveSettings = document.querySelector("#saveSettings");
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
const catalogAssistantButton = document.querySelector("#catalogAssistantButton");
const catalogAssistantDialog = document.querySelector("#catalogAssistantDialog");
const catalogAssistantForm = document.querySelector("#catalogAssistantForm");
const catalogAssistantQuestion = document.querySelector("#catalogAssistantQuestion");
const catalogAssistantResult = document.querySelector("#catalogAssistantResult");
const closeCatalogAssistant = document.querySelector("#closeCatalogAssistant");
const cancelCatalogAssistant = document.querySelector("#cancelCatalogAssistant");
const askCatalogAssistant = document.querySelector("#askCatalogAssistant");
const toast = document.querySelector("#toast");

const state = {
  q: "",
  itemType: "",
  owned: "",
  sort: "title",
  limit: 250,
  offset: 0,
  total: 0,
  catalogView: window.localStorage.getItem("bgc.catalogView") === "list" ? "list" : "cards",
  collapseExpansions: window.localStorage.getItem("bgc.collapseExpansions") !== "false",
  expandedGameGroups: new Set(),
  supportsPlayers: "",
  idealPlayers: "",
  playerAge: "",
  weight: "",
  maxMinutes: "",
  minRating: "",
  category: "",
  mechanic: "",
};

const exploreState = {
  activeTab: "category",
  categories: new Set(),
  mechanics: new Set(),
  supportsPlayers: "",
  idealPlayers: "",
  playerAge: "",
  weight: "",
  maxMinutes: "",
  minRating: "",
  expandedResults: false,
  showRareFacets: {
    category: false,
    mechanic: false,
  },
};

let exploreRequestController;
let currentExplorePayload = null;

const rankingState = {
  group: "top",
  mode: "overall",
  category: "",
  mechanic: "",
  idealPlayers: "",
  maxMinutes: "",
  weight: "",
};

let rankingRequestController;
let rankingFacetsCache = null;

const rankingGroups = {
  top: {
    label: "Top",
    modes: [
      ["overall", "Migliori in assoluto"],
      ["outside_top", "Fuori dalla Top 500"],
      ["quality_time", "Qualità / tempo"],
      ["safe_choice", "Scelta sicura"],
    ],
  },
  situation: {
    label: "Per situazione",
    modes: [
      ["gateway", "Gateway"],
      ["expert", "Per esperti"],
      ["quality_time", "Qualità / tempo"],
      ["safe_choice", "Scelta sicura"],
    ],
  },
  facets: {
    label: "Generi & Meccaniche",
    modes: [
      ["overall", "Migliori"],
      ["outside_top", "Fuori dalla Top 500"],
      ["safe_choice", "Scelta sicura"],
    ],
  },
  personal: {
    label: "Personali",
    modes: [
      ["personal_favorites", "Preferiti personali"],
    ],
  },
}

const catalogColumnSorts = {
  title: ["title", "title_desc"],
  players: ["players_asc", "players_desc"],
  age: ["age_asc", "age_desc"],
  duration: ["duration_asc", "duration_desc"],
  weight: ["weight_desc", "weight_asc"],
  rating: ["rating_desc", "rating_asc"],
};

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
      const select = document.querySelector("#sortFilter");
      if (select) select.value = state.sort;
      refreshCatalog();
    });
  });
}

let searchTimer;
let catalogRequestController;
let currentCatalogData = null;
let importInProgress = false;
let settingsBusy = false;
let currentBggSettings = null;
let currentRagSettings = null;
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Human-reviewed web search: no Google API, scraping, or automatic PDF trust.
function googleRulebookSearchUrl(title) {
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

function initials(title) {
  const words = String(title || "?").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.slice(0, 3).map((word) => word[0]).join("").toUpperCase();
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("it-IT", { maximumFractionDigits: digits });
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
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function setSettingsBusy(busy) {
  settingsBusy = busy;
  for (const control of [closeSettings, cancelSettings, saveSettings, saveTestSettings]) {
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
  const active = ["general", "rulebooks", "providers"].includes(name) ? name : "general";
  settingsTabs.forEach((tab) => {
    const selected = tab.dataset.settingsTab === active;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
  });
  settingsPanels.forEach((panel) => {
    panel.hidden = panel.dataset.settingsPanel !== active;
  });
  if (saveSettings) saveSettings.hidden = active === "rulebooks";
  if (saveTestSettings) saveTestSettings.hidden = active !== "general";
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

  ragEmbeddingOrder.value = (data.embedding_provider_order || []).join(",");
  ragGenerationOrder.value = (data.generation_provider_order || []).join(",");
  ollamaUrl.value = ollama.url || "";
  ollamaEmbeddingModel.value = ollama.embedding_model || "";
  ollamaGenerationModel.value = ollama.generation_model || "";
  lmstudioUrl.value = lmstudio.url || "";
  lmstudioEmbeddingModel.value = lmstudio.embedding_model || "";
  lmstudioGenerationModel.value = lmstudio.generation_model || "";
  lmstudioGenerationTimeout.value = lmstudio.generation_timeout_seconds ?? 300;
  lmstudioGenerationMaxTokens.value = lmstudio.generation_max_tokens ?? 512;
  lmstudioDisableThinking.checked = lmstudio.generation_disable_thinking !== false;
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

function parseProviderOrder(value, label) {
  const allowed = new Set(["ollama", "lmstudio", "gemini"]);
  const result = String(value || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  if (!result.length || result.length > 3) {
    throw new Error(`${label}: indica da 1 a 3 provider.`);
  }
  if (new Set(result).size !== result.length || result.some((item) => !allowed.has(item))) {
    throw new Error(
      `${label}: usa solo ollama, lmstudio, gemini senza duplicati.`,
    );
  }
  return result;
}

async function openSettingsDialog(initialTab = "general") {
  settingsDialog.querySelectorAll(".settings-provider").forEach((section) => {
    section.open = false;
  });
  setSettingsTab(initialTab);
  settingsResult.hidden = true;
  settingsResult.textContent = "";
  setSettingsBusy(true);
  try {
    const [bggData, ragData, syncData] = await Promise.all([
      api("/api/settings/bgg"),
      api("/api/settings/rag"),
      api("/api/bgg-collection-sync"),
    ]);
    applyBggSettingsToForm(bggData);
    applyRagSettingsToForm(ragData);
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
      embedding_provider_order: parseProviderOrder(
        ragEmbeddingOrder.value,
        "Priorità embedding",
      ),
      generation_provider_order: parseProviderOrder(
        ragGenerationOrder.value,
        "Priorità generation",
      ),
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
    showToast(created ? "Documento caricato. Indicizzazione automatica avviata." : "Documento già presente. Indicizzazione verificata.");
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


async function decodeScannerPhoto(file) {
  if (!file || scannerBusy) return;
  const Reader = window.ZXingBrowser?.BrowserMultiFormatReader;
  if (!Reader) {
    cameraHint.textContent = "Lettore barcode non disponibile.";
    scannerManualFallback.open = true;
    return;
  }
  const objectUrl = URL.createObjectURL(file);
  scannerPhotoButton?.classList.add("is-busy");
  cameraHint.textContent = "Leggo il barcode dalla foto…";
  try {
    const reader = new Reader();
    configureZxingFormats(reader);
    const result = await reader.decodeFromImageUrl(objectUrl);
    const text = result?.getText?.() ?? result?.text;
    if (!text) throw new Error("Barcode non trovato");
    acceptScannerDetection(text);
  } catch (_) {
    cameraHint.textContent =
      "Non riesco a leggere il barcode dalla foto. Riprova più vicino oppure inseriscilo manualmente.";
    scannerManualFallback.open = true;
  } finally {
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

function renderScannerUnmatched(barcode) {
  scannerResult.innerHTML = `
    <div class="scanner-unmatched">
      <strong>Barcode non associato</strong>
      <p class="muted">
        Cerca un gioco posseduto e assegna il codice <code>${escapeHtml(barcode)}</code>
        a una copia fisica.
      </p>
      <div class="inline-input-action">
        <input id="scannerGameSearch" type="search" autocomplete="off"
               placeholder="Cerca gioco posseduto…">
        <button class="button button-ghost" id="scannerSearchGames" type="button">Cerca</button>
      </div>
      <div id="scannerGameResults" class="scanner-game-results"></div>
    </div>
  `;
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
  window.setTimeout(() => searchInput?.focus(), 0);
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
    } else {
      renderScannerUnmatched(barcode);
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

function catalogMetric(label, value) {
  return `<div class="catalog-metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
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
          ? `<img src="${escapeHtml(game.bgg_metadata.cover_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<span>${escapeHtml(initials(game.title))}</span>`}
      </span>
      <span class="expansion-mini-copy">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${escapeHtml(playerText(game))} gioc. · ${escapeHtml(timeText(game))}</small>
      </span>
      ${game.collection?.own ? '<span class="owned-dot" title="Posseduta">✓</span>' : ""}
    </a>
  `;
}

function gameCard(game, expansions = []) {
  const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
  const rating = game.bgg?.average ? formatNumber(game.bgg.average, 1) : "—";
  const weight = game.bgg?.average_weight ? formatNumber(game.bgg.average_weight, 2) : "—";
  const ownedExpansionCount = expansions.filter((item) => item.collection?.own).length;
  const groupId = `game-group-${game.bgg_id}`;
  const expanded = state.expandedGameGroups.has(String(game.bgg_id));
  return `
    <article class="game-card-wrap ${expansions.length ? "has-expansions" : ""}" data-game-id="${game.bgg_id}">
      <a class="game-card" href="/games/${game.bgg_id}" data-nav aria-label="Apri ${escapeHtml(game.title)}">
        <div class="cover">
          <span class="badge card-badge">${type}</span>
          ${game.bgg_metadata?.cover_url
            ? `<img class="cover-image" src="${escapeHtml(game.bgg_metadata.cover_url)}" alt="Cover di ${escapeHtml(game.title)}" loading="lazy" referrerpolicy="no-referrer">`
            : `<span class="cover-initials">${escapeHtml(initials(game.title))}</span>`}
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(game.title)}</h3>
          <div class="catalog-metrics">
            ${catalogMetric("Giocatori", playerText(game))}
            ${catalogMetric("Età", ageText(game))}
            ${catalogMetric("Durata", timeText(game).replace(" min", ""))}
            ${catalogMetric("Peso", weight)}
          </div>
          <div class="card-footer-meta">
            <span>${game.year_published || "—"}</span>
            <span class="rating">★ ${rating}</span>
          </div>
        </div>
      </a>
      ${expansions.length ? `
        <button class="expansion-count-badge" type="button" data-expansion-toggle="${game.bgg_id}"
                aria-controls="${groupId}" aria-expanded="${expanded ? "true" : "false"}"
                title="${ownedExpansionCount} espansioni possedute su ${expansions.length}">
          <strong>${ownedExpansionCount}</strong><span>esp.</span>
        </button>
        <div class="expansion-drawer" id="${groupId}" ${expanded ? "" : "hidden"}>
          ${expansions.map(expansionMiniCard).join("")}
        </div>
      ` : ""}
    </article>
  `;
}

function gameListRow(game, expansions = [], isExpansion = false) {
  const rating = game.bgg?.average ? formatNumber(game.bgg.average, 1) : "—";
  const weight = game.bgg?.average_weight ? formatNumber(game.bgg.average_weight, 2) : "—";
  const ownedExpansionCount = expansions.filter((item) => item.collection?.own).length;
  const expanded = state.expandedGameGroups.has(String(game.bgg_id));
  return `
    <div class="catalog-list-row ${isExpansion ? "is-expansion-row" : ""}">
      <a class="catalog-list-game" href="/games/${game.bgg_id}" data-nav aria-label="Apri ${escapeHtml(game.title)}">
        <span class="catalog-list-cover">
          ${game.bgg_metadata?.cover_url
            ? `<img src="${escapeHtml(game.bgg_metadata.cover_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
            : `<span>${escapeHtml(initials(game.title))}</span>`}
        </span>
        <span class="catalog-list-title">
          <strong>${escapeHtml(game.title)}</strong>
          <small>${game.item_type === "expansion" ? "Espansione" : (game.year_published || "Gioco base")}</small>
        </span>
      </a>
      <span class="list-stat"><strong>${escapeHtml(playerText(game))}</strong><small>Giocatori</small></span>
      <span class="list-stat"><strong>${escapeHtml(ageText(game))}</strong><small>Età</small></span>
      <span class="list-stat"><strong>${escapeHtml(timeText(game).replace(" min", ""))}</strong><small>Minuti</small></span>
      <span class="list-stat"><strong>${weight}</strong><small>Peso</small></span>
      <span class="list-rating"><strong>${rating}</strong><small>BGG</small></span>
      ${expansions.length ? `
        <button class="list-expansion-toggle" type="button" data-expansion-toggle="${game.bgg_id}"
                aria-expanded="${expanded ? "true" : "false"}"
                title="${ownedExpansionCount} espansioni possedute su ${expansions.length}">
          <strong>${ownedExpansionCount}</strong><span>esp.</span><i aria-hidden="true">${expanded ? "▴" : "▾"}</i>
        </button>
      ` : '<span class="list-expansion-placeholder"></span>'}
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
      if (caret) caret.textContent = expanded ? "▴" : "▾";
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
        <p class="eyebrow">Ludoteca</p>
        <h1>I tuoi giochi</h1>
        <p class="page-lead">Trova rapidamente il gioco giusto per persone, tempo e serata.</p>
        <div class="catalog-hero-actions">
          <button class="assistant-home-button" id="catalogAssistantHome" type="button">
            <span aria-hidden="true">✦</span>
            <span><strong>Chiedi alla tua ludoteca</strong><small>Consigli su misura con l'AI</small></span>
          </button>
          ${activeFacet ? `
            <button class="active-facet-chip" id="clearFacet" type="button">
              ${escapeHtml(activeFacet)} <span aria-hidden="true">×</span>
            </button>
          ` : ""}
        </div>
      </div>
      <div class="page-header-meta catalog-header-actions">
        <div class="catalog-sync-inline" title="Sincronizzazione automatica BoardGameGeek">
          <span class="status-dot" id="catalogBggSyncDot" aria-hidden="true"></span>
          <span id="catalogBggSyncStatus">BGG</span>
          <button class="sync-icon-button" id="catalogBggSync" type="button"
                  aria-label="Sincronizza ora con BoardGameGeek" title="Sincronizza ora">↻</button>
        </div>
        <div class="catalog-view-switch" aria-label="Vista catalogo">
          <button class="view-switch-button ${state.catalogView === "cards" ? "is-active" : ""}" id="cardViewButton"
                  type="button" aria-pressed="${state.catalogView === "cards" ? "true" : "false"}">▦ Card</button>
          <button class="view-switch-button ${state.catalogView === "list" ? "is-active" : ""}" id="listViewButton"
                  type="button" aria-pressed="${state.catalogView === "list" ? "true" : "false"}">☷ Lista</button>
        </div>
      </div>
    </section>

    <section class="stats-panel catalog-overview" id="statsPanel" aria-label="Riepilogo ludoteca">
      <div class="stat"><strong>—</strong><span>Giochi base</span></div>
      <div class="stat"><strong>—</strong><span>Espansioni</span></div>
      <div class="stat"><strong>—</strong><span>Completati</span></div>
      <div class="stat"><strong>—</strong><span>Regolamenti</span></div>
    </section>

    <section class="achievement-showcase" id="achievementShowcase" hidden>
      <div class="achievement-showcase-head">
        <div><p class="eyebrow">Ultimi traguardi</p><h2>Dalla Sala dei trofei</h2></div>
        <a class="button button-ghost" href="/completed" data-nav>Vedi tutti</a>
      </div>
      <div class="achievement-showcase-grid" id="achievementShowcaseGrid"></div>
    </section>

    <section class="catalog-workspace" aria-labelledby="catalogGamesHeading">
      <div class="catalog-head catalog-workspace-head">
        <div>
          <h2 id="catalogGamesHeading">Collezione</h2>
          <p class="section-subtitle">Ricerca libera o filtri avanzati per trovare il tavolo giusto.</p>
        </div>
        <div class="catalog-head-actions">
          <label class="collapse-expansions-toggle">
            <input id="collapseExpansions" type="checkbox" ${state.collapseExpansions ? "checked" : ""}>
            <span>Raggruppa espansioni</span>
          </label>
          <span class="muted" id="resultCount">Caricamento…</span>
        </div>
      </div>

      <section class="toolbar catalog-simple-search" aria-label="Ricerca catalogo">
        <label class="field search-field">
          <input id="searchInput" type="search" aria-label="Cerca per titolo"
                 placeholder="Cerca un gioco…" value="${escapeHtml(state.q)}" autocomplete="off">
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
            <option value="">Tutti</option>
            <option value="true" ${state.owned === "true" ? "selected" : ""}>Posseduti</option>
            <option value="false" ${state.owned === "false" ? "selected" : ""}>Non posseduti</option>
          </select>
        </label>
        <label class="field">
          <select id="sortFilter" aria-label="Ordina">
            <optgroup label="Titolo">
              <option value="title" ${state.sort === "title" ? "selected" : ""}>Titolo A–Z</option>
              <option value="title_desc" ${state.sort === "title_desc" ? "selected" : ""}>Titolo Z–A</option>
            </optgroup>
            <optgroup label="Giocatori">
              <option value="players_asc" ${state.sort === "players_asc" ? "selected" : ""}>Giocatori: meno → più</option>
              <option value="players_desc" ${state.sort === "players_desc" ? "selected" : ""}>Giocatori: più → meno</option>
            </optgroup>
            <optgroup label="Età">
              <option value="age_asc" ${state.sort === "age_asc" ? "selected" : ""}>Età: più bassa</option>
              <option value="age_desc" ${state.sort === "age_desc" ? "selected" : ""}>Età: più alta</option>
            </optgroup>
            <optgroup label="Durata">
              <option value="duration_asc" ${state.sort === "duration_asc" ? "selected" : ""}>Durata: più breve</option>
              <option value="duration_desc" ${state.sort === "duration_desc" ? "selected" : ""}>Durata: più lunga</option>
            </optgroup>
            <optgroup label="Valutazione">
              <option value="rating_desc" ${state.sort === "rating_desc" ? "selected" : ""}>Rating BGG: migliore</option>
              <option value="rating_asc" ${state.sort === "rating_asc" ? "selected" : ""}>Rating BGG: peggiore</option>
              <option value="rank_asc" ${state.sort === "rank_asc" ? "selected" : ""}>Classifica BGG</option>
              <option value="weight_desc" ${state.sort === "weight_desc" ? "selected" : ""}>Complessità: alta</option>
              <option value="weight_asc" ${state.sort === "weight_asc" ? "selected" : ""}>Complessità: bassa</option>
              <option value="year_desc" ${state.sort === "year_desc" ? "selected" : ""}>Anno più recente</option>
            </optgroup>
          </select>
        </label>
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

      <section class="catalog-results ${state.catalogView === "list" ? "catalog-results-list" : "catalog-results-cards"}"
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
  document.querySelector("#ownedFilter")?.addEventListener("change", (event) => refreshFrom("owned", event.target.value));
  document.querySelector("#sortFilter")?.addEventListener("change", (event) => refreshFrom("sort", event.target.value));

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

  document.querySelector("#catalogAssistantHome")?.addEventListener("click", () => {
    openCatalogAssistant();
  });

  document.querySelector("#catalogBggSync")?.addEventListener("click", () => {
    void runCatalogBggSync();
  });

  document.querySelector("#collapseExpansions")?.addEventListener("change", (event) => {
    state.collapseExpansions = event.target.checked;
    state.expandedGameGroups.clear();
    window.localStorage.setItem("bgc.collapseExpansions", state.collapseExpansions ? "true" : "false");
    rerenderCurrentCatalog();
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
  const params = new URLSearchParams({
    limit: String(state.limit),
    offset: String(state.offset),
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
    [stats.completed, "Completati"],
    [stats.rulebooks, "Regolamenti"],
  ];
  document.querySelector("#statsPanel").innerHTML = values.map(([value, label]) =>
    `<div class="stat"><strong>${formatNumber(value, 0)}</strong><span>${label}</span></div>`
  ).join("");
}

function renderCatalogData(catalog) {
  currentCatalogData = catalog;
  state.total = catalog.total;
  const grid = document.querySelector("#catalogGrid");
  const count = document.querySelector("#resultCount");
  if (!grid || !count) return;

  count.textContent = `${formatNumber(catalog.total, 0)} titoli`;
  grid.className = `catalog-results ${state.catalogView === "list" ? "catalog-results-list" : "catalog-results-cards"}`;

  if (!catalog.items.length) {
    grid.innerHTML = '<div class="empty catalog-empty">Nessun gioco corrisponde ai filtri selezionati.</div>';
  } else {
    const groups = groupCatalogItems(catalog.items);
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

function ragIndexFailureText(item) {
  const raw = String(item?.last_error_message || "").trim();
  if (!raw) return "Indicizzazione non riuscita.";

  if (/failed.*->.*failed/i.test(raw)) {
    return raw.slice(0, 320);
  }
  if (/Gemini embedding request failed with HTTP 429/i.test(raw)) {
    return "Gemini embedding non disponibile: quota/rate limit (HTTP 429).";
  }
  if (/Gemini embedding/i.test(raw)) {
    return "Gemini embedding non disponibile: " + raw.slice(0, 220);
  }
  if (/Ollama/i.test(raw) || /qwen/i.test(raw)) {
    return "Qwen/Ollama embedding non disponibile: " + raw.slice(0, 220);
  }
  if (/embedding/i.test(raw)) {
    return "Embedding non disponibile: " + raw.slice(0, 220);
  }
  return "Indicizzazione non riuscita: " + raw.slice(0, 220);
}

async function refreshRagIndexStatus(bggId, documentItems, {poll = true} = {}) {
  const status = document.querySelector("#ragIndexStatus");
  const retry = document.querySelector(".rag-prepare-index");
  const currentPath = window.location.pathname.replace(/\/+$/, "");
  if (!status || currentPath !== "/games/" + bggId) return;

  if (!documentItems.length) {
    status.className = "rag-index-status muted";
    status.textContent = "L'indice verrà creato automaticamente quando aggiungi un regolamento.";
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
      status.textContent = "Indicizzazione automatica in preparazione…";
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
        retry.textContent = "Riprova indicizzazione";
      }
      return;
    }

    if (running.length) {
      status.className = "rag-index-status";
      const stageLabels = {queued: "in coda", ingest: "lettura PDF", chunks: "preparazione testo", embeddings: "indicizzazione"};
      const stage = running[0]?.stage;
      status.textContent = "Indicizzazione automatica in corso" + (stage ? " · " + (stageLabels[stage] || stage) : "") + "…";
      if (retry) retry.hidden = true;
      if (poll) window.setTimeout(() => void refreshRagIndexStatus(bggId, documentItems), 3000);
      return;
    }

    if (ready.length === documentItems.length) {
      status.className = "rag-index-status success";
      status.textContent = documentItems.length === 1
        ? "✓ Regolamento indicizzato"
        : "✓ " + documentItems.length + " documenti indicizzati";
      if (retry) retry.hidden = true;
      return;
    }

    status.className = "rag-index-status";
    status.textContent = "Indicizzazione automatica in preparazione…";
    if (retry) retry.hidden = true;
  } catch (_) {
    status.className = "rag-index-status error";
    status.textContent = "Non riesco a verificare l'indicizzazione.";
    if (retry) {
      retry.hidden = false;
      retry.disabled = false;
      retry.textContent = "Riprova indicizzazione";
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
  status.textContent = "Riprovo l'indicizzazione…";
  try {
    const providerMessages = [];
    for (const item of documentItems) {
      try {
        const indexed = await api(
          "/api/documents/" + encodeURIComponent(item.id) + "/auto-index/run",
          {method: "POST"},
        );
        const providerMessage = indexed?.embeddings?.provider_message;
        if (providerMessage && !providerMessages.includes(providerMessage)) {
          providerMessages.push(providerMessage);
        }
      } catch (error) {
        if (error.status !== 409) throw error;
      }
    }
    showToast(
      providerMessages.length
        ? providerMessages.join(" · ")
        : "Indicizzazione completata."
    );
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

async function ensureItalianDescription(bggId) {
  const node = document.querySelector("#gameDescriptionText");
  if (!node?.isConnected || node.dataset.ready === "true" || navigator.webdriver) return;
  try {
    let status = await api(`/api/games/${bggId}/description-it`);
    if (!status.source_available) {
      const metadata = await api(`/api/games/${bggId}/bgg-metadata/refresh`, {method: "POST"});
      const cover = document.querySelector(".game-summary-cover .detail-cover");
      if (cover?.isConnected && metadata.cover_url) {
        cover.innerHTML = `<img class="cover-image" src="${escapeHtml(metadata.cover_url)}" alt="" referrerpolicy="no-referrer">`;
      }
      status = await api(`/api/games/${bggId}/description-it`);
    }
    if (status.translation?.translated_text) {
      node.textContent = status.translation.translated_text;
      node.dataset.ready = "true";
      return;
    }
    const translated = await api(`/api/games/${bggId}/description-it/translate`, {method: "POST"});
    if (translated.translation?.translated_text && node.isConnected) {
      node.textContent = translated.translation.translated_text;
      node.dataset.ready = "true";
    }
  } catch (_) {
    if (node?.isConnected) {
      node.textContent = "Descrizione italiana non disponibile al momento.";
    }
  }
}

async function renderDetail(bggId) {
  app.innerHTML = `
    <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
    <section class="game-page game-page-loading">
      <div class="game-summary-rail"><div class="skeleton"></div></div>
      <div class="game-main"><div class="skeleton"></div></div>
    </section>
  `;
  const requestedPath = window.location.pathname;
  try {
    const [game, copies, documents] = await Promise.all([
      api(`/api/games/${bggId}`),
      api(`/api/games/${bggId}/copies`),
      api(`/api/games/${bggId}/documents`),
    ]);
    if (window.location.pathname !== requestedPath) return;

    const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
    const collection = game.collection || {};
    const bgg = game.bgg || {};
    const metadata = game.bgg_metadata || {};
    const copyItems = copies.items || [];
    const documentItems = documents.items || [];
    const rulebooks = documentItems.filter((item) => item.document_type === "rulebook");
    const italianDescription = String(game.description_it || "").trim();
    const description = italianDescription
      ? escapeHtml(italianDescription).replace(/\r?\n/g, "<br>")
      : "Traduzione italiana in preparazione…";
    const copyLabel = copyItems.length === 1 ? "1 copia registrata" : `${copyItems.length} copie registrate`;
    const firstRulebook = rulebooks[0] || null;

    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>

      <section class="game-page game-centric-detail">
        <aside class="game-summary-rail" aria-label="Riepilogo gioco">
          <div class="game-summary-cover">
            <div class="detail-cover">
              ${metadata.cover_url
                ? `<img class="cover-image" src="${escapeHtml(metadata.cover_url)}" alt="Cover di ${escapeHtml(game.title)}" referrerpolicy="no-referrer">`
                : `<span class="cover-initials">${escapeHtml(initials(game.title))}</span>`}
            </div>
          </div>

          <div class="game-summary-card">
            <div class="game-summary-badges">
              <span class="badge">${type}</span>
              ${collection.own ? '<span class="badge">✓ Posseduto</span>' : ""}
              ${game.year_published ? `<span class="badge">${game.year_published}</span>` : ""}
            </div>
            <dl class="game-summary-list game-facts-primary">
              <div><dt>Giocatori</dt><dd>${escapeHtml(playerText(game))}</dd></div>
              <div><dt>Raccomandato per</dt><dd>${escapeHtml(bgg.recommended_players || "—")}</dd></div>
              <div><dt>Ideale per</dt><dd>${escapeHtml(bgg.best_players || "—")}</dd></div>
              <div><dt>Età ufficiale</dt><dd>${escapeHtml(ageText(game))}</dd></div>
              <div><dt>Durata</dt><dd>${escapeHtml(timeText(game))}</dd></div>
              <div><dt>Complessità</dt><dd>${bgg.average_weight ? `${formatNumber(bgg.average_weight, 2)} / 5` : "—"}</dd></div>
              <div><dt>Rating BGG</dt><dd>${bgg.average ? `★ ${formatNumber(bgg.average, 2)}` : "—"}</dd></div>
            </dl>
            <a class="external-link game-bgg-link"
               href="https://boardgamegeek.com/boardgame/${game.bgg_id}"
               target="_blank" rel="noopener noreferrer">Apri su BoardGameGeek ↗</a>
          </div>
        </aside>

        <article class="game-main detail-main">
          <header class="game-header game-header-player">
            <div>
              <p class="eyebrow">BGG #${game.bgg_id}</p>
              <h1>${escapeHtml(game.title)}</h1>
              ${game.original_title && game.original_title !== game.title
                ? `<p class="game-original-title">${escapeHtml(game.original_title)}</p>`
                : ""}
            </div>
            <div class="game-primary-actions">
              <button class="button ${game.progress?.completed ? "completion-button is-completed" : "button-ghost completion-button"}"
                      id="toggleCompleted" type="button"
                      aria-pressed="${game.progress?.completed ? "true" : "false"}">
                ${game.progress?.completed ? "♛ Completato" : "Segna completato"}
              </button>
              <button class="button button-primary" id="addPhysicalCopy" type="button">+ Aggiungi copia</button>
            </div>
          </header>

          <section class="game-description-panel" aria-labelledby="gameDescriptionTitle">
            <p class="eyebrow">Il gioco</p>
            <h2 id="gameDescriptionTitle">Descrizione</h2>
            <div class="game-description-text" id="gameDescriptionText" data-ready="${italianDescription ? "true" : "false"}">${description}</div>
          </section>

          <section class="copy-compact-panel" aria-label="Copie fisiche">
            <div class="copy-compact-summary">
              <div>
                <strong>La tua copia</strong>
                <span>${copyItems.length ? escapeHtml(copyLabel) : "Nessuna copia registrata"}</span>
              </div>
              <button class="button button-ghost" id="addPhysicalCopySecondary" type="button">
                ${copyItems.length ? "+ Aggiungi altra copia" : "+ Aggiungi copia"}
              </button>
            </div>
            ${copyItems.length ? `
              <details class="copy-details-disclosure">
                <summary>Gestisci ${escapeHtml(copyLabel)}</summary>
                <div class="physical-copy-list" id="physicalCopyList">
                  ${copyItems.map((copy, index) => physicalCopyCard(copy, index)).join("")}
                </div>
              </details>
            ` : '<div id="physicalCopyList" hidden></div>'}
          </section>

          <section class="game-section rules-workspace rules-simple" aria-labelledby="rulesWorkspaceTitle">
            <div class="simple-rulebook-head">
              <div>
                <p class="eyebrow">Regolamento</p>
                <h2 id="rulesWorkspaceTitle">Regole</h2>
              </div>
              <span class="rulebook-presence ${rulebooks.length ? "is-present" : "is-missing"}">
                ${rulebooks.length ? "✓ Regolamento presente" : "Regolamento non presente"}
              </span>
            </div>

            <div class="simple-rulebook-actions">
              <button class="button button-primary" id="rulebookSearchAction" type="button">Cerca automaticamente</button>
              <button class="button button-ghost" id="addDocument" type="button">Carica PDF</button>
              ${firstRulebook ? `<a class="button button-ghost" href="/api/documents/${encodeURIComponent(firstRulebook.id)}/file" target="_blank" rel="noopener noreferrer">Apri regolamento</a>` : ""}
            </div>
            <p id="gameDiscoveryStatus" hidden></p>
            <div class="game-document-list visually-hidden" id="gameDocumentList" aria-hidden="true">
              ${documentItems.map(documentCard).join("")}
            </div>

            <section class="rag-panel rag-panel-secondary simple-rag" id="ragPanel" data-index-busy="false">
              <div class="rag-heading-row">
                <h3>Fai una domanda sul regolamento</h3>
                <div class="rag-index-line">
                  <span class="rag-index-status" id="ragIndexStatus" role="status">Controllo indicizzazione…</span>
                  <button class="button button-ghost rag-prepare-index" type="button" hidden
                          ${documentItems.length ? "" : "disabled"}>Riprova indicizzazione</button>
                </div>
              </div>
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
                <div class="rag-empty">Le risposte useranno il regolamento archiviato.</div>
              </div>
            </section>
          </section>

          <details class="game-section technical-game-details">
            <summary><span><strong>Altri dati BGG</strong><small>Informazioni secondarie</small></span></summary>
            <div class="technical-game-content">
              <div class="fact-grid">
                ${fact("Dipendenza lingua", bgg.language_dependence || "—")}
                ${fact("Ranking BGG", bgg.rank ? `#${formatNumber(bgg.rank, 0)}` : "—")}
                ${fact("Numero possessori BGG", bgg.num_owned ? formatNumber(bgg.num_owned, 0) : "—")}
              </div>
            </div>
          </details>
        </article>
      </section>
    `;

    const openCopy = () => openCopyEditor(game.bgg_id, game.title);
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
        showToast(next ? "Gioco aggiunto alla Sala dei trofei." : "Gioco rimosso dai completati.");
        await renderDetail(game.bgg_id);
      } catch (error) {
        showToast(error.message, true);
        button.disabled = false;
      }
    });
    document.querySelector("#addPhysicalCopy")?.addEventListener("click", openCopy);
    document.querySelector("#addPhysicalCopySecondary")?.addEventListener("click", openCopy);
    document.querySelectorAll(".edit-copy").forEach((button) => {
      button.addEventListener("click", () => {
        const copy = copyItems.find((item) => item.id === button.dataset.copyId);
        if (copy) openCopyEditor(game.bgg_id, game.title, copy);
      });
    });
    document.querySelector("#addDocument")?.addEventListener("click", () => {
      openDocumentDialog(game.bgg_id, game.title);
    });
    setupRagPanel(game.bgg_id, documentItems);
    setupGameDiscovery(game.bgg_id, game.title);
    ensureItalianDescription(game.bgg_id);

    document.title = `${game.title} · BoardGameCompanion`;
  } catch (error) {
    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
      <div class="empty">Impossibile caricare il gioco: ${escapeHtml(error.message)}</div>
    `;
    showToast(error.message, true);
  }
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
    const knownSourceMiss = completed && candidates === 0;
    button.dataset.mode = knownSourceMiss ? "google" : "discovery";
    button.dataset.googleUrl = googleUrl;
    if (knownSourceMiss) {
      button.textContent = "Cerca PDF su Google ↗";
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
      status.textContent = `PDF archiviati: ${stored.length} (${italian.length} IT; ${fetched.length} acquisiti automaticamente) · Fonti trovate: ${candidates} · Errori di ricerca: ${failures} · Ultima ricerca: ${item.last_finished_at || "mai"}.`;
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

    button.disabled = true;
    button.textContent = "Ricerca delle fonti note…";
    try {
      const result = await api(`/api/games/${bggId}/rulebook-discovery/run`, {method: "POST"});
      const found = Number(result.candidates_found || 0);
      const failures = Number(result.provider_failures || 0);
      const approved = (result.review_items || []).filter((value) => value.status === "approved").length;
      const pending = (result.review_items || []).filter((value) => value.status === "pending").length;
      if (found) {
        showToast(`Trovate ${found} fonti: ${approved} approvate, ${pending} da verificare. Il download dei PDF è separato dalla ricerca.`);
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
          <div><p class="eyebrow">Regolamenti</p><h1>Ricerca regolamenti</h1>
          <p class="muted">Controlla la copertura delle fonti note per il catalogo. Italiano prima di inglese; ogni candidato continua a passare dalla policy di fiducia.</p></div>
          <button class="button button-primary" id="runDiscoveryBatch" type="button">Cerca su 5 giochi</button>
        </div>
        <div class="update-list">
          ${data.items.map((item) => `<article class="update-card">
            <div><strong>${escapeHtml(item.title)}</strong> <span class="badge">BGG #${item.bgg_id}</span></div>
            <p class="muted">${escapeHtml(item.status)} · ultimo: ${escapeHtml(item.last_finished_at || "mai")} · fonti trovate: ${item.candidates_found} · da verificare: ${item.review_items_created}</p>
            <p class="muted">${(item.providers || []).map((value) => `${escapeHtml(value.provider)}: ${escapeHtml(value.outcome)} (${value.candidate_count})`).join(" · ") || "Nessun provider ancora interrogato"}</p>
            ${item.last_error ? `<p class="integration-error">${escapeHtml(item.last_error)}</p>` : ""}
            <a class="external-link" href="/games/${item.bgg_id}" data-nav>Apri gioco →</a>
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
            <p class="eyebrow">Regolamenti</p>
            <h1>Fonti da verificare</h1>
            <p class="muted">
              Decidi esplicitamente sulle fonti che non possono essere considerate attendibili in automatico.
            </p>
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
            <p class="eyebrow">Regolamenti</p>
            <h1>Aggiornamenti regolamenti</h1>
            <p class="muted">
              Le fonti già approvate vengono ricontrollate in sicurezza.
              Una nuova versione viene archiviata solo quando cambia davvero il PDF.
            </p>
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



function openCatalogAssistant() {
  catalogAssistantResult.innerHTML =
    '<p class="muted">Le raccomandazioni vengono scelte esclusivamente tra i giochi posseduti nel catalogo.</p>';
  catalogAssistantQuestion.value = "";
  catalogAssistantDialog.showModal();
  window.setTimeout(() => catalogAssistantQuestion.focus(), 0);
}

function closeCatalogAssistantDialog() {
  if (!askCatalogAssistant.disabled && catalogAssistantDialog.open) {
    catalogAssistantDialog.close();
  }
}

function renderCatalogAssistantResult(payload) {
  const recommendations = payload.recommendations || [];
  catalogAssistantResult.innerHTML = `
    <div class="assistant-answer">
      <p>${escapeHtml(payload.answer || "")}</p>
    </div>
    ${recommendations.length ? `
      <div class="assistant-recommendations">
        ${recommendations.map((item) => `
          <a class="assistant-game-card" href="/games/${encodeURIComponent(item.bgg_id)}" data-nav>
            <span class="assistant-game-title">
              <strong>${escapeHtml(item.title)}</strong>
              <small>${item.best_players ? `Ideale: ${escapeHtml(item.best_players)}` : "Gioco posseduto"}</small>
            </span>
            <span class="assistant-game-reason">${escapeHtml(item.reason)}</span>
            <span class="assistant-game-meta">
              ${item.rating ? `★ ${formatNumber(item.rating, 1)}` : ""}
              ${item.weight ? ` · peso ${formatNumber(item.weight, 1)}` : ""}
            </span>
          </a>
        `).join("")}
      </div>
    ` : '<p class="muted">Nessun titolo del catalogo soddisfa abbastanza bene la richiesta.</p>'}
    <small class="assistant-provider">Provider: ${escapeHtml(payload.provider || "AI")} · ${escapeHtml(payload.model || "")}</small>
  `;
}

async function submitCatalogAssistant() {
  const query = catalogAssistantQuestion.value.trim();
  if (!query || askCatalogAssistant.disabled) return;
  askCatalogAssistant.disabled = true;
  askCatalogAssistant.textContent = "Sto scegliendo…";
  catalogAssistantResult.innerHTML = '<div class="assistant-thinking">Analizzo la tua ludoteca…</div>';
  try {
    const payload = await api("/api/catalog/assistant", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query}),
    });
    renderCatalogAssistantResult(payload);
  } catch (error) {
    catalogAssistantResult.innerHTML =
      `<div class="integration-error">${escapeHtml(error.message)}</div>`;
  } finally {
    askCatalogAssistant.disabled = false;
    askCatalogAssistant.textContent = "Chiedi all'AI";
  }
}

function browseGameRow(game, index) {
  const rank = game.bgg?.rank && Number(game.bgg.rank) > 0 ? `#${formatNumber(game.bgg.rank, 0)}` : "—";
  return `
    <a class="browse-game-row" href="/games/${encodeURIComponent(game.bgg_id)}" data-nav>
      <span class="browse-rank">${index !== null ? index : rank}</span>
      <span class="browse-cover">
        ${game.bgg_metadata?.cover_url
          ? `<img src="${escapeHtml(game.bgg_metadata.cover_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
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

function rankingParams() {
  const params = new URLSearchParams({
    mode: rankingState.mode,
    limit: "50",
  });
  for (const [key, value] of [
    ["category", rankingState.category],
    ["mechanic", rankingState.mechanic],
    ["ideal_players", rankingState.idealPlayers],
    ["max_minutes", rankingState.maxMinutes],
    ["weight", rankingState.weight],
  ]) {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  }
  return params;
}

function rankingModeButtons() {
  const group = rankingGroups[rankingState.group] || rankingGroups.top;
  return group.modes.map(([mode, label]) => `
    <button class="ranking-mode-button ${rankingState.mode === mode ? "is-active" : ""}"
            type="button" data-ranking-mode="${mode}">
      ${escapeHtml(label)}
    </button>
  `).join("");
}

function rankingGameSummary(game) {
  const categories = Array.isArray(game.bgg_metadata?.categories)
    ? game.bgg_metadata.categories.filter(Boolean).slice(0, 2)
    : [];
  const mechanics = Array.isArray(game.bgg_metadata?.mechanics)
    ? game.bgg_metadata.mechanics.filter(Boolean).slice(0, 2)
    : [];

  const weight = Number(game.bgg?.average_weight);
  let complexity = "";
  if (Number.isFinite(weight) && weight > 0) {
    if (weight <= 1.8) complexity = "molto accessibile";
    else if (weight <= 2.6) complexity = "complessità leggera";
    else if (weight <= 3.4) complexity = "complessità media";
    else if (weight <= 4.1) complexity = "impegnativo";
    else complexity = "molto impegnativo";
  }

  const parts = [];
  if (categories.length) parts.push(categories.join(" / "));
  if (mechanics.length) parts.push(mechanics.join(" + "));
  if (complexity) parts.push(complexity);

  if (!parts.length) {
    const fallback = [];
    if (playerText(game) !== "—") fallback.push(`${playerText(game)} giocatori`);
    if (timeText(game) !== "—") fallback.push(timeText(game));
    return fallback.join(" · ") || "Caratteristiche non ancora disponibili";
  }
  return parts.join(" · ");
}

function rankingGameRow(item, index) {
  const game = item.game;
  const cover = game.bgg_metadata?.cover_url
    ? `<img src="${escapeHtml(game.bgg_metadata.cover_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : `<span>${escapeHtml(initials(game.title))}</span>`;
  const factors = (item.factors || []).map(
    (factor) => `<span>${escapeHtml(factor)}</span>`
  ).join("");
  const rating = game.bgg?.average
    ? `★ ${formatNumber(game.bgg.average, 1)}`
    : "BGG —";
  return `
    <a class="ranking-result-row ${index <= 3 ? `is-podium podium-${index}` : ""}" href="/games/${encodeURIComponent(game.bgg_id)}" data-nav>
      <span class="ranking-result-position">#${index}</span>
      <span class="ranking-result-cover">${cover}</span>
      <span class="ranking-result-body">
        <span class="ranking-result-title">
          <strong>${escapeHtml(game.title)}</strong>
          <small>${escapeHtml(playerText(game))} gioc. · ${escapeHtml(timeText(game))} · ${rating}</small>
        </span>
        <span class="ranking-result-summary">${escapeHtml(rankingGameSummary(game))}</span>
        <span class="ranking-result-factors">${factors}</span>
      </span>
      <span class="ranking-result-score" title="${escapeHtml(item.reason || "Criterio della classifica")}">
        <strong>${formatNumber(item.score, 1)}</strong>
        <small>score</small>
      </span>
    </a>
  `;
}

function rankingSelectOptions(items, selected, placeholder) {
  return `
    <option value="">${escapeHtml(placeholder)}</option>
    ${items.map((item) => `
      <option value="${escapeHtml(item.name)}"
              ${selected === item.name ? "selected" : ""}>
        ${escapeHtml(item.name)} (${formatNumber(item.count, 0)})
      </option>
    `).join("")}
  `;
}

function rankingFilterMarkup(facets) {
  return `
    <div class="ranking-filter-head">
      <div>
        <p class="eyebrow">Affina</p>
        <h2>Contesto</h2>
      </div>
      <span class="quiet-pill">Facoltativo</span>
    </div>
    <p class="muted ranking-filter-intro">
      I filtri non cambiano la formula: restringono il tavolo su cui la classifica viene calcolata.
    </p>

    <section class="ranking-filter-group">
      <strong>Giocatori ideali</strong>
      <div class="ranking-filter-chips">
        ${["", "1", "2", "3", "4", "5", "6"].map((value) => `
          <button class="ranking-filter-chip ${rankingState.idealPlayers === value ? "is-active" : ""}"
                  type="button" data-ranking-filter="idealPlayers" data-ranking-value="${value}">
            ${value ? (value === "6" ? "6+" : value) : "Tutti"}
          </button>
        `).join("")}
      </div>
    </section>

    <section class="ranking-filter-group">
      <strong>Durata massima</strong>
      <div class="ranking-filter-chips">
        ${[
          ["", "Tutte"], ["30", "30 min"], ["60", "60 min"],
          ["90", "90 min"], ["120", "2 h"], ["180", "3 h"],
        ].map(([value, label]) => `
          <button class="ranking-filter-chip ${rankingState.maxMinutes === value ? "is-active" : ""}"
                  type="button" data-ranking-filter="maxMinutes" data-ranking-value="${value}">
            ${label}
          </button>
        `).join("")}
      </div>
    </section>

    <section class="ranking-filter-group">
      <strong>Complessità</strong>
      <div class="ranking-filter-chips">
        ${[
          ["", "Tutte"], ["light", "Semplice"],
          ["medium", "Media"], ["heavy", "Impegnativa"],
        ].map(([value, label]) => `
          <button class="ranking-filter-chip ${rankingState.weight === value ? "is-active" : ""}"
                  type="button" data-ranking-filter="weight" data-ranking-value="${value}">
            ${label}
          </button>
        `).join("")}
      </div>
    </section>

    <label class="ranking-filter-field">
      <span>Genere</span>
      <select id="rankingCategory">
        ${rankingSelectOptions(facets.categories || [], rankingState.category, "Tutti i generi")}
      </select>
    </label>

    <label class="ranking-filter-field">
      <span>Meccanica</span>
      <select id="rankingMechanic">
        ${rankingSelectOptions(facets.mechanics || [], rankingState.mechanic, "Tutte le meccaniche")}
      </select>
    </label>

    <button class="button button-ghost ranking-reset-filters" id="rankingResetFilters" type="button">
      Azzera filtri
    </button>
  `;
}

function bindRankingControls() {
  document.querySelectorAll("[data-ranking-group]").forEach((button) => {
    button.onclick = () => {
      rankingState.group = button.dataset.rankingGroup;
      const group = rankingGroups[rankingState.group] || rankingGroups.top;
      if (!group.modes.some(([mode]) => mode === rankingState.mode)) {
        rankingState.mode = group.modes[0][0];
      }
      renderRankings();
    };
  });

  document.querySelectorAll("[data-ranking-mode]").forEach((button) => {
    button.onclick = () => {
      rankingState.mode = button.dataset.rankingMode;
      refreshRankings();
    };
  });

  document.querySelectorAll("[data-ranking-filter]").forEach((button) => {
    button.onclick = () => {
      rankingState[button.dataset.rankingFilter] = button.dataset.rankingValue || "";
      refreshRankings();
    };
  });

  const category = document.querySelector("#rankingCategory");
  if (category) {
    category.onchange = (event) => {
      rankingState.category = event.target.value;
      refreshRankings();
    };
  }
  const mechanic = document.querySelector("#rankingMechanic");
  if (mechanic) {
    mechanic.onchange = (event) => {
      rankingState.mechanic = event.target.value;
      refreshRankings();
    };
  }
  const reset = document.querySelector("#rankingResetFilters");
  if (reset) {
    reset.onclick = () => {
      rankingState.category = "";
      rankingState.mechanic = "";
      rankingState.idealPlayers = "";
      rankingState.maxMinutes = "";
      rankingState.weight = "";
      renderRankings();
    };
  }
}

async function refreshRankings() {
  rankingRequestController?.abort();
  const controller = new AbortController();
  rankingRequestController = controller;
  const results = document.querySelector("#rankingResults");
  const heading = document.querySelector("#rankingCurrentHeading");
  const description = document.querySelector("#rankingCurrentDescription");
  const count = document.querySelector("#rankingResultCount");
  if (!results || !heading || !description || !count) return;

  results.classList.add("is-refreshing");
  results.setAttribute("aria-busy", "true");
  try {
    const payload = await api(`/api/catalog/rankings?${rankingParams()}`, {
      signal: controller.signal,
    });
    if (controller.signal.aborted || !document.querySelector("#rankingResults")) return;
    heading.textContent = payload.title;
    description.textContent = payload.description;
    count.textContent = payload.total === 1
      ? "1 gioco classificato"
      : `${formatNumber(payload.total, 0)} giochi classificati`;
    results.innerHTML = payload.items.length
      ? payload.items.map((item, index) => rankingGameRow(item, index + 1)).join("")
      : '<div class="empty">Nessun gioco soddisfa questa classifica e i filtri selezionati.</div>';

    document.querySelector("#rankingModes").innerHTML = rankingModeButtons();
    document.querySelector("#rankingFilters").innerHTML = rankingFilterMarkup(
      rankingFacetsCache || {categories: [], mechanics: []}
    );
    bindRankingControls();
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

async function renderRankings() {
  app.innerHTML = `
    <section class="page-header browse-header rankings-header">
      <div>
        <p class="eyebrow">Ludoteca</p>
        <h1>Classifiche</h1>
        <p class="page-lead">
          Graduatorie deterministiche e spiegabili: il rating BGG è solo uno degli ingredienti.
        </p>
      </div>
      <div class="ranking-result-count" id="rankingResultCount">— giochi classificati</div>
    </section>

    <nav class="ranking-groups" aria-label="Famiglie di classifiche">
      ${Object.entries(rankingGroups).map(([key, group]) => `
        <button class="ranking-group-button ${rankingState.group === key ? "is-active" : ""}"
                type="button" data-ranking-group="${key}">
          ${escapeHtml(group.label)}
        </button>
      `).join("")}
    </nav>

    <section class="rankings-layout">
      <div class="rankings-main">
        <div class="ranking-mode-strip" id="rankingModes">${rankingModeButtons()}</div>
        <header class="ranking-current-head">
          <div>
            <p class="eyebrow">Algoritmo attivo</p>
            <h2 id="rankingCurrentHeading">Classifica</h2>
            <p class="muted" id="rankingCurrentDescription"></p>
          </div>
          <span class="ranking-explainer-badge">0–100</span>
        </header>
        <div class="ranking-results" id="rankingResults">${skeletons()}</div>
      </div>

      <aside class="ranking-filter-panel" id="rankingFilters" aria-label="Filtri classifica">
        ${skeletons()}
      </aside>
    </section>
  `;

  document.title = "Classifiche · BoardGameCompanion";
  bindRankingControls();

  try {
    if (!rankingFacetsCache) {
      rankingFacetsCache = await api("/api/catalog/facets?limit=100");
    }
    const filters = document.querySelector("#rankingFilters");
    if (filters) filters.innerHTML = rankingFilterMarkup(rankingFacetsCache);
    bindRankingControls();
    await refreshRankings();
  } catch (error) {
    const results = document.querySelector("#rankingResults");
    if (results) results.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function completionAchievementMarkup(game) {
  const achievements = [{icon: "♛", label: "Completato"}];
  const weight = Number(game.bgg?.average_weight || 0);
  const minutes = Number(
    game.play_time?.max || game.play_time?.playing || game.play_time?.min || 0
  );
  if (weight >= 3.5) achievements.push({icon: "◆", label: "Impresa"});
  if (minutes >= 120) achievements.push({icon: "⌛", label: "Maratona"});
  return achievements.map((item) =>
    `<span class="trophy-achievement"><i aria-hidden="true">${item.icon}</i>${escapeHtml(item.label)}</span>`
  ).join("");
}

function trophyGameCard(game, {compact = false} = {}) {
  const cover = game.bgg_metadata?.cover_url
    ? `<img src="${escapeHtml(game.bgg_metadata.cover_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : `<span class="trophy-cover-fallback">${escapeHtml(initials(game.title))}</span>`;
  const completedAt = game.progress?.completed_at
    ? new Date(game.progress.completed_at + "T12:00:00").toLocaleDateString("it-IT", {
        year: "numeric", month: "short", day: "numeric",
      })
    : null;
  return `
    <a class="trophy-card ${compact ? "is-compact" : ""}"
       href="/games/${encodeURIComponent(game.bgg_id)}" data-nav>
      <span class="trophy-crown" aria-hidden="true">♛</span>
      <span class="trophy-cover">${cover}</span>
      <span class="trophy-card-body">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${completedAt ? `Registrato il ${escapeHtml(completedAt)}` : "Completato"}</small>
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
      "/api/games?owned=true&item_type=standalone&completed=true&sort=completed_desc&limit=4&offset=0"
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

async function renderCompleted() {
  app.innerHTML = `
    <section class="trophy-hero">
      <div>
        <p class="eyebrow">La mia ludoteca</p>
        <h1>Sala dei trofei</h1>
        <p class="page-lead">
          I giochi che hai portato fino in fondo. Nessun punteggio: solo traguardi personali.
        </p>
      </div>
      <span class="trophy-hero-mark" aria-hidden="true">♛</span>
    </section>
    <section class="trophy-wall" id="trophyWall">${skeletons()}</section>
  `;
  try {
    const payload = await api(
      "/api/games?owned=true&item_type=standalone&completed=true&sort=completed_desc&limit=250&offset=0"
    );
    const target = document.querySelector("#trophyWall");
    if (!target) return;
    target.innerHTML = payload.items.length
      ? payload.items.map((game) => trophyGameCard(game)).join("")
      : `<div class="empty trophy-empty">
          <strong>La Sala dei trofei è ancora vuota.</strong>
          <span>Apri la scheda di un gioco e usa “Segna completato” quando vuoi esporlo qui.</span>
        </div>`;
    document.title = "Completati · BoardGameCompanion";
  } catch (error) {
    document.querySelector("#trophyWall").innerHTML =
      `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function exploreFacetMosaic(item, kind) {
  const covers = Array.isArray(item.covers) ? item.covers.slice(0, 4) : [];
  const icon = kind === "category" ? "◫" : "⌘";
  if (!covers.length) {
    return `<div class="explore-facet-mosaic is-empty" aria-hidden="true">
      <span>${icon}</span>
    </div>`;
  }
  return `<div class="explore-facet-mosaic has-${covers.length}" aria-hidden="true">
    ${covers.map((url) =>
      `<img src="${escapeHtml(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    ).join("")}
  </div>`;
}

function exploreFacetCard(item, kind) {
  const selected = Boolean(item.selected);
  return `
    <button class="explore-facet-card ${selected ? "is-selected" : ""}" type="button"
            data-explore-kind="${kind}" data-explore-name="${escapeHtml(item.name)}"
            aria-pressed="${selected ? "true" : "false"}">
      <span class="explore-facet-count">${formatNumber(item.count, 0)} giochi</span>
      ${exploreFacetMosaic(item, kind)}
      <span class="explore-facet-label">
        <strong>${escapeHtml(item.name)}</strong>
        <small>${kind === "category" ? "Genere" : "Meccanica"}${selected ? " · selezionata" : ""}</small>
      </span>
      <span class="explore-facet-check" aria-hidden="true">${selected ? "✓" : "+"}</span>
    </button>
  `;
}

function exploreParams() {
  const params = new URLSearchParams({
    limit: exploreState.expandedResults ? "250" : "12",
  });
  [...exploreState.categories].forEach((value) => params.append("category", value));
  [...exploreState.mechanics].forEach((value) => params.append("mechanic", value));
  for (const [key, value] of [
    ["supports_players", exploreState.supportsPlayers],
    ["ideal_players", exploreState.idealPlayers],
    ["player_age", exploreState.playerAge],
    ["weight", exploreState.weight],
    ["max_minutes", exploreState.maxMinutes],
    ["min_rating", exploreState.minRating],
  ]) {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  }
  return params;
}

function exploreSelectionChips() {
  const chips = [
    ...[...exploreState.categories].map((name) => ({kind: "category", name, label: "Genere"})),
    ...[...exploreState.mechanics].map((name) => ({kind: "mechanic", name, label: "Meccanica"})),
  ];
  if (!chips.length) {
    return '<span class="explore-selection-empty">Nessun genere o meccanica selezionati.</span>';
  }
  return chips.map((item) => `
    <button class="explore-selection-chip" type="button"
            data-explore-remove-kind="${item.kind}" data-explore-remove-name="${escapeHtml(item.name)}">
      <small>${item.label}</small><strong>${escapeHtml(item.name)}</strong><span aria-hidden="true">×</span>
    </button>
  `).join("");
}

const exploreOptionalGroups = [
  {
    apiKey: "supports_players",
    stateKey: "supportsPlayers",
    title: "Giocatori",
    hint: "Il gioco supporta questo numero di giocatori.",
  },
  {
    apiKey: "ideal_players",
    stateKey: "idealPlayers",
    title: "Ideale in",
    hint: "Valore “best/recommended players” BGG.",
  },
  {
    apiKey: "player_age",
    stateKey: "playerAge",
    title: "Età giocatore",
    hint: "Età minima consigliata BGG compatibile.",
  },
  {
    apiKey: "max_minutes",
    stateKey: "maxMinutes",
    title: "Durata",
    hint: "Durata massima della partita in minuti.",
  },
  {
    apiKey: "weight",
    stateKey: "weight",
    title: "Complessità",
    hint: "Peso medio BGG.",
  },
  {
    apiKey: "min_rating",
    stateKey: "minRating",
    title: "Rating BGG",
    hint: "Valutazione media minima.",
  },
];

function exploreOptionalGroup(group, options) {
  const current = String(exploreState[group.stateKey] || "");
  if (!Array.isArray(options) || !options.length) {
    return `
      <section class="explore-option-group is-empty">
        <div class="explore-option-heading">
          <strong>${escapeHtml(group.title)}</strong>
          <small>${escapeHtml(group.hint)}</small>
        </div>
        <span class="explore-option-none">Nessuna opzione compatibile</span>
      </section>
    `;
  }
  return `
    <section class="explore-option-group">
      <div class="explore-option-heading">
        <strong>${escapeHtml(group.title)}</strong>
        <small>${escapeHtml(group.hint)}</small>
      </div>
      <div class="explore-option-buttons">
        ${options.map((option) => {
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
        }).join("")}
      </div>
    </section>
  `;
}

function renderExploreOptionalFilters(payload) {
  const container = document.querySelector("#exploreFilterOptions");
  if (!container) return;
  const options = payload.options || {};
  container.innerHTML = exploreOptionalGroups
    .map((group) => exploreOptionalGroup(group, options[group.apiKey] || []))
    .join("");

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

function renderExplorePayload(payload) {
  currentExplorePayload = payload;
  const allTabItems = exploreState.activeTab === "category"
    ? payload.categories || []
    : payload.mechanics || [];
  const showRare = Boolean(exploreState.showRareFacets[exploreState.activeTab]);
  const rareItems = allTabItems.filter(
    (item) => Number(item.count) <= 1 && !item.selected
  );
  const tabItems = showRare
    ? allTabItems
    : allTabItems.filter((item) => Number(item.count) > 1 || item.selected);
  const selectedCount = exploreState.categories.size + exploreState.mechanics.size;
  const visibleGames = exploreState.expandedResults
    ? (payload.games || [])
    : (payload.games || []).slice(0, 12);

  const selections = document.querySelector("#exploreSelections");
  const facets = document.querySelector("#exploreFacetGrid");
  const facetSummary = document.querySelector("#exploreFacetSummary");
  const rareToggle = document.querySelector("#exploreRareToggle");
  const resultCount = document.querySelector("#exploreResultCount");
  const resultGrid = document.querySelector("#exploreResultGrid");
  const resultMore = document.querySelector("#exploreResultMore");
  if (
    !selections || !facets || !facetSummary || !rareToggle
    || !resultCount || !resultGrid || !resultMore
  ) return;

  selections.innerHTML = `
    <div class="explore-selection-chips">${exploreSelectionChips()}</div>
    ${selectedCount ? '<button class="button button-ghost explore-clear-selections" id="exploreClearSelections" type="button">Azzera selezioni</button>' : ""}
  `;

  facets.innerHTML = tabItems.length
    ? tabItems.map((item) => exploreFacetCard(item, exploreState.activeTab)).join("")
    : '<div class="empty explore-empty-facets">Nessun altro criterio compatibile con la selezione corrente.</div>';

  const facetLabel = exploreState.activeTab === "category" ? "generi" : "meccaniche";
  facetSummary.textContent = `${formatNumber(tabItems.length, 0)} ${facetLabel} mostrati`;
  rareToggle.hidden = rareItems.length === 0;
  rareToggle.textContent = showRare
    ? "Nascondi rari"
    : `Mostra tutti (+${formatNumber(rareItems.length, 0)})`;
  rareToggle.setAttribute("aria-pressed", showRare ? "true" : "false");
  rareToggle.onclick = () => {
    exploreState.showRareFacets[exploreState.activeTab] = !showRare;
    renderExplorePayload(payload);
  };

  resultCount.textContent = Number(payload.total) === 1
    ? "1 gioco corrispondente"
    : `${formatNumber(payload.total, 0)} giochi corrispondenti`;
  resultGrid.innerHTML = visibleGames.length
    ? visibleGames.map((game) => gameCard(game, [])).join("")
    : '<div class="empty catalog-empty">Nessun gioco soddisfa contemporaneamente tutti i criteri.</div>';

  const hiddenCount = Math.max(0, Number(payload.total || 0) - visibleGames.length);
  resultMore.hidden = hiddenCount === 0 && !exploreState.expandedResults;
  resultMore.textContent = exploreState.expandedResults
    ? "Mostra meno"
    : `Mostra altri ${hiddenCount}`;

  renderExploreOptionalFilters(payload);

  document.querySelectorAll("[data-explore-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.exploreKind === "category"
        ? exploreState.categories
        : exploreState.mechanics;
      const name = button.dataset.exploreName;
      if (target.has(name)) target.delete(name);
      else target.add(name);
      exploreState.expandedResults = false;
      refreshExplore();
    });
  });

  document.querySelectorAll("[data-explore-remove-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.exploreRemoveKind === "category"
        ? exploreState.categories
        : exploreState.mechanics;
      target.delete(button.dataset.exploreRemoveName);
      exploreState.expandedResults = false;
      refreshExplore();
    });
  });

  document.querySelector("#exploreClearSelections")?.addEventListener("click", () => {
    exploreState.categories.clear();
    exploreState.mechanics.clear();
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
  const facets = document.querySelector("#exploreFacetGrid");
  const resultGrid = document.querySelector("#exploreResultGrid");
  if (!facets || !resultGrid) return;

  exploreRequestController?.abort();
  const controller = new AbortController();
  exploreRequestController = controller;
  const layout = document.querySelector(".explore-layout");
  layout?.classList.add("is-refreshing");
  layout?.setAttribute("aria-busy", "true");
  if (!currentExplorePayload) {
    facets.innerHTML = skeletons();
    resultGrid.innerHTML = skeletons();
  }

  try {
    const payload = await api(`/api/catalog/explore?${exploreParams()}`, {signal: controller.signal});
    if (controller.signal.aborted || !document.querySelector("#exploreFacetGrid")) return;
    renderExplorePayload(payload);
  } catch (error) {
    if (error.name === "AbortError") return;
    facets.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
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
  document.querySelectorAll("[data-explore-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      exploreState.activeTab = button.dataset.exploreTab;
      document.querySelectorAll("[data-explore-tab]").forEach((item) => {
        const active = item.dataset.exploreTab === exploreState.activeTab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (currentExplorePayload) renderExplorePayload(currentExplorePayload);
    });
  });

  document.querySelector("#exploreResetOptional")?.addEventListener("click", () => {
    for (const key of ["supportsPlayers", "idealPlayers", "playerAge", "weight", "maxMinutes", "minRating"]) {
      exploreState[key] = "";
    }
    exploreState.expandedResults = false;
    renderExplore();
  });
}

async function renderExplore(initialTab = null) {
  currentExplorePayload = null;
  if (initialTab === "category" || initialTab === "mechanic") {
    exploreState.activeTab = initialTab;
  }
  app.innerHTML = `
    <section class="page-header browse-header explore-page-header">
      <div>
        <p class="eyebrow">Ludoteca</p>
        <h1>Esplora</h1>
        <p class="page-lead">Combina liberamente generi, meccaniche e parametri di gioco. Ogni scelta restringe l'intersezione dei titoli posseduti.</p>
      </div>
      <div class="explore-header-result">
        <strong id="exploreResultCount">— giochi corrispondenti</strong>
        <small>Solo giochi base posseduti</small>
      </div>
    </section>

    <section class="explore-layout">
      <div class="explore-main">
        <section class="explore-selection-bar" id="exploreSelections" aria-label="Criteri selezionati"></section>

        <div class="explore-tabs" role="tablist" aria-label="Tipo di criterio">
          <button class="explore-tab ${exploreState.activeTab === "category" ? "is-active" : ""}"
                  type="button" role="tab" data-explore-tab="category"
                  aria-selected="${exploreState.activeTab === "category" ? "true" : "false"}">Generi</button>
          <button class="explore-tab ${exploreState.activeTab === "mechanic" ? "is-active" : ""}"
                  type="button" role="tab" data-explore-tab="mechanic"
                  aria-selected="${exploreState.activeTab === "mechanic" ? "true" : "false"}">Meccaniche</button>
        </div>

        <div class="explore-facet-toolbar">
          <span id="exploreFacetSummary" class="muted"></span>
          <button class="button button-ghost explore-rare-toggle" id="exploreRareToggle"
                  type="button" aria-pressed="false" hidden>Mostra tutti</button>
        </div>
        <section class="explore-facet-grid" id="exploreFacetGrid" aria-live="polite">${skeletons()}</section>

        <section class="explore-results-section" aria-labelledby="exploreGamesTitle">
          <div class="explore-results-head">
            <div>
              <p class="eyebrow">Intersezione</p>
              <h2 id="exploreGamesTitle">Giochi corrispondenti</h2>
            </div>
            <button class="button button-ghost" id="exploreResultMore" type="button" hidden>Mostra altri</button>
          </div>
          <div class="catalog-results catalog-results-cards explore-result-grid" id="exploreResultGrid">${skeletons()}</div>
        </section>
      </div>

      <aside class="explore-filter-panel" aria-label="Parametri facoltativi">
        <div class="explore-filter-head">
          <div><p class="eyebrow">Affina</p><h2>Altri parametri</h2></div>
          <span class="quiet-pill">Facoltativi</span>
        </div>
        <p class="muted explore-filter-intro">Le opzioni si aggiornano in base alla selezione corrente: non vengono proposti valori che porterebbero a zero giochi.</p>

        <div class="explore-filter-options" id="exploreFilterOptions">
          ${skeletons()}
        </div>
        <button class="button button-ghost explore-reset-optional" id="exploreResetOptional" type="button">Azzera parametri</button>
      </aside>
    </section>
  `;

  bindExploreControls();
  document.title = "Esplora · BoardGameCompanion";
  await refreshExplore();
}

async function route() {
  catalogRequestController?.abort();
  exploreRequestController?.abort();
  rankingRequestController?.abort();
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
  if (/^\/rankings\/?$/.test(window.location.pathname)) {
    await renderRankings();
    return;
  }
  if (/^\/completed\/?$/.test(window.location.pathname)) {
    await renderCompleted();
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
  if (catalogAssistantDialog?.open && link.closest("#catalogAssistantDialog")) catalogAssistantDialog.close();
  history.pushState({}, "", url.pathname);
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
  if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
    closeSidebar();
  }
});

scannerButton.addEventListener("click", () => {
  closeSidebar();
  openScannerDialog();
});
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
settingsTabs.forEach((tab) => {
  tab.addEventListener("click", () => setSettingsTab(tab.dataset.settingsTab));
});

catalogAssistantButton?.addEventListener("click", () => {
  closeSidebar();
  openCatalogAssistant();
});
catalogAssistantForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitCatalogAssistant();
});
closeCatalogAssistant?.addEventListener("click", closeCatalogAssistantDialog);
cancelCatalogAssistant?.addEventListener("click", closeCatalogAssistantDialog);
catalogAssistantDialog?.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeCatalogAssistantDialog();
});
document.querySelectorAll("[data-assistant-example]").forEach((button) => {
  button.addEventListener("click", () => {
    if (!catalogAssistantQuestion) return;
    catalogAssistantQuestion.value = button.dataset.assistantExample || "";
    catalogAssistantQuestion.focus();
  });
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

importButton.addEventListener("click", () => {
  closeSidebar();
  resetImportDialog();
  importDialog.showModal();
});
importSidebarButton?.addEventListener("click", () => {
  closeSidebar();
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
