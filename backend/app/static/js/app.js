import { analyzeCsv, getHealth } from "./api.js";
import { renderChart, renderLegend } from "./charts.js";
import { downloadCsv, downloadPseudoXlsx, downloadText, exportSvgAsPng } from "./export.js";
import { getIcon } from "./icons.js";
import { createRouter } from "./router.js";
import { getState, setState, subscribe, updateState } from "./state.js";
import { DataTable } from "./table.js";
import { autosize, openDialog, renderSkeletons, selectPanel, setupCommandPalette, showToast } from "./ui.js";

const els = {
  appRoot: document.getElementById("app"),
  routeLabel: document.getElementById("route-label"),
  modelSelect: document.getElementById("model-select"),
  modelBadge: document.getElementById("model-badge"),
  qualityBadge: document.getElementById("quality-badge"),
  latencyBadge: document.getElementById("latency-badge"),
  promptInput: document.getElementById("prompt-input"),
  sendBtn: document.getElementById("send-btn"),
  rerunBtn: document.getElementById("rerun-btn"),
  fileInput: document.getElementById("file-input"),
  dropzone: document.getElementById("dropzone"),
  fileLabel: document.getElementById("file-label"),
  fileChipRow: document.getElementById("file-chip-row"),
  insightList: document.getElementById("insight-list"),
  insightTemplate: document.getElementById("insight-template"),
  pinnedList: document.getElementById("pinned-list"),
  insightSearch: document.getElementById("insight-search"),
  nextStepsList: document.getElementById("next-steps-list"),
  chartList: document.getElementById("chart-list"),
  chartModal: document.getElementById("chart-modal"),
  commandPalette: document.getElementById("command-palette"),
  projectTree: document.getElementById("project-tree"),
  chatSearch: document.getElementById("chat-search"),
  starterPrompts: document.getElementById("starter-prompts"),
  progressCard: document.getElementById("progress-card"),
  stepper: document.getElementById("stepper"),
  llmBanner: document.getElementById("llm-banner"),
};

const table = new DataTable(document.getElementById("analysis-table"));
const chartControllers = new Map();

const starterPrompts = [
  "Show me participation data by course.",
  "Which courses have the biggest completion gap?",
  "Summarize assignment completion and next actions.",
];

function ensureTheme(preference) {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = preference === "system" ? (prefersDark ? "dark" : "light") : preference;
  document.documentElement.dataset.theme = resolved;
  localStorage.setItem("theme", preference);
}

function toSeverity(text) {
  const lower = String(text).toLowerCase();
  if (lower.includes("risk") || lower.includes("drop") || lower.includes("low")) return "danger";
  if (lower.includes("watch") || lower.includes("gap")) return "warning";
  return "success";
}

function normalizeAnalysis(raw) {
  const chartType = raw.chart_type || "bar";
  const chartRows = raw.chart?.data || [];
  const categoryKey = raw.chart?.category_key;
  const valueKey = raw.chart?.value_key;
  const labels = chartRows.map((row) => String(row[categoryKey] ?? ""));
  const values = chartRows.map((row) => Number(row[valueKey]) || 0);
  const chart = raw.chart
    ? {
        id: "analysis-chart",
        title: raw.chart.title,
        chart_type: chartType,
        data: { labels, datasets: [{ label: valueKey || "Value", data: values }] },
        rows: chartRows,
      }
    : null;

  const insights = (raw.insights || []).map((detail, index) => ({
    id: `insight-${index}`,
    title: String(detail).split(".")[0] || `Insight ${index + 1}`,
    detail: String(detail),
    severity: toSeverity(detail),
    confidence: 85 + (index % 4) * 3,
  }));

  return {
    source: raw.source,
    rowCount: raw.row_count || 0,
    filename: raw.filename || "",
    qualityScore: Math.max(60, Math.min(99, 100 - Math.round((raw.column_count || 0) * 0.4))),
    insights,
    charts: chart ? [chart] : [],
    nextSteps: (raw.next_steps || []).map((step) => String(step)),
    rows: chartRows,
    tokenUsage: raw.token_usage || null,
  };
}

