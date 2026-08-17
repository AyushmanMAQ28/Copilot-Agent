function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function downloadText(filename, text, mime = "text/plain") {
  downloadBlob(filename, new Blob([text], { type: mime }));
}

export function downloadCsv(filename, rows) {
  if (!rows?.length) {
    downloadText(filename, "", "text/csv");
    return;
  }
  const columns = Array.from(rows.reduce((set, row) => {
    Object.keys(row || {}).forEach((key) => set.add(key));
    return set;
  }, new Set()));
  const esc = (value) => {
    const str = String(value ?? "");
    return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  };
  const body = [columns.join(",")].concat(rows.map((row) => columns.map((column) => esc(row[column])).join(","))).join("\n");
  downloadText(filename, body, "text/csv;charset=utf-8");
}

export function downloadPseudoXlsx(filename, rows) {
  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  const columns = rows?.length ? Object.keys(rows[0]) : [];
  const header = `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  const body = (rows || [])
    .map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>`)
    .join("");
  const html = `<!doctype html><html><body><table>${header}${body}</table></body></html>`;
  downloadText(filename, html, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
}

export async function exportSvgAsPng(svgElement, filename, backgroundColor) {
  const rect = svgElement.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));

  const serialized = new XMLSerializer().serializeToString(svgElement);
  const encoded = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = backgroundColor;
  ctx.fillRect(0, 0, width, height);

  await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, width, height);
      resolve();
    };
    img.onerror = reject;
    img.src = encoded;
  });

  const dataUrl = canvas.toDataURL("image/png");
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  link.click();
}
