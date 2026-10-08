const SETTINGS_TABS = new Set([
  "general",
  "rulebooks",
  "providers",
  "crowdfunding",
  "diagnostics",
]);

export function activateSettingsTab({
  name = "general",
  tabs,
  panels,
  saveSettings,
  saveTestSettings,
  onDiagnostics,
}) {
  const active = SETTINGS_TABS.has(name) ? name : "general";
  for (const tab of tabs || []) {
    const selected = tab.dataset.settingsTab === active;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
  }
  for (const panel of panels || []) {
    panel.hidden = panel.dataset.settingsPanel !== active;
  }
  if (saveSettings) {
    saveSettings.hidden = active === "rulebooks" || active === "diagnostics";
  }
  if (saveTestSettings) saveTestSettings.hidden = active !== "general";
  if (active === "diagnostics") onDiagnostics?.();
  return active;
}