function renderProjectTree(state) {
  els.projectTree.textContent = "";
  const query = state.chatSearch.toLowerCase();
  state.projects.forEach((project) => {
    const projectBtn = document.createElement("button");
    projectBtn.className = "project-row";
    projectBtn.textContent = project.name;
    projectBtn.type = "button";
    projectBtn.addEventListener("click", () => router.go(project.id, project.chats[0]?.id || "overview"));
    els.projectTree.append(projectBtn);

    project.chats
      .filter((chat) => !query || chat.title.toLowerCase().includes(query))
      .forEach((chat) => {
        const chatBtn = document.createElement("button");
        chatBtn.className = "chat-row";
        chatBtn.type = "button";
        chatBtn.textContent = chat.title;
        if (state.route.projectId === project.id && state.route.chatId === chat.id) {
          chatBtn.setAttribute("aria-current", "page");
        }
        chatBtn.addEventListener("click", () => router.go(project.id, chat.id));
        els.projectTree.append(chatBtn);
      });
  });
}

function renderStarterPrompts() {
  els.starterPrompts.textContent = "";
  const title = document.createElement("h2");
  title.textContent = "Suggested starter prompts";
  const row = document.createElement("div");
  row.className = "row";
  starterPrompts.forEach((prompt) => {
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.type = "button";
    btn.textContent = prompt;
    btn.addEventListener("click", () => {
      setState({ prompt });
      els.promptInput.value = prompt;
      els.promptInput.dispatchEvent(new Event("input"));
    });
    row.append(btn);
  });
  els.starterPrompts.append(title, row);
}

function renderProgress(steps, active) {
  els.progressCard.hidden = false;
  els.stepper.textContent = "";
  steps.forEach((step, index) => {
    const item = document.createElement("li");
    item.textContent = step;
    if (index <= active) item.classList.add("active");
    els.stepper.append(item);
  });
}

function hideProgress() {
  els.progressCard.hidden = true;
}

function renderInsights(state) {
  const analysis = state.analysis;
  els.insightList.textContent = "";
  els.pinnedList.textContent = "";
  if (!analysis) {
    renderSkeletons(els.insightList, 3);
    return;
  }

  const query = state.insightsFilter.toLowerCase();
  const filtered = analysis.insights.filter((insight) => (`${insight.title} ${insight.detail}`).toLowerCase().includes(query));

  filtered.forEach((insight) => {
    const fragment = els.insightTemplate.content.cloneNode(true);
    fragment.querySelector("[data-role=severity]").textContent = insight.severity;
    fragment.querySelector("[data-role=confidence]").textContent = `${insight.confidence}% confidence`;
    fragment.querySelector("[data-role=title]").textContent = insight.title;
    fragment.querySelector("[data-role=detail]").textContent = insight.detail;
    const pin = fragment.querySelector("[data-action=pin]");
    pin.textContent = state.pinnedInsightIds.includes(insight.id) ? "★" : "☆";
    pin.addEventListener("click", () => {
      updateState((current) => ({
        ...current,
        pinnedInsightIds: current.pinnedInsightIds.includes(insight.id)
          ? current.pinnedInsightIds.filter((id) => id !== insight.id)
          : current.pinnedInsightIds.concat(insight.id),
      }));
    });
    fragment.querySelector("[data-action=copy]").addEventListener("click", async () => {
      await navigator.clipboard.writeText(`${insight.title}: ${insight.detail}`);
      showToast("Insight copied");
    });
    els.insightList.append(fragment);
  });

  const pinned = analysis.insights.filter((insight) => state.pinnedInsightIds.includes(insight.id));
  if (!pinned.length) {
    const note = document.createElement("p");
    note.className = "text-muted";
    note.textContent = "Pin insights to build your report board.";
    els.pinnedList.append(note);
  } else {
    pinned.forEach((insight) => {
      const item = document.createElement("p");
      item.textContent = `• ${insight.title}`;
      els.pinnedList.append(item);
    });
  }
}

