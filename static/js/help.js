// Wires a "?" button to its help <dialog>: open on click; close with ×, Escape or a click outside.
// Older iPads (before iPadOS 15.4) have no <dialog>.showModal(): show it with the open attribute instead.
document.querySelectorAll('[data-help-open]').forEach((btn) => {
  const dialog = document.getElementById(btn.dataset.helpOpen);
  if (!dialog) return;
  const open = () => { if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', ''); };
  const close = () => { if (dialog.close) dialog.close(); else dialog.removeAttribute('open'); };
  btn.addEventListener('click', open);
  const x = dialog.querySelector('[data-help-close]');
  if (x) x.addEventListener('click', close);
  dialog.addEventListener('click', (e) => { if (e.target === dialog) close(); });
});
