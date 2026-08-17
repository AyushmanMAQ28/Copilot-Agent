const icons = {
  expand: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M4 9V4h5v2H6v3H4zm10-5h6v6h-2V6h-4V4zM4 15h2v3h3v2H4v-5zm14 3v-3h2v5h-5v-2h3z"/></svg>',
  download: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M5 20h14v-2H5v2zM11 3h2v9.17l3.59-3.58L18 10l-6 6-6-6 1.41-1.41L11 12.17V3z"/></svg>',
  csv: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16l4-4h10a2 2 0 0 0 2-2V8l-6-6zm1 7V3.5L19.5 9H15z"/></svg>',
};

export function getIcon(name) {
  return icons[name] || "";
}