function createChartActions(chart, host, chartContainer) {
  const actions = document.createElement("div");
  actions.className = "row gap-sm";

  const expand = document.createElement("button");
  expand.className = "btn btn-icon";
  expand.type = "button";
  expand.ariaLabel = "Expand chart";
  expand.innerHTML = getIcon("expand");
  expand.addEventListener("click", () => {
    const modalBody = document.createElement("div");
    const shell = document.createElement("div");
    shell.className = "chart-shell";
    modalBody.append(shell);
    renderChart(shell, chart, { hiddenSeries: new Set() });
    openDialog(els.chartModal, chart.title, modalBody);
  });

  const png = document.createElement("button");
  png.className = "btn btn-icon";
  png.type = "button";
  png.ariaLabel = "Download chart PNG";
  png.innerHTML = getIcon("download");
  png.addEventListener("click", async () => {
    const svg = chartContainer.querySelector("svg");
    if (!svg) return;
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg-elevated").trim() || "#ffffff";
    await exportSvgAsPng(svg, `${chart.id || "chart"}.png`, bg);
  });

  const csv = document.createElement("button");
  csv.className = "btn btn-icon";
  csv.type = "button";
  csv.ariaLabel = "Download chart data CSV";
  csv.innerHTML = getIcon("csv");
  csv.addEventListener("click", () => {
    downloadCsv(`${chart.id || "chart"}.csv`, chart.rows || []);
  });

  const xlsx = document.createElement("button");
  xlsx.className = "btn btn-icon";
  xlsx.type = "button";
  xlsx.textContent = "XLSX";
  xlsx.addEventListener("click", () => {
    downloadPseudoXlsx(`${chart.id || "chart"}.xlsx`, chart.rows || []);
  });

  const jsonCopy = document.createElement("button");
  jsonCopy.className = "btn";
  jsonCopy.type = "button";
  jsonCopy.textContent = "Copy JSON";
  jsonCopy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(JSON.stringify(chart.rows || [], null, 2));
    showToast("Chart data copied as JSON");
  });

  const mdCopy = document.createElement("button");
  mdCopy.className = "btn";
  mdCopy.type = "button";
  mdCopy.textContent = "Copy Markdown";
  mdCopy.addEventListener("click", async () => {
    const rows = chart.rows || [];
    if (!rows.length) return;
    const cols = Object.keys(rows[0]);
    const head = `| ${cols.join(" | ")} |`;
    const sep = `| ${cols.map(() => "---").join(" | ")} |`;
    const body = rows.map((row) => `| ${cols.map((col) => String(row[col] ?? "")).join(" | ")} |`).join("\n");
    await navigator.clipboard.writeText(`${head}\n${sep}\n${body}`);
    showToast("Chart data copied as Markdown");
  });

  actions.append(expand, png, csv, xlsx, jsonCopy, mdCopy);
  host.append(actions);
}

function renderCharts(state) {
  els.chartList.textContent = "";
  chartControllers.forEach((controller) => controller?.destroy?.());
  chartControllers.clear();
  if (!state.analysis) {
    renderSkeletons(els.chartList, 2);
    table.setRows([]);
    return;
  }

  state.analysis.charts.forEach((chart, index) => {
    const card = document.createElement("article");
    card.className = "chart-card";
    const head = document.createElement("div");
    head.className = "chart-head";
    const title = document.createElement("h3");
    title.textContent = chart.title;
    head.append(title);

    const chartHost = document.createElement("div");
    chartHost.className = "chart-shell";
    const legendHost = document.createElement("div");
    const hiddenSeries = new Set();

    const draw = () => {
      chartHost.textContent = "";
      const controller = renderChart(chartHost, chart, { hiddenSeries });
      chartControllers.set(`${chart.id}-${index}`, controller);
      renderLegend(legendHost, chart.data.datasets || [], hiddenSeries, (seriesIndex) => {
        if (hiddenSeries.has(seriesIndex)) hiddenSeries.delete(seriesIndex);
        else hiddenSeries.add(seriesIndex);
        draw();
      });
    };

    draw();

    createChartActions(chart, head, chartHost);

    card.append(head, chartHost, legendHost);
    els.chartList.append(card);
  });

  table.setRows(state.analysis.rows || []);
}

