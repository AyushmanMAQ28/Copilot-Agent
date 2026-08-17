const SVG_NS = "http://www.w3.org/2000/svg";

function createSvg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function toNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function niceStep(span) {
  if (!Number.isFinite(span) || span <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(span));
  const unit = span / power;
  if (unit < 1.5) return power;
  if (unit < 3) return 2 * power;
  if (unit < 7) return 5 * power;
  return 10 * power;
}

function niceTicks(min, max, count = 5) {
  if (min === max) return [min];
  const step = niceStep((max - min) / count);
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks = [];
  for (let value = start; value <= end + step / 2; value += step) ticks.push(value);
  return ticks;
}

function getPalette() {
  const style = getComputedStyle(document.documentElement);
  return [
    style.getPropertyValue("--accent").trim() || "#2563eb",
    "#0ea5e9",
    "#22c55e",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#14b8a6",
  ];
}

function formatNumber(value) {
  const num = toNumber(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, notation: Math.abs(num) >= 10000 ? "compact" : "standard" }).format(num);
}

function rotateIfLong(label, index, count) {
  if (label.length > 14 || count > 8) return index % 2 === 0 ? -25 : -45;
  return 0;
}

function normalizeChart(chart) {
  if (chart.data?.labels && chart.data?.datasets) return chart;
  if (Array.isArray(chart.data)) {
    const labels = chart.data.map((row) => String(row.category ?? row.label ?? ""));
    return { ...chart, data: { labels, datasets: [{ label: "Value", data: chart.data.map((row) => toNumber(row.value)) }] } };
  }
  return { ...chart, data: { labels: [], datasets: [] } };
}

function addTooltip(shell) {
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  shell.append(tooltip);
  return tooltip;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function setTooltip(tooltip, lines, x, y, shellRect) {
  tooltip.textContent = "";
  lines.forEach((line) => {
    const item = document.createElement("div");
    item.textContent = line;
    tooltip.append(item);
  });
  tooltip.hidden = false;
  const maxX = shellRect.width - tooltip.offsetWidth - 8;
  const maxY = shellRect.height - tooltip.offsetHeight - 8;
  tooltip.style.left = `${clamp(x + 12, 8, Math.max(8, maxX))}px`;
  tooltip.style.top = `${clamp(y + 12, 8, Math.max(8, maxY))}px`;
}

function renderHeatmap(shell, chart) {
  shell.textContent = "";
  const data = Array.isArray(chart.matrix) ? chart.matrix : chart.data?.data || [];
  const palette = getPalette();
  const cells = document.createElement("div");
  cells.className = "heatmap";
  const values = data.map((cell) => toNumber(cell.value));
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  data.forEach((cell, index) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "heat-cell";
    const value = toNumber(cell.value);
    const ratio = max === min ? 0.5 : (value - min) / (max - min);
    item.style.background = `color-mix(in oklab, ${palette[0]}, transparent ${Math.round((1 - ratio) * 85)}%)`;
    item.textContent = `${cell.x || index}, ${cell.y || ""}: ${formatNumber(value)}`;
    cells.append(item);
  });
  const legend = document.createElement("p");
  legend.className = "text-muted";
  legend.textContent = `Heatmap legend: ${formatNumber(min)} → ${formatNumber(max)}`;
  shell.append(cells, legend);
  return { exportable: false };
}

function renderKpi(shell, chart) {
  shell.textContent = "";
  const grid = document.createElement("div");
  grid.className = "kpi-grid";
  const source = chart.data?.datasets || [];
  source.forEach((set, setIndex) => {
    (set.data || []).forEach((value, index) => {
      const card = document.createElement("div");
      card.className = "kpi-card";
      const label = document.createElement("p");
      label.className = "text-muted";
      const itemLabel = chart.data.labels?.[index] || set.label || `KPI ${setIndex + 1}`;
      label.textContent = itemLabel;
      const metric = document.createElement("p");
      metric.className = "kpi-value";
      metric.textContent = formatNumber(value);
      card.append(label, metric);
      grid.append(card);
    });
  });
  shell.append(grid);
  return { exportable: false };
}

