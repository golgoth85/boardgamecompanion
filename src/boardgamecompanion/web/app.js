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
const settingsDialog = document.querySelector("#settingsDialog");
const settingsButton = document.querySelector("#settingsButton");
const settingsForm = document.querySelector("#settingsForm");
const closeSettings = document.querySelector("#closeSettings");
const cancelSettings = document.querySelector("#cancelSettings");
const saveSettings = document.querySelector("#saveSettings");
const saveTestSettings = document.querySelector("#saveTestSettings");
const floppyUrl = document.querySelector("#floppyUrl");
const floppyApiKey = document.querySelector("#floppyApiKey");
const floppyTimeout = document.querySelector("#floppyTimeout");
const floppyVerifyTls = document.querySelector("#floppyVerifyTls");
const floppyClearToken = document.querySelector("#floppyClearToken");
const clearTokenRow = document.querySelector("#clearTokenRow");
const floppyUrlHint = document.querySelector("#floppyUrlHint");
const floppyTokenHint = document.querySelector("#floppyTokenHint");
const floppyTimeoutHint = document.querySelector("#floppyTimeoutHint");
const settingsResult = document.querySelector("#settingsResult");
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
let settingsBusy = false;
let currentFloppySettings = null;
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
let documentBusy = false;
let documentBggId = null;

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
  saveSettings.textContent = busy ? "Salvataggio…" : "Salva";
  saveTestSettings.textContent = busy ? "Verifica…" : "Salva e verifica";
}

function closeSettingsDialog() {
  if (!settingsBusy && settingsDialog.open) {
    settingsDialog.close();
  }
}

function applyFloppySettingsToForm(data) {
  currentFloppySettings = data;
  floppyUrl.value = data.url || "";
  floppyApiKey.value = "";
  floppyTimeout.value = String(data.timeout_seconds ?? 45);
  floppyVerifyTls.checked = data.verify_tls !== false;
  floppyClearToken.checked = false;

  const overrides = data.overrides || {};
  floppyUrl.disabled = Boolean(overrides.url);
  floppyApiKey.disabled = Boolean(overrides.api_key);
  floppyTimeout.disabled = Boolean(overrides.timeout_seconds);
  floppyVerifyTls.disabled = Boolean(overrides.verify_tls);

  floppyUrlHint.textContent = overrides.url
    ? "Override attivo da variabile Docker."
    : "Salvato localmente in /config.";

  if (overrides.api_key) {
    floppyTokenHint.textContent = "Token configurato tramite variabile Docker.";
    clearTokenRow.hidden = true;
  } else if (data.api_key_configured) {
    floppyTokenHint.textContent = "Token configurato. Lascia vuoto per mantenerlo invariato.";
    clearTokenRow.hidden = false;
  } else {
    floppyTokenHint.textContent = "Nessun token configurato.";
    clearTokenRow.hidden = true;
  }

  floppyTimeoutHint.textContent = overrides.timeout_seconds
    ? "Override attivo da variabile Docker."
    : "Intervallo consentito: 1–60 secondi.";
}

async function openSettingsDialog() {
  settingsResult.hidden = true;
  settingsResult.textContent = "";
  setSettingsBusy(true);
  try {
    const data = await api("/api/settings/floppy");
    applyFloppySettingsToForm(data);
    settingsDialog.showModal();
  } catch (error) {
    settingsDialog.showModal();
    settingsResult.hidden = false;
    settingsResult.textContent = error.message;
  } finally {
    setSettingsBusy(false);
  }
}

