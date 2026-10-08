export const shellSectionLabels = Object.freeze({
  catalog: "Ludoteca",
  rankings: "Classifiche",
  suggestions: "Suggerimenti",
  crowdfunding: "Crowdfunding",
  lists: "Liste",
  wishlist: "Wishlist",
  explore: "Esplora",
  completed: "Sala dei trofei",
  reviews: "Fonti da verificare",
  updates: "Aggiornamenti regolamenti",
  discovery: "Ricerca regolamenti",
});

export function shellRouteKey(pathname = window.location.pathname) {
  if (/^\/rankings\/?$/.test(pathname)) return "rankings";
  if (/^\/suggestions\/?$/.test(pathname)) return "suggestions";
  if (/^\/crowdfunding\/?$/.test(pathname)) return "crowdfunding";
  if (/^\/lists\/?$/.test(pathname)) return "lists";
  if (/^\/wishlist\/?$/.test(pathname)) return "wishlist";
  if (/^\/completed\/?$/.test(pathname)) return "completed";
  if (/^\/(?:explore|categories|mechanics)\/?$/.test(pathname)) return "explore";
  if (/^\/reviews\/?$/.test(pathname)) return "reviews";
  if (/^\/updates\/?$/.test(pathname)) return "updates";
  if (/^\/discovery\/?$/.test(pathname)) return "discovery";
  return "catalog";
}
