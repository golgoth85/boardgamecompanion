function personalRatingLabel(value) {
  return String(Number(value)).replace(".", ",");
}

export function starRatingMarkup(value, {interactive = false, compact = false} = {}) {
  const rating = Number(value || 0);
  const stars = [1, 2, 3, 4, 5].map((star) => {
    const fillClass = rating >= star ? "is-active" : (rating >= star - 0.5 ? "is-half" : "");
    if (!interactive) {
      return `<span class="personal-star ${fillClass}" aria-hidden="true">★</span>`;
    }
    const half = star - 0.5;
    return `<span class="personal-star-control ${fillClass}">
      <span class="personal-star-glyph" aria-hidden="true">★</span>
      <button class="personal-star-hit personal-star-hit-left" type="button"
              data-personal-rating="${half}"
              aria-label="Valuta ${personalRatingLabel(half)} stelle"
              aria-pressed="${rating === half ? "true" : "false"}"></button>
      <button class="personal-star-hit personal-star-hit-right" type="button"
              data-personal-rating="${star}"
              aria-label="Valuta ${personalRatingLabel(star)} stelle"
              aria-pressed="${rating === star ? "true" : "false"}"></button>
    </span>`;
  }).join("");
  return `<span class="personal-stars ${compact ? "is-compact" : ""}" aria-label="${rating ? `${personalRatingLabel(rating)} stelle su 5` : "Non valutato"}">${stars}</span>`;
}

export function wishlistActionMarkup({active = false, itemId = "", sourceKind, sourceKey}) {
  return `<button class="button button-ghost wishlist-action ${active ? "is-active" : ""}"
                  type="button"
                  data-wishlist-source-kind="${sourceKind}"
                  data-wishlist-source-key="${sourceKey}"
                  data-wishlist-item-id="${itemId || ""}">
            ${active ? "♥ In Wishlist" : "♡ Wishlist"}
          </button>`;
}

export function personalStatusLabel(progress = {}) {
  if (progress.completed) return "Completato";
  if (progress.played) return "Giocato";
  return "Mai giocato";
}