async function persistFloppySettings({verifyAfter = false} = {}) {
  if (settingsBusy) return;
  setSettingsBusy(true);
  settingsResult.hidden = true;

  const payload = {
    url: floppyUrl.value.trim(),
    api_key: floppyApiKey.disabled || !floppyApiKey.value.trim()
      ? null
      : floppyApiKey.value.trim(),
    clear_api_key: !floppyClearToken.disabled && floppyClearToken.checked,
    timeout_seconds: Number(floppyTimeout.value || 45),
    verify_tls: floppyVerifyTls.checked,
  };

  try {
    const saved = await api("/api/settings/floppy", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    applyFloppySettingsToForm(saved);
    settingsResult.hidden = false;
    settingsResult.innerHTML = "<strong>Impostazioni salvate.</strong>";
    showToast("Impostazioni Floppy salvate.");

    if (verifyAfter) {
      const status = await api("/api/integrations/floppy/status");
      if (status.authenticated && status.boardgame_api) {
        const version = status.info?.version ? ` · versione ${escapeHtml(status.info.version)}` : "";
        settingsResult.innerHTML =
          `<strong>Connessione riuscita.</strong> API board game disponibile${version}.`;
      } else if (!status.configured) {
        settingsResult.textContent = "Configurazione incompleta: URL e token sono entrambi necessari.";
      } else {
        settingsResult.textContent =
          status.error?.message || "Floppy risponde, ma la verifica API non è riuscita.";
      }
    }

    if (document.querySelector("#floppyPanel")) {
      await loadFloppyStatus();
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
    showToast(created ? "Documento caricato." : "Documento già presente: nessun duplicato creato.");
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
    return "La fotocamera richiede HTTPS (oppure localhost). Usa l’inserimento manuale.";
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
  scannerForm.reset();
  lookupBarcode.disabled = false;
  lookupBarcode.textContent = "Cerca";
  scannerResult.innerHTML =
    '<p class="muted">Inquadra il barcode: il lookup parte automaticamente dopo la lettura.</p>';
  cameraSection.hidden = false;
  const cameraUsable = scannerCameraUsable();
  toggleCamera.disabled = !cameraUsable;
  scannerManualFallback.open = !cameraUsable;
  cameraHint.textContent = cameraUsable
    ? "La fotocamera partirà automaticamente."
    : scannerCameraErrorMessage();
}

function openScannerDialog() {
  resetScanner();
  scannerDialog.showModal();
  if (scannerCameraUsable()) {
    void startScannerCamera();
  } else {
    window.setTimeout(() => scannerBarcode.focus(), 0);
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
  `;
  scannerResult.querySelectorAll(".scanner-open-game").forEach((link) => {
    link.addEventListener("click", () => closeScannerDialog(), {once: true});
  });
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

async function assignBarcodeToCopy(copyId, barcode) {
  await api(`/api/copies/${encodeURIComponent(copyId)}`, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({barcode}),
  });
  scannerBarcode.value = barcode;
  showToast("Barcode assegnato alla copia.");
  await lookupScannerBarcode(barcode);
}

async function assignScannedBarcodeToGame(bggId, title, barcode) {
  scannerResult.innerHTML = '<p class="muted">Controllo copie fisiche…</p>';
  try {
    const copies = await api(`/api/games/${bggId}/copies`);
    const unbarcoded = (copies.items || []).filter((copy) => !copy.barcode_normalized);

    if (unbarcoded.length === 1) {
      await assignBarcodeToCopy(unbarcoded[0].id, barcode);
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
          void assignBarcodeToCopy(button.dataset.copyId, barcode);
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
      scannerBarcode.value = barcode;
      showToast("Nuova copia creata con il barcode.");
      await lookupScannerBarcode(barcode);
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
        scannerBarcode.value = barcode;
        showToast("Nuova copia creata.");
        await lookupScannerBarcode(barcode);
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

function gameCard(game) {
  const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
  const year = game.year_published || "—";
  const rating = game.bgg?.average ? `★ ${formatNumber(game.bgg.average, 1)}` : "★ —";
  const imageUrl = game.metadata?.image_url;
  return `
    <a class="game-card" href="/games/${game.bgg_id}" data-nav aria-label="Apri ${escapeHtml(game.title)}">
      <div class="cover">
        <span class="cover-initials">${escapeHtml(initials(game.title))}</span>
        ${imageUrl
          ? `<img class="cover-image" src="${escapeHtml(imageUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`
          : ""}
        <span class="badge card-badge">${type}</span>
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
          e arricchisci i metadata su richiesta attraverso Floppy senza rendere il catalogo dipendente dalla rete.
        </p>
      </article>
      <section class="stats-panel" id="statsPanel" aria-label="Statistiche catalogo">
        <div class="stat"><strong>—</strong><span>Totale</span></div>
        <div class="stat"><strong>—</strong><span>Giochi base</span></div>
        <div class="stat"><strong>—</strong><span>Espansioni</span></div>
        <div class="stat"><strong>—</strong><span>Posseduti</span></div>
      </section>
    </section>

    <section class="panel integration-panel" id="floppyPanel" aria-label="Integrazione Floppy">
      <div class="integration-head">
        <div>
          <p class="eyebrow">Integrazione</p>
          <h2>Floppy</h2>
        </div>
        <span class="integration-status" id="floppyStatus">Verifica…</span>
      </div>
      <div id="floppyBody" class="integration-body">
        Controllo configurazione e connettività…
      </div>
      <div class="integration-actions">
        <button class="button button-ghost" id="floppyCheck" type="button">Verifica connessione</button>
        <button class="button button-primary" id="floppyPreview" type="button" disabled>Confronta cataloghi</button>
      </div>
      <div id="floppyPreviewResult" class="integration-result" hidden></div>
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
  bindFloppyControls();
  void loadFloppyStatus();
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

function bindFloppyControls() {
  document.querySelector("#floppyCheck")?.addEventListener("click", () => {
    void loadFloppyStatus();
  });
  document.querySelector("#floppyPreview")?.addEventListener("click", () => {
    void loadFloppyPreview();
  });
}

function setFloppyStatus(label, kind = "") {
  const badge = document.querySelector("#floppyStatus");
  if (!badge) return;
  badge.textContent = label;
  badge.className = `integration-status ${kind}`.trim();
}

async function loadFloppyStatus() {
  const body = document.querySelector("#floppyBody");
  const previewButton = document.querySelector("#floppyPreview");
  const previewResult = document.querySelector("#floppyPreviewResult");
  if (!body || !previewButton) return;

  previewButton.disabled = true;
  if (previewResult) previewResult.hidden = true;
  setFloppyStatus("Verifica…");
  body.textContent = "Controllo configurazione e connettività…";

  try {
    const status = await api("/api/integrations/floppy/status");
    if (!document.querySelector("#floppyPanel")) return;

    if (!status.configured) {
      setFloppyStatus("Non configurato", "neutral");
      body.innerHTML =
        'Apri <strong>Impostazioni</strong> e inserisci URL e API Token di Floppy.';
      return;
    }

    if (!status.reachable) {
      setFloppyStatus("Non raggiungibile", "error");
      body.textContent = status.error?.message || "Impossibile raggiungere Floppy.";
      return;
    }

    if (!status.authenticated) {
      setFloppyStatus("Autenticazione fallita", "error");
      body.textContent =
        "Floppy risponde, ma il token non consente l’accesso all’API board game. Verifica l’API Token in Settings → Integrations.";
      return;
    }

    setFloppyStatus("Connesso", "success");
    previewButton.disabled = false;
    const version = status.info?.version ? ` · versione ${escapeHtml(status.info.version)}` : "";
    const schema = status.schema?.write_contract_ready
      ? "Contratto write validato: dopo il dry-run puoi aggiungere in sicurezza i giochi mancanti alla collection."
      : "Contratto write non disponibile: il confronto resta in sola lettura.";
    body.innerHTML = `API board game raggiungibile${version}. ${escapeHtml(schema)}`;
  } catch (error) {
    setFloppyStatus("Errore", "error");
    body.textContent = error.message;
  }
}

async function loadFloppyPreview(syncReport = null) {
  const button = document.querySelector("#floppyPreview");
  const result = document.querySelector("#floppyPreviewResult");
  if (!button || !result) return;

  button.disabled = true;
  button.textContent = "Confronto…";
  result.hidden = false;
  result.innerHTML = '<span class="muted">Lettura catalogo e collection Floppy…</span>';

  try {
    const preview = await api("/api/integrations/floppy/preview");
    if (!document.querySelector("#floppyPanel")) return;

    const needsMedia = (preview.needs_media_items || []).slice(0, 6);
    const needsCollection = (preview.needs_collection_items || []).slice(0, 6);
    const ambiguous = (preview.ambiguous_items || []).slice(0, 4);

    const listBlock = (title, items, total) => {
      if (!items.length) return "";
      return `
        <div class="integration-missing">
          <strong>${escapeHtml(title)}</strong>
          <ul>${items.map((item) =>
            `<li>${escapeHtml(item.title)} <span class="muted">BGG #${escapeHtml(item.bgg_id)}</span></li>`
          ).join("")}</ul>
          ${total > items.length
            ? `<span class="muted">…e altri ${total - items.length}</span>`
            : ""}
        </div>
      `;
    };

    const reportHtml = syncReport
      ? `
        <div class="sync-report ${syncReport.failed ? "has-errors" : ""}">
          <strong>Ultimo batch:</strong>
          ${formatNumber(syncReport.attempted, 0)} tentati ·
          ${formatNumber(syncReport.media_created, 0)} media creati ·
          ${formatNumber(syncReport.collection_created, 0)} copie aggiunte ·
          ${formatNumber(syncReport.failed, 0)} errori
          ${syncReport.remaining_from_preview
            ? ` · ${formatNumber(syncReport.remaining_from_preview, 0)} ancora da elaborare`
            : ""}
        </div>
      `
      : "";

    const canApply = Boolean(preview.apply_supported) &&
      Number(preview.actionable || 0) > 0 &&
      Number(preview.ambiguous || 0) === 0;
    const batchCount = Math.min(Number(preview.actionable || 0), 20);
    const applyLabel = batchCount === Number(preview.actionable || 0)
      ? `Sincronizza ${batchCount}`
      : `Sincronizza prossimi ${batchCount}`;

    result.innerHTML = `
      ${reportHtml}
      <div class="integration-summary">
        <div><strong>${formatNumber(preview.local_owned, 0)}</strong><span>Locali posseduti</span></div>
        <div><strong>${formatNumber(preview.remote_collection_entries, 0)}</strong><span>Copie in Floppy</span></div>
        <div><strong>${formatNumber(preview.already_owned, 0)}</strong><span>Già allineati</span></div>
        <div><strong>${formatNumber(preview.needs_collection, 0)}</strong><span>Da aggiungere alla collection</span></div>
        <div><strong>${formatNumber(preview.needs_media, 0)}</strong><span>Media mancanti</span></div>
        <div><strong>${formatNumber(preview.ambiguous, 0)}</strong><span>Ambigui</span></div>
      </div>

      ${listBlock("Media da creare in Floppy", needsMedia, preview.needs_media)}
      ${listBlock("Media già presenti, copia da aggiungere", needsCollection, preview.needs_collection)}
      ${listBlock("Corrispondenze ambigue — nessuna scrittura", ambiguous, preview.ambiguous)}

      <div class="sync-actions">
        ${preview.actionable === 0
          ? '<span class="sync-ok">✓ Collection allineata</span>'
          : canApply
            ? `<button class="button button-primary" id="floppyApply" type="button">${applyLabel}</button>`
            : ""}
      </div>

      <p class="muted integration-note">
        Dry-run add-only: BoardGameCompanion non elimina media, copie o cronologia da Floppy.
        ${preview.ambiguous
          ? " Risolvi prima le corrispondenze ambigue."
          : preview.apply_supported
            ? " La scrittura richiede conferma esplicita."
            : " L'istanza Floppy non espone il contratto write richiesto."}
      </p>
    `;

    document.querySelector("#floppyApply")?.addEventListener("click", () => {
      void applyFloppySync(preview);
    });
  } catch (error) {
    result.innerHTML = `<span class="integration-error">${escapeHtml(error.message)}</span>`;
    showToast(error.message, true);
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      button.textContent = "Confronta cataloghi";
    }
  }
}

async function applyFloppySync(preview) {
  const applyButton = document.querySelector("#floppyApply");
  const actionable = Number(preview.actionable || 0);
  const batchSize = Math.min(actionable, 20);
  if (!applyButton || !batchSize) return;

  const confirmed = window.confirm(
    `Aggiungerò fino a ${batchSize} giochi alla collection di Floppy. Non verrà cancellato nulla. Procedere?`
  );
  if (!confirmed) return;

  applyButton.disabled = true;
  applyButton.textContent = "Sincronizzazione…";

  try {
    const report = await api("/api/integrations/floppy/sync", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        plan_hash: preview.plan_hash,
        batch_size: batchSize,
      }),
    });

    if (report.failed) {
      showToast(
        `Sync completato con ${report.failed} errori. Controlla il riepilogo.`,
        true,
      );
    } else {
      showToast(
        `Sync completato: ${report.collection_created} copie aggiunte a Floppy.`,
      );
    }
    await loadFloppyPreview(report);
  } catch (error) {
    showToast(error.message, true);
    if (error.status === 409) {
      await loadFloppyPreview();
    } else if (applyButton.isConnected) {
      applyButton.disabled = false;
      applyButton.textContent = "Riprova sincronizzazione";
    }
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
    <article class="game-document-card">
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

async function refreshGameMetadata(bggId) {
  const button = document.querySelector("#refreshGameMetadata");
  if (button) {
    button.disabled = true;
    button.textContent = "Aggiornamento…";
  }
  try {
    const result = await api(`/api/games/${bggId}/metadata/refresh`, {
      method: "POST",
    });
    showToast(result.changed ? "Metadata BGG aggiornati." : "Metadata BGG già aggiornati.");
    await renderDetail(bggId);
  } catch (error) {
    showToast(error.message, true);
    if (button?.isConnected) {
      button.disabled = false;
      button.textContent = "Aggiorna metadata";
    }
  }
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
    const [game, copies, documents] = await Promise.all([
      api(`/api/games/${bggId}`),
      api(`/api/games/${bggId}/copies`),
      api(`/api/games/${bggId}/documents`),
    ]);
    if (window.location.pathname !== requestedPath) return;
    const type = game.item_type === "expansion" ? "Espansione" : "Gioco base";
    const collection = game.collection || {};
    const bgg = game.bgg || {};
    const metadata = game.metadata || null;
    const copyItems = copies.items || [];
    const documentItems = documents.items || [];

    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
      <section class="detail">
        <div class="detail-cover">
          <span class="cover-initials">${escapeHtml(initials(game.title))}</span>
          ${metadata?.image_url
            ? `<img class="detail-cover-image" src="${escapeHtml(metadata.image_url)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">`
            : ""}
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
            <span class="badge">${copyItems.length} ${copyItems.length === 1 ? "copia" : "copie"}</span>
          </div>

          <div class="fact-grid">
            ${fact("Giocatori", playerText(game))}
            ${fact("Durata", timeText(game))}
            ${fact("Rating BGG", bgg.average ? `★ ${formatNumber(bgg.average, 2)}` : "—")}
            ${fact("Complessità", bgg.average_weight ? `${formatNumber(bgg.average_weight, 2)} / 5` : "—")}
            ${fact("Ranking BGG", bgg.rank ? `#${formatNumber(bgg.rank, 0)}` : "—")}
            ${fact("Partite registrate", collection.num_plays ?? "—")}
          </div>

          <div class="section-heading-row">
            <h2 class="section-title">Copie fisiche</h2>
            <button class="button button-ghost" id="addPhysicalCopy" type="button">+ Aggiungi copia</button>
          </div>
          <div class="physical-copy-list" id="physicalCopyList">
            ${copyItems.length
              ? copyItems.map((copy, index) => physicalCopyCard(copy, index)).join("")
              : '<div class="empty copy-empty">Nessuna copia fisica registrata.</div>'}
          </div>

          <div class="section-heading-row document-heading">
            <div>
              <h2 class="section-title">Manuali e documenti</h2>
              <p class="section-subtitle">${documentItems.length} ${documentItems.length === 1 ? "documento" : "documenti"} archiviati</p>
            </div>
            <button class="button button-ghost" id="addDocument" type="button">+ Aggiungi PDF</button>
          </div>
          <div class="game-document-list" id="gameDocumentList">
            ${documentItems.length
              ? documentItems.map(documentCard).join("")
              : '<div class="empty document-empty">Nessun manuale o documento registrato.</div>'}
          </div>

          <div class="section-heading-row metadata-heading">
            <div>
              <h2 class="section-title">Metadata BGG via Floppy</h2>
              <p class="section-subtitle">
                ${metadata
                  ? `Cache aggiornata: ${escapeHtml(formatUpdateTime(metadata.fetched_at))}`
                  : "Nessun metadata live in cache. Il catalogo resta utilizzabile offline."}
              </p>
            </div>
            <button class="button button-ghost" id="refreshGameMetadata" type="button">
              Aggiorna metadata
            </button>
          </div>

          ${metadata ? `
            <div class="fact-grid metadata-facts">
              ${fact("Rating live", metadata.score != null ? `★ ${formatNumber(metadata.score, 1)}` : "—")}
              ${fact("Valutazioni", metadata.score_count != null ? formatNumber(metadata.score_count, 0) : "—")}
              ${fact("Giocatori", metadata.players || "—")}
              ${fact("Durata", metadata.playtime || "—")}
              ${fact("Età minima", metadata.min_age || "—")}
              ${fact("Anno provider", metadata.year_published || "—")}
              ${fact("Designer", metadata.designers || "—")}
              ${fact("Editori", metadata.publishers || "—")}
              ${fact("Categorie", metadata.genres?.length ? metadata.genres.join(", ") : "—")}
            </div>
            ${metadata.synopsis
              ? `<p class="metadata-synopsis">${escapeHtml(metadata.synopsis)}</p>`
              : ""}
          ` : `
            <div class="metadata-empty">
              Cover, descrizione e dettagli correnti possono essere recuperati su richiesta tramite Floppy.
            </div>
          `}

          <h2 class="section-title">Dati BGG dal CSV</h2>
          <div class="fact-grid">
            ${fact("Best players", bgg.best_players || "—")}
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

    document.querySelector("#addPhysicalCopy")?.addEventListener("click", () => {
      openCopyEditor(game.bgg_id, game.title);
    });
    document.querySelectorAll(".edit-copy").forEach((button) => {
      button.addEventListener("click", () => {
        const copy = copyItems.find((item) => item.id === button.dataset.copyId);
        if (copy) openCopyEditor(game.bgg_id, game.title, copy);
      });
    });
    document.querySelector("#addDocument")?.addEventListener("click", () => {
      openDocumentDialog(game.bgg_id, game.title);
    });
    document.querySelector("#refreshGameMetadata")?.addEventListener("click", () => {
      void refreshGameMetadata(game.bgg_id);
    });

    document.title = `${game.title} · BoardGameCompanion`;
  } catch (error) {
    app.innerHTML = `
      <a class="detail-back" href="/" data-nav>← Torna al catalogo</a>
      <div class="empty">Impossibile caricare il gioco: ${escapeHtml(error.message)}</div>
    `;
    showToast(error.message, true);
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
    : item.status === "rejected" ? "Rifiutato" : "Da revisionare";
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
  app.innerHTML = '<div class="empty">Caricamento coda di revisione…</div>';
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
      <section class="review-page">
        <div class="review-page-head">
          <div>
            <p class="eyebrow">P6 · Rulebook review</p>
            <h1>Coda di revisione</h1>
            <p class="muted">
              I candidati non idonei al download unattended richiedono una decisione esplicita.
            </p>
          </div>
          <span class="review-counter">${pendingData.total} pending</span>
        </div>

        ${corruptWarning}

        <h2 class="section-title">Da revisionare</h2>
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
    document.title = "Revisioni · BoardGameCompanion";
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
    showToast(enabled ? "Aggiornamenti automatici in pausa." : "Aggiornamenti automatici riattivati.");
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
      ? `Scheduler attivo · scansione coda ogni ${escapeHtml(formatUpdateInterval(worker.poll_seconds || 60))}`
      : "Scheduler automatico disattivato";
    const corruptWarning = data.corrupt_count
      ? `<div class="review-warning">${data.corrupt_count} target collegati a review corrotte sono stati esclusi da questa pagina.</div>`
      : "";

    app.innerHTML = `
      <section class="update-page">
        <div class="review-page-head">
          <div>
            <p class="eyebrow">P6B · Rulebook updates</p>
            <h1>Aggiornamenti automatici</h1>
            <p class="muted">
              I candidati approvati vengono ricontrollati con il guarded fetch.
              Una nuova versione viene archiviata solo quando cambia il contenuto.
            </p>
          </div>
          <span class="review-counter">${data.total} target</span>
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
    document.title = "Aggiornamenti · BoardGameCompanion";
    scheduleUpdateRefresh();
  } catch (error) {
    app.innerHTML = `<div class="empty">Impossibile caricare gli aggiornamenti: ${escapeHtml(error.message)}</div>`;
    showToast(error.message, true);
    scheduleUpdateRefresh();
  }
}


async function route() {
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

scannerButton.addEventListener("click", openScannerDialog);
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
  void openSettingsDialog();
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
  currentFloppySettings = null;
});

settingsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void persistFloppySettings({verifyAfter: false});
});

saveTestSettings.addEventListener("click", () => {
  void persistFloppySettings({verifyAfter: true});
});

floppyClearToken.addEventListener("change", () => {
  floppyApiKey.disabled = floppyClearToken.checked || Boolean(currentFloppySettings?.overrides?.api_key);
  if (floppyClearToken.checked) floppyApiKey.value = "";
});

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
