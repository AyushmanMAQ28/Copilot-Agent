const listeners = new Set();

const initialState = {
  themePreference: localStorage.getItem("theme") || "system",
  model: "qwen-3.6-27b",
  projects: [
    { id: "learning", name: "Learning analysis", chats: [{ id: "overview", title: "Participation overview" }] },
  ],
  route: { projectId: "learning", chatId: "overview" },
  prompt: "Show me participation, completion, and assignment completion by course.",
  upload: null,
  analysis: null,
  insightsFilter: "",
  chatSearch: "",
  pinnedInsightIds: [],
  compareMode: false,
  metrics: { latencyMs: null, tokens: null },
};

let state = initialState;

export function getState() {
  return state;
}

export function setState(patch) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener(state));
}

export function updateState(updater) {
  state = updater(state);
  listeners.forEach((listener) => listener(state));
}

export function subscribe(listener) {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}