function renderNextSteps(state) {
  els.nextStepsList.textContent = "";
  if (!state.analysis) {
    renderSkeletons(els.nextStepsList, 3);
    return;
  }
  state.analysis.nextSteps.forEach((step) => {
    const card = document.createElement("article");
    card.className = "insight-item";
    const text = document.createElement("p");
    text.textContent = step;
    const button = document.createElement("button");
    button.className = "btn btn-primary";
    button.textContent = "Run this next step";
    button.addEventListener("click", () => {
      els.promptInput.value = step;
      setState({ prompt: step });
      runAnalysis(step);
    });
    card.append(text, button);
    els.nextStepsList.append(card);
  });
}

function renderFileChip(state) {
  els.fileChipRow.textContent = "";
  if (!state.upload) return;
  const chip = document.createElement("span");
  chip.className = "file-chip";
  chip.textContent = `${state.upload.name} · ${(state.upload.size / 1024).toFixed(1)} KB`;
  const remove = document.createElement("button");
  remove.className = "btn btn-icon";
  remove.textContent = "×";
  remove.type = "button";
  remove.setAttribute("aria-label", "Remove file");
  remove.addEventListener("click", () => {
    setState({ upload: null });
    els.fileLabel.textContent = "Drop a CSV file here or click to attach";
  });
  chip.append(remove);
  els.fileChipRow.append(chip);
}

function render(state) {
  ensureTheme(state.themePreference);
  els.modelBadge.textContent = `Model: ${state.model}`;
  els.qualityBadge.textContent = `Data quality ${state.analysis?.qualityScore ?? "—"}%`;
  const token = state.metrics.tokens ? ` · ${state.metrics.tokens} tokens` : "";
  els.latencyBadge.textContent = `Latency ${state.metrics.latencyMs ?? "—"} ms${token}`;
  const project = state.projects.find((item) => item.id === state.route.projectId);
  const chat = project?.chats.find((item) => item.id === state.route.chatId);
  els.routeLabel.textContent = `${project?.name || "Project"} · ${chat?.title || "Chat"}`;

  renderProjectTree(state);
  renderFileChip(state);
  renderInsights(state);
  renderCharts(state);
  renderNextSteps(state);
}

function validateCsv(file) {
  const mime = (file.type || "").toLowerCase();
  const name = file.name.toLowerCase();
  if (!name.endsWith(".csv") && mime !== "text/csv" && mime !== "application/vnd.ms-excel") {
    showToast("Only CSV files are allowed", "danger");
    return false;
  }
  return true;
}

async function runAnalysis(forcedPrompt) {
  const state = getState();
  if (!state.upload) {
    showToast("Attach a CSV file first", "warning");
    return;
  }

  const prompt = forcedPrompt || els.promptInput.value.trim();
  if (!prompt) {
    showToast("Enter a question to analyze", "warning");
    return;
  }

  try {
    renderSkeletons(els.insightList, 3);
    renderSkeletons(els.chartList, 2);
    renderSkeletons(els.nextStepsList, 2);

    const result = await analyzeCsv({
      file: state.upload,
      prompt,
      model: state.model,
      onProgress: ({ steps, active }) => renderProgress(steps, active),
    });

    const analysis = normalizeAnalysis(result.body);
    setState({
      prompt,
      analysis,
      metrics: {
        latencyMs: result.elapsedMs,
        tokens: analysis.tokenUsage,
      },
    });

    hideProgress();
    els.llmBanner.hidden = analysis.source !== "pandas";
    showToast("Analysis complete", "success");
  } catch (error) {
    hideProgress();
    showToast(error instanceof Error ? error.message : "Analysis failed", "danger");
  }
}

