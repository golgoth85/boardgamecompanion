import {api} from "../core/api.js";
import {coverMarkup, escapeHtml} from "../core/ui.js";

function wishlistCard(item) {
  const destination = item.local_url || item.target_url || "#";
  const external = !item.local_url && item.target_url;
  return `
    <article class="wishlist-card">
      ${coverMarkup(item, "wishlist-cover")}
      <div class="wishlist-card-copy">
        <div>
          <p class="eyebrow">${item.source_type === "crowdfunding" ? "Crowdfunding" : "BoardGameGeek"}</p>
          <h2>${escapeHtml(item.title)}</h2>
          <p class="muted">${item.year_published ? escapeHtml(item.year_published) : ""}${item.owned ? " · già posseduto" : ""}</p>
        </div>
        <div class="wishlist-actions">
          <a class="button button-primary" href="${escapeHtml(destination)}" ${external ? 'target="_blank" rel="noopener noreferrer"' : "data-nav"}>Apri${external ? " ↗" : ""}</a>
          <button class="button button-ghost remove-wishlist-item" type="button" data-wishlist-id="${escapeHtml(item.id)}">Rimuovi</button>
        </div>
      </div>
    </article>
  `;
}

export async function renderWishlistView(app, {showToast} = {}) {
  app.innerHTML = `
    <section class="feature-page">
      <header class="feature-page-header">
        <div>
          <p class="eyebrow">Da tenere d'occhio</p>
          <h1>Wishlist</h1>
          <p class="page-lead">Giochi e campagne salvati da Suggerimenti e Crowdfunding.</p>
        </div>
      </header>
      <div id="wishlistGrid" class="wishlist-grid"><div class="skeleton"></div></div>
    </section>
  `;
  try {
    const data = await api("/api/wishlist");
    const grid = app.querySelector("#wishlistGrid");
    grid.innerHTML = data.items.length
      ? data.items.map(wishlistCard).join("")
      : '<div class="empty-state"><strong>Wishlist vuota</strong><p>Aggiungi titoli da Suggerimenti o Crowdfunding.</p></div>';
    grid.querySelectorAll(".remove-wishlist-item").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api(`/api/wishlist/${encodeURIComponent(button.dataset.wishlistId)}`, {method: "DELETE"});
          showToast?.("Rimosso dalla Wishlist.");
          await renderWishlistView(app, {showToast});
        } catch (error) {
          showToast?.(error.message, true);
        }
      });
    });
    document.title = "Wishlist · BoardGameCompanion";
  } catch (error) {
    app.querySelector("#wishlistGrid").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}
