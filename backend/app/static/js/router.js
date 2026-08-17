function parseHash(hash) {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "projects" && parts[2] === "chats") {
    return { projectId: parts[1], chatId: parts[3] || "overview" };
  }
  return { projectId: "learning", chatId: "overview" };
}

export function createRouter(onRoute) {
  function applyRoute() {
    onRoute(parseHash(window.location.hash));
  }

  window.addEventListener("hashchange", applyRoute);
  applyRoute();

  return {
    go(projectId, chatId) {
      window.location.hash = `/projects/${projectId}/chats/${chatId}`;
    },
    dispose() {
      window.removeEventListener("hashchange", applyRoute);
    },
  };
}
