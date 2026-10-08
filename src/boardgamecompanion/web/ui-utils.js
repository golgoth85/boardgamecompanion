export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function initials(title) {
  const words = String(title || "?").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.slice(0, 3).map((word) => word[0]).join("").toUpperCase();
}

export function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("it-IT", {maximumFractionDigits: digits});
}

export function safeExternalHref(value, fallback = "#") {
  const text = String(value || "").trim();
  if (!text) return fallback;
  try {
    const url = new URL(text);
    if (!["http:", "https:"].includes(url.protocol)) return fallback;
    if (url.username || url.password) return fallback;
    return text;
  } catch (_) {
    return fallback;
  }
}
