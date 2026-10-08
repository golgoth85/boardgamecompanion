export function starRatingMarkup(value, {interactive = false, compact = false} = {}) {
  const rating = Number(value || 0);
  const stars = [1, 2, 3, 4, 5].map((star) => {
    const active = star <= rating;
    if (!interactive) {
      return `<span class="personal-star ${active ? "is-active" : ""}" aria-hidden="true">★</span>`;
    }
    return `<button class="personal-star-button ${active ? "is-active" : ""}"
                    type="button" data-personal-rating="${star}"
                    aria-label="Valuta ${star} stelle" aria-pressed="${rating === star ? "true" : "false"}">★</button>`;
  }).join("");
  return `<span class="personal-stars ${compact ? "is-compact" : ""}" aria-label="${rating ? `${rating} stelle su 5` : "Non valutato"}">${stars}</span>`;
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
