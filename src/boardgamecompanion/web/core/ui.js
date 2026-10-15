export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("it-IT", {maximumFractionDigits: digits});
}

export function initials(title) {
  const words = String(title || "?").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  return words.slice(0, 3).map((word) => word[0]).join("").toUpperCase();
}

export function relativeTime(value) {
  if (!value) return "mai";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recentemente";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "adesso";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h fa`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} g fa`;
  return date.toLocaleDateString("it-IT");
}

export function coverMarkup(item, className = "shared-cover") {
  const title = escapeHtml(item?.title || "");
  const url = item?.cover_url || item?.bgg_metadata?.cover_url;
  return url
    ? `<span class="${className}"><img src="${escapeHtml(url)}" alt="Cover di ${title}" loading="lazy" referrerpolicy="no-referrer"></span>`
    : `<span class="${className} is-placeholder">${escapeHtml(initials(item?.title))}</span>`;
}

export function starRatingMarkup(value, {interactive = false, name = "Valutazione personale", dataAttribute = "data-personal-rating"} = {}) {
  const rating = Number(value || 0);
  const stars = [1, 2, 3, 4, 5].map((star) => {
    const active = rating >= star;
    if (!interactive) return `<span class="personal-star ${active ? "is-active" : ""}" aria-hidden="true">★</span>`;
    return `<button class="personal-star-button ${active ? "is-active" : ""}" type="button" ${dataAttribute}="${star}" aria-label="${name}: ${star} stella${star === 1 ? "" : "e"}" aria-pressed="${rating === star ? "true" : "false"}">★</button>`;
  }).join("");
  return `<span class="personal-stars ${interactive ? "is-interactive" : ""}" aria-label="${name}: ${rating || "non impostata"} su 5">${stars}</span>`;
}

export function compactGameTile(game) {
  const rating = game.progress?.personal_rating;
  return `
    <a class="shared-game-tile" href="/games/${encodeURIComponent(game.bgg_id)}" data-nav>
      ${coverMarkup(game, "shared-game-cover")}
      <span class="shared-game-copy">
        <strong>${escapeHtml(game.title)}</strong>
        <small>${escapeHtml(String(game.year_published || "Anno —"))}${game.progress?.played ? " · giocato" : ""}</small>
        ${rating ? `<span class="shared-personal-rating">Tu ${starRatingMarkup(rating)}</span>` : ""}
      </span>
    </a>
  `;
}
