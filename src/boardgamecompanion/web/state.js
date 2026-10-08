const catalogPageSizeValues = new Set(["20", "50", "100", "250", "all"]);
const storedCatalogPageSize = window.localStorage.getItem("bgc.catalogPageSize") || "50";

export const CATALOG_ALL_LIMIT = 5000;
export {catalogPageSizeValues};

export const initialCatalogPageSize = catalogPageSizeValues.has(storedCatalogPageSize)
  ? storedCatalogPageSize
  : "50";

const storedCatalogColumns = Number(window.localStorage.getItem("bgc.catalogColumns"));
export const initialCatalogColumns = [3, 4, 5].includes(storedCatalogColumns)
  ? storedCatalogColumns
  : 5;

export const state = {
  q: "",
  itemType: "",
  owned: "",
  sort: "title",
  pageSize: initialCatalogPageSize,
  limit: initialCatalogPageSize === "all"
    ? CATALOG_ALL_LIMIT
    : Number(initialCatalogPageSize),
  offset: 0,
  total: 0,
  catalogView: window.localStorage.getItem("bgc.catalogView") === "list"
    ? "list"
    : "cards",
  collapseExpansions: window.localStorage.getItem("bgc.collapseExpansions") !== "false",
  expandedGameGroups: new Set(),
  cardsPerRow: initialCatalogColumns,
  supportsPlayers: "",
  idealPlayers: "",
  playerAge: "",
  weight: "",
  maxMinutes: "",
  minRating: "",
  category: "",
  mechanic: "",
};

export const exploreState = {
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

export const rankingState = {
  group: "top",
  mode: "overall",
  category: "",
  mechanic: "",
  idealPlayers: "",
  maxMinutes: "",
  weight: "",
};

export const rankingGroups = Object.freeze({
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
});

export const catalogColumnSorts = Object.freeze({
  title: ["title", "title_desc"],
  players: ["players_asc", "players_desc"],
  age: ["age_asc", "age_desc"],
  duration: ["duration_asc", "duration_desc"],
  weight: ["weight_desc", "weight_asc"],
  rating: ["rating_desc", "rating_asc"],
});