function handleFileSelection(file) {
  if (!file || !validateCsv(file)) return;
  setState({ upload: file });
  els.fileLabel.textContent = "CSV attached";
}

function setupEvents() {
  renderStarterPrompts();
  autosize(els.promptInput);

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = getState().themePreference;
    const next = current === "light" ? "dark" : current === "dark" ? "system" : "light";
    setState({ themePreference: next });
    showToast(`Theme set to ${next}`);
  });

  document.getElementById("sidebar-toggle").addEventListener("click", () => {
    document.body.classList.toggle("sidebar-collapsed");
  });

  document.getElementById("new-project-btn").addEventListener("click", () => {
    const id = `project-${Date.now()}`;
    updateState((state) => ({
      ...state,
      projects: state.projects.concat({ id, name: `Project ${state.projects.length + 1}`, chats: [{ id: "chat-1", title: "New chat" }] }),
      route: { projectId: id, chatId: "chat-1" },
    }));
    router.go(id, "chat-1");
  });

  document.getElementById("new-chat-btn").addEventListener("click", () => {
    updateState((state) => ({
      ...state,
      projects: state.projects.map((project) => {
        if (project.id !== state.route.projectId) return project;
        const nextIndex = project.chats.length + 1;
        return { ...project, chats: project.chats.concat({ id: `chat-${Date.now()}`, title: `Chat ${nextIndex}` }) };
      }),
    }));
  });

  els.modelSelect.addEventListener("change", () => setState({ model: els.modelSelect.value }));
  els.chatSearch.addEventListener("input", () => setState({ chatSearch: els.chatSearch.value }));
  els.insightSearch.addEventListener("input", () => setState({ insightsFilter: els.insightSearch.value }));

  els.fileInput.addEventListener("change", () => handleFileSelection(els.fileInput.files?.[0]));
  els.dropzone.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      els.fileInput.click();
    }
  });
  ["dragenter", "dragover"].forEach((name) => {
    els.dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      els.dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    els.dropzone.addEventListener(name, () => els.dropzone.classList.remove("dragover"));
  });
  els.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    handleFileSelection(event.dataTransfer?.files?.[0]);
  });

  els.sendBtn.addEventListener("click", () => runAnalysis());
  els.rerunBtn.addEventListener("click", () => runAnalysis());
  els.promptInput.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") runAnalysis();
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => selectPanel(tab.dataset.tab));
  });
  selectPanel("insights");

  document.getElementById("compare-toggle").addEventListener("click", () => {
    updateState((state) => ({ ...state, compareMode: !state.compareMode }));
    showToast(getState().compareMode ? "Compare mode enabled" : "Compare mode disabled");
  });

  document.getElementById("export-report-btn").addEventListener("click", () => {
    const analysis = getState().analysis;
    if (!analysis) return;
    const report = {
      generatedAt: new Date().toISOString(),
      quality: analysis.qualityScore,
      insights: analysis.insights,
      next_steps: analysis.nextSteps,
      chart_rows: analysis.rows,
    };
    downloadText("analysis-report.json", JSON.stringify(report, null, 2), "application/json");
  });

  setupCommandPalette((prompt) => {
    els.promptInput.value = prompt;
    setState({ prompt });
    runAnalysis(prompt);
  });
}

const router = createRouter((route) => setState({ route }));

subscribe(render);
setupEvents();

getHealth()
  .then(() => showToast("Backend connected"))
  .catch(() => showToast("Backend unavailable", "warning"));
