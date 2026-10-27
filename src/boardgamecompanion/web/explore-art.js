// Static artwork for the Esplora macro groups (keyed like explore_groups.py)
// and the Classifiche modes: one line illustration and one hue each, drawn on
// a 48×48 grid.
const art = {
  // Generi
  fantastic: [262, `
    <circle cx="22" cy="26" r="10"/>
    <ellipse cx="22" cy="26" rx="18" ry="5.5" transform="rotate(-18 22 26)"/>
    <path d="M38 6l1.6 3.4L43 11l-3.4 1.6L38 16l-1.6-3.4L33 11l3.4-1.6z"/>`],
  scifi: [232, `
    <path d="M24 6c6 5 8 12 8 20l-4 6h-8l-4-6c0-8 2-15 8-20z"/>
    <circle cx="24" cy="19" r="3"/>
    <path d="M16 26l-5 7 6-1M32 26l5 7-6-1M21 36l3 6 3-6"/>`],
  adventure: [168, `
    <circle cx="24" cy="24" r="17"/>
    <path d="M30.5 17.5l-4 9-9 4 4-9z"/>
    <path d="M24 7v4M24 37v4M7 24h4M37 24h4"/>`],
  history: [36, `
    <path d="M8 16L24 7l16 9z"/>
    <path d="M8 40h32M10 36h28"/>
    <path d="M13 19v15M20 19v15M28 19v15M35 19v15"/>`],
  war: [4, `
    <path d="M10 10l20 20M38 10L18 30"/>
    <path d="M10 10l1-4 3 3zM38 10l-1-4-3 3z"/>
    <path d="M26 34l6-6M22 34l-6-6"/>
    <path d="M29 37l4 4M19 37l-4 4"/>`],
  economy: [46, `
    <path d="M6 40V22l9 6v-6l9 6v-6l9 6V10h7v30z"/>
    <path d="M12 34h4M21 34h4M30 34h4"/>
    <path d="M6 40h36"/>`],
  nature: [108, `
    <path d="M10 38C10 20 22 9 40 8c-1 18-12 30-30 30z"/>
    <path d="M10 38l18-18M20 28h-6M26 22v-6"/>`],
  mystery: [220, `
    <circle cx="20" cy="20" r="11"/>
    <path d="M28 28l12 12"/>
    <path d="M15 20a5 5 0 015-5"/>`],
  party: [320, `
    <ellipse cx="17" cy="17" rx="8" ry="10"/>
    <ellipse cx="31" cy="15" rx="7" ry="9"/>
    <path d="M17 27l-1 3h2zM31 24l-1 3h2z"/>
    <path d="M17 30c0 5 3 6 5 12M31 27c0 6-4 8-6 15"/>`],
  logic: [190, `
    <path d="M10 18h7a4 4 0 118 0h7v7a4 4 0 110 8v7H10V33a4 4 0 100-8z"/>`],
  format: [14, `
    <rect x="7" y="10" width="17" height="24" rx="3" transform="rotate(-10 15 22)"/>
    <rect x="24" y="20" width="17" height="17" rx="4"/>
    <circle cx="29" cy="25" r="1.2"/><circle cx="36" cy="32" r="1.2"/><circle cx="32.5" cy="28.5" r="1.2"/>`],
  theme: [292, `
    <rect x="7" y="18" width="34" height="22" rx="3"/>
    <path d="M7 18l3-9 32 0-1 9"/>
    <path d="M15 9l-3 9M24 9l-3 9M33 9l-3 9"/>
    <path d="M21 25v9l8-4.5z"/>`],
  // Meccaniche
  cards: [24, `
    <rect x="9" y="12" width="16" height="24" rx="3" transform="rotate(-16 17 24)"/>
    <rect x="16" y="10" width="16" height="24" rx="3"/>
    <rect x="23" y="12" width="16" height="24" rx="3" transform="rotate(16 31 24)"/>`],
  drafting: [56, `
    <rect x="8" y="22" width="14" height="19" rx="2.5"/>
    <rect x="17" y="15" width="14" height="19" rx="2.5"/>
    <rect x="26" y="8" width="14" height="19" rx="2.5"/>
    <path d="M33 31v8l-3-3M33 39l3-3"/>`],
  engine: [150, `
    <circle cx="18" cy="20" r="5"/>
    <path d="M18 9v3M18 28v3M7 20h3M26 20h3M10.2 12.2l2.2 2.2M23.6 25.6l2.2 2.2M10.2 27.8l2.2-2.2M23.6 14.4l2.2-2.2"/>
    <circle cx="33" cy="33" r="4"/>
    <path d="M33 25v2.5M33 38.5V41M25 33h2.5M38.5 33H41"/>`],
  actions: [38, `
    <circle cx="24" cy="11" r="5"/>
    <path d="M18 18c-6 0-11 2-11 5 0 2 4 3 8 3l-4 13h10l3-6 3 6h10l-4-13c4 0 8-1 8-3 0-3-5-5-11-5z"/>`],
  dice: [0, `
    <rect x="9" y="9" width="30" height="30" rx="6"/>
    <circle cx="17" cy="17" r="2"/><circle cx="31" cy="17" r="2"/><circle cx="24" cy="24" r="2"/>
    <circle cx="17" cy="31" r="2"/><circle cx="31" cy="31" r="2"/>`],
  map: [120, `
    <path d="M16 6l8 4.5v9L16 24l-8-4.5v-9z"/>
    <path d="M32 15l8 4.5v9L32 33l-8-4.5v-9z"/>
    <path d="M16 24l8 4.5v9L16 42l-8-4.5v-9z"/>`],
  conflict: [350, `
    <path d="M24 6l15 5v11c0 9-6 16-15 20-9-4-15-11-15-20V11z"/>
    <path d="M24 14v20M16 22h16"/>`],
  social: [276, `
    <path d="M14 22l10-10 6 6-10 10z"/>
    <path d="M27 9l6 6M11 25l6 6"/>
    <path d="M25 22l14 14"/>
    <path d="M6 42h18"/>`],
  spatial: [200, `
    <rect x="8" y="8" width="14" height="14" rx="2"/>
    <rect x="26" y="8" width="14" height="14" rx="2"/>
    <rect x="8" y="26" width="14" height="14" rx="2"/>
    <path d="M26 33h14M33 26v14"/>`],
  dexterity: [178, `
    <circle cx="24" cy="27" r="14"/>
    <path d="M24 27l6-6M20 7h8M24 7v6M36 13l3-3"/>`],
  modes: [102, `
    <path d="M24 13c-5-4-11-4-17-2v26c6-2 12-2 17 2 5-4 11-4 17-2V11c-6-2-12-2-17 2z"/>
    <path d="M24 13v26"/>`],
  story: [300, `
    <path d="M12 8h20a4 4 0 014 4v28H16a4 4 0 01-4-4z"/>
    <path d="M12 36a4 4 0 014-4h20"/>
    <path d="M18 15h12M18 21h9"/>`],
  // Classifiche
  "mode-overall": [42, `
    <path d="M15 8h18v9a9 9 0 01-18 0z"/>
    <path d="M15 11H8c0 6 3 9 7 9M33 11h7c0 6-3 9-7 9"/>
    <path d="M24 26v7M17 40h14l-2-7H19z"/>`],
  "mode-outside_top": [190, `
    <path d="M14 9h20l7 10-17 21L7 19z"/>
    <path d="M7 19h34M19 9l-3 10 8 21 8-21-3-10"/>`],
  "mode-quality_time": [28, `
    <path d="M13 7h22M13 41h22"/>
    <path d="M15 7c0 9 9 11 9 17s-9 8-9 17M33 7c0 9-9 11-9 17s9 8 9 17"/>
    <path d="M19 36c2-2 8-2 10 0"/>`],
  "mode-gateway": [150, `
    <path d="M10 41V11a3 3 0 013-3h22a3 3 0 013 3v30"/>
    <path d="M6 41h36"/>
    <path d="M18 24h12M25 19l5 5-5 5"/>`],
  "mode-expert": [262, `
    <path d="M5 40l13-22 7 11 5-7 13 18z"/>
    <path d="M18 18V7l8 3-8 3"/>`],
  "mode-safe_choice": [150, `
    <path d="M24 6l15 5v11c0 9-6 16-15 20-9-4-15-11-15-20V11z"/>
    <path d="M17 24l5 5 9-10"/>`],
  "mode-personal_favorites": [340, `
    <path d="M24 40S8 30 8 18a8 8 0 0116-3 8 8 0 0116 3c0 12-16 22-16 22z"/>`],
  other: [215, `
    <circle cx="13" cy="24" r="3"/><circle cx="24" cy="24" r="3"/><circle cx="35" cy="24" r="3"/>`],
};

export function exploreGroupArt(key) {
  const [hue, paths] = art[key] || art.other;
  return `<span class="explore-group-art" style="--group-hue:${hue}" aria-hidden="true">
    <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.4"
         stroke-linecap="round" stroke-linejoin="round">${paths}</svg>
  </span>`;
}