export function renderChart(shell, inputChart, options = {}) {
  const chart = normalizeChart(inputChart);
  if (chart.chart_type === "kpi") return renderKpi(shell, chart);
  if (chart.chart_type === "heatmap") return renderHeatmap(shell, chart);

  shell.textContent = "";
  shell.classList.add("chart-shell");
  const tooltip = addTooltip(shell);
  const svg = createSvg("svg", {
    viewBox: "0 0 960 420",
    width: "100%",
    height: "auto",
    role: "img",
    "aria-label": `${chart.title}. ${chart.data.labels.length} categories and ${chart.data.datasets.length} series.`,
  });
  shell.append(svg);

  const left = 70;
  const right = 20;
  const top = 24;
  const bottom = 90;
  const w = 960 - left - right;
  const h = 420 - top - bottom;
  const labels = chart.data.labels || [];
  const datasets = chart.data.datasets || [];
  const hidden = options.hiddenSeries || new Set();

  const values = [];
  datasets.forEach((set, dsIndex) => {
    if (hidden.has(dsIndex)) return;
    (set.data || []).forEach((value) => {
      if (typeof value === "object" && value !== null) {
        values.push(toNumber(value.y));
        values.push(toNumber(value.x));
      } else {
        values.push(toNumber(value));
      }
    });
  });
  const min = chart.chart_type === "scatter" ? Math.min(...values, 0) : Math.min(0, ...values);
  const max = Math.max(...values, 1);
  const ticks = niceTicks(min, max, 5);
  const yMin = ticks[0] ?? 0;
  const yMax = ticks[ticks.length - 1] ?? 1;
  const yScale = (value) => top + h - ((value - yMin) / Math.max(1e-9, yMax - yMin)) * h;
  const xSlot = labels.length ? w / Math.max(1, labels.length) : w;

  ticks.forEach((tick) => {
    const y = yScale(tick);
    svg.append(createSvg("line", { x1: left, y1: y, x2: left + w, y2: y, stroke: "var(--border-subtle)", "stroke-width": 1 }));
    const text = createSvg("text", { x: left - 8, y: y + 4, "text-anchor": "end", fill: "var(--text-faint)", "font-size": 11 });
    text.textContent = formatNumber(tick);
    svg.append(text);
  });

  svg.append(createSvg("line", { x1: left, y1: top + h, x2: left + w, y2: top + h, stroke: "var(--border)", "stroke-width": 1 }));
  svg.append(createSvg("line", { x1: left, y1: top, x2: left, y2: top + h, stroke: "var(--border)", "stroke-width": 1 }));

  const palette = getPalette();
  const hitRegions = [];

  if (chart.chart_type === "pie" || chart.chart_type === "donut") {
    const centerX = 480;
    const centerY = 205;
    const radius = 140;
    const innerRadius = chart.chart_type === "donut" ? 78 : 0;
    const series = datasets[0]?.data || [];
    const total = Math.max(1, series.reduce((sum, value) => sum + Math.abs(toNumber(value)), 0));
    let start = -Math.PI / 2;
    series.forEach((rawValue, index) => {
      const value = Math.abs(toNumber(rawValue));
      const angle = (value / total) * Math.PI * 2;
      if (!angle) return;
      const end = start + angle;
      const x1 = centerX + radius * Math.cos(start);
      const y1 = centerY + radius * Math.sin(start);
      const x2 = centerX + radius * Math.cos(end);
      const y2 = centerY + radius * Math.sin(end);
      const largeArc = angle > Math.PI ? 1 : 0;
      let pathValue = `M ${centerX} ${centerY} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`;
      if (innerRadius) {
        const ix2 = centerX + innerRadius * Math.cos(end);
        const iy2 = centerY + innerRadius * Math.sin(end);
        const ix1 = centerX + innerRadius * Math.cos(start);
        const iy1 = centerY + innerRadius * Math.sin(start);
        pathValue = [
          `M ${x1} ${y1}`,
          `A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`,
          `L ${ix2} ${iy2}`,
          `A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${ix1} ${iy1}`,
          "Z",
        ].join(" ");
      }
      const path = createSvg("path", {
        d: pathValue,
        fill: palette[index % palette.length],
        opacity: 0.92,
      });
      svg.append(path);
      hitRegions.push({
        contains: (x, y) => {
          const dx = x - centerX;
          const dy = y - centerY;
          const dist = Math.hypot(dx, dy);
          if (dist > radius || dist < innerRadius) return false;
          let anglePos = Math.atan2(dy, dx);
          if (anglePos < -Math.PI / 2) anglePos += Math.PI * 2;
          let normalizedStart = start;
          if (normalizedStart < -Math.PI / 2) normalizedStart += Math.PI * 2;
          let normalizedEnd = end;
          if (normalizedEnd < -Math.PI / 2) normalizedEnd += Math.PI * 2;
          return anglePos >= normalizedStart && anglePos <= normalizedEnd;
        },
        lines: [`${labels[index] || `Slice ${index + 1}`}`, `${formatNumber(value)}`],
      });
      start = end;
    });
  } else {
    labels.forEach((label, index) => {
      const x = left + xSlot * index + xSlot / 2;
      const rotate = rotateIfLong(String(label), index, labels.length);
      const text = createSvg("text", {
        x,
        y: top + h + 20,
        fill: "var(--text-faint)",
        "font-size": 11,
        "text-anchor": rotate ? "end" : "middle",
        transform: rotate ? `rotate(${rotate} ${x} ${top + h + 20})` : undefined,
      });
      text.textContent = String(label).slice(0, 24);
      if (rotate && String(label).length > 24) {
        const title = createSvg("title");
        title.textContent = String(label);
        text.append(title);
      }
      svg.append(text);
    });

    datasets.forEach((set, dsIndex) => {
      if (hidden.has(dsIndex)) return;
      const color = palette[dsIndex % palette.length];
      const data = set.data || [];

      if (["line", "area"].includes(chart.chart_type)) {
        let pathData = "";
        data.forEach((value, index) => {
          const x = left + xSlot * index + xSlot / 2;
          const y = yScale(toNumber(value));
          pathData += `${index ? "L" : "M"} ${x} ${y} `;
          hitRegions.push({
            contains: (px, py) => Math.hypot(px - x, py - y) < 10,
            lines: [`${labels[index] || `Point ${index + 1}`}`, `${set.label}: ${formatNumber(value)}`],
          });
          const dot = createSvg("circle", { cx: x, cy: y, r: 3.2, fill: color });
          svg.append(dot);
        });
        if (chart.chart_type === "area") {
          const firstX = left + xSlot / 2;
          const lastX = left + xSlot * (data.length - 1) + xSlot / 2;
          const area = createSvg("path", {
            d: `${pathData} L ${lastX} ${top + h} L ${firstX} ${top + h} Z`,
            fill: `color-mix(in oklab, ${color}, transparent 70%)`,
          });
          svg.append(area);
        }
        svg.append(createSvg("path", { d: pathData, fill: "none", stroke: color, "stroke-width": 2 }));
        return;
      }

      if (chart.chart_type === "scatter") {
        data.forEach((point, pointIndex) => {
          const px = toNumber(point.x);
          const py = toNumber(point.y);
          const x = left + ((px - yMin) / Math.max(1e-9, yMax - yMin)) * w;
          const y = yScale(py);
          const dot = createSvg("circle", { cx: x, cy: y, r: 4, fill: color, opacity: 0.85 });
          svg.append(dot);
          hitRegions.push({
            contains: (mx, my) => Math.hypot(mx - x, my - y) < 10,
            lines: [`${set.label || "Series"}`, `x: ${formatNumber(px)}`, `y: ${formatNumber(py)}`],
          });
          if (!labels[pointIndex]) labels[pointIndex] = `${pointIndex + 1}`;
        });
        return;
      }

      data.forEach((value, index) => {
        const xBase = left + xSlot * index;
        const numeric = toNumber(value);
        const barWidth = Math.max(4, xSlot / Math.max(1.2, datasets.length + 0.7));

        let x = xBase + (chart.chart_type === "grouped_bar" ? barWidth * dsIndex + 6 : xSlot * 0.2);
        let width = chart.chart_type === "grouped_bar" ? barWidth : xSlot * 0.6;
        let y = yScale(numeric);
        let height = top + h - y;

        if (chart.chart_type === "horizontal_bar") {
          const yBand = h / Math.max(1, labels.length);
          const yStart = top + yBand * index + yBand * 0.2;
          const hBar = yBand * 0.6;
          const xStart = left;
          const xEnd = left + ((numeric - yMin) / Math.max(1e-9, yMax - yMin)) * w;
          x = Math.min(xStart, xEnd);
          width = Math.abs(xEnd - xStart);
          y = yStart;
          height = hBar;
        }

        if (chart.chart_type === "stacked_bar") {
          const previous = datasets.slice(0, dsIndex).reduce((sum, s) => sum + toNumber(s.data?.[index]), 0);
          const topValue = previous + numeric;
          y = yScale(topValue);
          height = yScale(previous) - y;
          x = xBase + xSlot * 0.2;
          width = xSlot * 0.6;
        }

        const rect = createSvg("rect", {
          x,
          y: Math.min(y, top + h),
          width,
          height: Math.max(0, height),
          fill: color,
          rx: 4,
          opacity: 0.9,
        });
        svg.append(rect);
        hitRegions.push({
          contains: (mx, my) => mx >= x && mx <= x + width && my >= y && my <= y + Math.max(0, height),
          lines: [`${labels[index] || `Item ${index + 1}`}`, `${set.label}: ${formatNumber(value)}`],
        });
      });
    });
  }

  const shellRect = () => shell.getBoundingClientRect();
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const scaleX = 960 / Math.max(1, rect.width);
    const scaleY = 420 / Math.max(1, rect.height);
    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;
    const match = hitRegions.find((region) => region.contains(x, y));
    if (!match) {
      tooltip.hidden = true;
      return;
    }
    setTooltip(tooltip, match.lines, event.clientX - shellRect().left, event.clientY - shellRect().top, shellRect());
  });
  svg.addEventListener("mouseleave", () => {
    tooltip.hidden = true;
  });

  const ro = new ResizeObserver(() => {
    tooltip.hidden = true;
  });
  ro.observe(shell);

  return {
    svg,
    destroy() {
      ro.disconnect();
    },
  };
}

export function renderLegend(container, datasets, hiddenSeries, onToggle) {
  container.textContent = "";
  const legend = document.createElement("div");
  legend.className = "legend";
  const palette = getPalette();
  datasets.forEach((set, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = palette[index % palette.length];
    swatch.style.opacity = hiddenSeries.has(index) ? "0.3" : "1";
    const label = document.createElement("span");
    label.textContent = set.label || `Series ${index + 1}`;
    button.append(swatch, label);
    button.addEventListener("click", () => onToggle(index));
    legend.append(button);
  });
  container.append(legend);
}
