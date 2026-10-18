const labels = {deepseek: "DeepSeek", groq: "Groq", lmstudio: "LM Studio", ollama: "Ollama", gemini: "Gemini"};
const cloudProviders = ["deepseek", "groq"];
const field = (id) => document.getElementById(id);

export function readProviderPriority(container) {
  return JSON.parse(container.dataset.order || "[]");
}

export function renderProviderPriority(container, choices, selected) {
  const order = [...new Set(selected || [])].filter((p) => choices.includes(p));
  if (!order.length) order.push(choices[0]);
  container.dataset.order = JSON.stringify(order);
  container.replaceChildren();
  const all = [...order, ...choices.filter((p) => !order.includes(p))];
  for (const provider of all) {
    const index = order.indexOf(provider);
    const row = document.createElement("div");
    row.className = `ai-priority-row${index === 0 ? " is-primary" : ""}`;
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = index !== -1;
    checkbox.disabled = order.length === 1 && index === 0;
    checkbox.setAttribute("aria-label", `Usa ${labels[provider]}`);
    checkbox.addEventListener("change", () => {
      const next = checkbox.checked ? [...order, provider] : order.filter((p) => p !== provider);
      renderProviderPriority(container, choices, next);
      container.querySelector(`[data-provider="${provider}"] input`)?.focus();
    });
    label.append(checkbox, document.createTextNode(labels[provider]));
    row.dataset.provider = provider;
    const position = document.createElement("small");
    position.textContent = index === 0 ? "Attivo" : index < 0 ? "Non usato" : `${index + 1}°`;
    const actions = document.createElement("span");
    actions.className = "ai-priority-actions";
    for (const [offset, arrow, direction] of [[-1, "↑", "su"], [1, "↓", "giù"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button-ghost";
      button.textContent = arrow;
      button.setAttribute("aria-label", `Sposta ${labels[provider]} ${direction}`);
      button.disabled = index < 0 || index + offset < 0 || index + offset >= order.length;
      button.addEventListener("click", () => {
        const next = [...order];
        [next[index], next[index + offset]] = [next[index + offset], next[index]];
        renderProviderPriority(container, choices, next);
        const target = container.querySelector(`[data-provider="${provider}"] button:not(:disabled)`);
        (target || container.querySelector(`[data-provider="${provider}"] input`))?.focus();
      });
      actions.append(button);
    }
    row.append(label, position, actions);
    container.append(row);
  }
}

function setModelOptions(select, models, selected) {
  const options = new Map(models.map((model) => [model.id, model.name || model.id]));
  if (selected && !options.has(selected)) options.set(selected, selected);
  select.replaceChildren(...[...options].map(([id, name]) => new Option(name, id)));
  if (selected) select.value = selected;
}

export function applyCloudProviderSettings(data) {
  for (const provider of cloudProviders) {
    const config = data.providers?.[provider] || {};
    const key = field(`${provider}ApiKey`);
    key.value = "";
    key.disabled = false;
    field(`${provider}ClearApiKey`).checked = false;
    field(`${provider}ClearRow`).hidden = config.api_key_source !== "stored";
    field(`${provider}State`).textContent = config.api_key_configured ? "Chiave configurata" : "Da configurare";
    field(`${provider}ApiKeyHint`).textContent = config.api_key_configured
      ? "Chiave configurata. Lascia il campo vuoto per conservarla."
      : "Incolla la chiave API del tuo account.";
    const select = field(`${provider}GenerationModel`);
    setModelOptions(select, [...select.options].map((o) => ({id: o.value, name: o.textContent})), config.generation_model);
    field(`${provider}VerifyStatus`).textContent = "La verifica non salva la chiave. Salva impostazioni per applicare le modifiche.";
  }
  field("aiWebProvider").value = data.web_provider_preference || "auto";
  field("aiWebProviderHint").textContent = `Provider web attuale: ${labels[data.web_provider] || "Gemini"}. Gli embedding restano separati.`;
}

export function cloudProviderPayload() {
  const payload = {web_provider: field("aiWebProvider").value};
  for (const provider of cloudProviders) {
    const clear = field(`${provider}ClearApiKey`).checked;
    payload[`${provider}_api_key`] = clear ? null : field(`${provider}ApiKey`).value.trim() || null;
    payload[`clear_${provider}_api_key`] = clear;
    payload[`${provider}_generation_model`] = field(`${provider}GenerationModel`).value;
  }
  return payload;
}

export function setupCloudProviderControls({api, generationControl, onSelect}) {
  for (const provider of cloudProviders) {
    field(`${provider}ClearApiKey`).addEventListener("change", (event) => {
      const key = field(`${provider}ApiKey`);
      key.disabled = event.target.checked;
      if (key.disabled) key.value = "";
    });
    field(`${provider}Use`).addEventListener("click", () => {
      const order = readProviderPriority(generationControl);
      renderProviderPriority(generationControl, ["deepseek", "groq", "lmstudio", "ollama", "gemini"],
        [provider, ...order.filter((p) => p !== provider)]);
      if (provider === "deepseek") field("aiWebProvider").value = "deepseek";
      onSelect(labels[provider]);
    });
    field(`${provider}Verify`).addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const status = field(`${provider}VerifyStatus`);
      if (field(`${provider}ClearApiKey`).checked) {
        status.textContent = "La chiave è segnata per la rimozione. Annulla la rimozione per verificarla.";
        return;
      }
      button.disabled = true;
      status.textContent = "Verifica in corso…";
      try {
        const data = await api(`/api/settings/ai/${provider}/verify`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({api_key: field(`${provider}ApiKey`).value.trim() || null}),
        });
        const select = field(`${provider}GenerationModel`);
        const selected = data.models.some((m) => m.id === select.value) ? select.value : data.models[0]?.id;
        setModelOptions(select, data.models, selected);
        status.textContent = `Chiave verificata: ${data.models.length} modelli disponibili. Salva per applicare.`;
      } catch (error) {
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
  }
}
