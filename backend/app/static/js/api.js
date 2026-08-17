const PROGRESS_STEPS = ["Parsing CSV", "Profiling", "Reasoning", "Building charts"];

async function parseJson(response) {
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : "Request failed";
    throw new Error(detail);
  }
  return body;
}

export async function getHealth() {
  const response = await fetch("/api/health", { headers: { Accept: "application/json" } });
  return parseJson(response);
}

export async function analyzeCsv({ file, prompt, model, onProgress }) {
  const startedAt = performance.now();
  let index = 0;
  onProgress?.({ steps: PROGRESS_STEPS, active: index });

  const timer = window.setInterval(() => {
    index = Math.min(index + 1, PROGRESS_STEPS.length - 1);
    onProgress?.({ steps: PROGRESS_STEPS, active: index });
  }, 450);

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("prompt", prompt);
    formData.append("model", model || "");
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: formData,
      headers: { Accept: "application/json" },
    });
    const body = await parseJson(response);
    return {
      body,
      elapsedMs: Math.round(performance.now() - startedAt),
      progressSteps: PROGRESS_STEPS,
    };
  } finally {
    window.clearInterval(timer);
    onProgress?.({ steps: PROGRESS_STEPS, active: PROGRESS_STEPS.length - 1 });
  }
}
