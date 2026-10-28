// Wires a "?" button to its help <dialog>: open on click; close with ×, Escape or a click outside.
document.querySelectorAll('[data-help-open]').forEach((btn) => {
  const dialog = document.getElementById(btn.dataset.helpOpen);
  if (!dialog) return;
  btn.addEventListener('click', () => dialog.showModal());
  dialog.querySelector('[data-help-close]')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
});
