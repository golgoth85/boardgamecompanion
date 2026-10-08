export function openDialog(dialog, {focus = null, select = false} = {}) {
  if (!dialog) return false;
  if (!dialog.open) dialog.showModal();
  if (focus) {
    focus.focus();
    if (select && typeof focus.select === "function") focus.select();
  }
  return true;
}

export function closeDialog(dialog) {
  if (!dialog?.open) return false;
  dialog.close();
  return true;
}

export function bindDialogCancel(dialog, handler = null) {
  dialog?.addEventListener("cancel", (event) => {
    event.preventDefault();
    if (handler) handler();
    else closeDialog(dialog);
  });
}
