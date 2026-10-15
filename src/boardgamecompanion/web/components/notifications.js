import {api} from "../core/api.js";
import {escapeHtml, relativeTime} from "../core/ui.js";

export function bindNotifications({onNavigate, showToast} = {}) {
  const dialog = document.querySelector("#notificationDialog");
  const triggers = document.querySelectorAll("[data-notifications]");
  const list = document.querySelector("#notificationList");
  const badges = document.querySelectorAll("[data-notification-badge]");
  if (!dialog || !list) return {refreshBadge: async () => {}};

  function setBadge(count) {
    badges.forEach((badge) => {
      badge.textContent = count > 99 ? "99+" : String(count || "");
      badge.hidden = !count;
    });
  }

  async function refreshBadge() {
    try {
      const payload = await api("/api/notifications?unread_only=true&limit=1");
      setBadge(payload.unread_count || 0);
    } catch (_) {}
  }

  async function render() {
    list.innerHTML = '<div class="skeleton"></div>';
    try {
      const payload = await api("/api/notifications?limit=100");
      setBadge(payload.unread_count || 0);
      list.innerHTML = payload.items.length
        ? payload.items.map((item) => `
            <article class="notification-item ${item.read ? "" : "is-unread"}">
              <button class="notification-open" type="button" data-notification-id="${escapeHtml(item.id)}" data-target-url="${escapeHtml(item.target_url || "")}">
                <span class="notification-dot" aria-hidden="true"></span>
                <span>
                  <strong>${escapeHtml(item.title)}</strong>
                  <small>${escapeHtml(item.body)}</small>
                  <time>${escapeHtml(relativeTime(item.created_at))}</time>
                </span>
              </button>
            </article>
          `).join("")
        : '<div class="empty-state"><strong>Nessuna notifica</strong><p>Le novità rilevanti compariranno qui.</p></div>';
      list.querySelectorAll(".notification-open").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await api(`/api/notifications/${encodeURIComponent(button.dataset.notificationId)}/read`, {
              method: "PUT",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({read: true}),
            });
          } catch (_) {}
          const target = String(button.dataset.targetUrl || "");
          if (target) {
            dialog.close();
            if (target.startsWith("/")) {
              history.pushState({}, "", target);
              onNavigate?.();
            } else {
              window.open(target, "_blank", "noopener,noreferrer");
            }
          } else {
            await render();
          }
          await refreshBadge();
        });
      });
    } catch (error) {
      list.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    }
  }

  triggers.forEach((button) => button.addEventListener("click", () => {
    if (!dialog.open) dialog.showModal();
    void render();
  }));
  dialog.querySelector("[data-close-notifications]")?.addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-read-all-notifications]")?.addEventListener("click", async () => {
    try {
      await api("/api/notifications/read-all", {method: "POST"});
      await render();
      showToast?.("Notifiche segnate come lette.");
    } catch (error) {
      showToast?.(error.message, true);
    }
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    dialog.close();
  });
  void refreshBadge();
  return {refreshBadge, render};
}
