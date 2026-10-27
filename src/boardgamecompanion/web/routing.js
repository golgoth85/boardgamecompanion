export const shellSectionLabels = Object.freeze({
  catalog: "Ludoteca",
  bgg: "Catalogo",
  rankings: "Classifiche",
  suggestions: "Suggerimenti",
  crowdfunding: "Crowdfunding",
  lists: "Raccolte",
  wishlist: "Wishlist",
  explore: "Esplora",
  plays: "Partite",
  assistant: "Assistente AI",
  reviews: "Fonti da verificare",
  updates: "Aggiornamenti regolamenti",
  discovery: "Ricerca regolamenti",
});

export function shellRouteKey(pathname = window.location.pathname) {
  if (/^\/bgg(?:\/\d+)?\/?$/.test(pathname)) return "bgg";
  if (/^\/rankings\/?$/.test(pathname)) return "rankings";
  if (/^\/suggestions\/?$/.test(pathname)) return "suggestions";
  if (/^\/crowdfunding\/?$/.test(pathname)) return "crowdfunding";
  if (/^\/lists\/?$/.test(pathname)) return "lists";
  if (/^\/wishlist\/?$/.test(pathname)) return "wishlist";
  if (/^\/(?:plays|completed)\/?$/.test(pathname)) return "plays";
  if (/^\/assistant\/?$/.test(pathname)) return "assistant";
  if (/^\/(?:explore|categories|mechanics)\/?$/.test(pathname)) return "explore";
  if (/^\/reviews\/?$/.test(pathname)) return "reviews";
  if (/^\/updates\/?$/.test(pathname)) return "updates";
  if (/^\/discovery\/?$/.test(pathname)) return "discovery";
  return "catalog";
}
