export function showToast(message, kind = "info") {
  const region = document.getElementById("toast-region");
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.dataset.kind = kind;
  toast.textContent = message;
  region.append(toast);
  window.setTimeout(() => toast.remove(), 2600);
}

export function autosize(textarea) {
  const apply = () => {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(200, textarea.scrollHeight)}px`;
  };
  textarea.addEventListener("input", apply);
  apply();
}

export function renderSkeletons(target, count = 3) {
  target.textContent = "";
  for (let i = 0; i < count; i += 1) {
    const sk = document.createElement("div");
    sk.className = "skeleton";
    target.append(sk);
  }
}

function trapFocus(dialog) {
  const selectors = "button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])";
  const focusable = Array.from(dialog.querySelectorAll(selectors)).filter((el) => !el.hasAttribute("disabled"));
  if (!focusable.length) return () => {};
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  first.focus();
  function onKeydown(event) {
    if (event.key === "Escape") dialog.close();
    if (event.key !== "Tab") return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  dialog.addEventListener("keydown", onKeydown);
  return () => dialog.removeEventListener("keydown", onKeydown);
}

export function openDialog(dialog, title, contentNode) {
  dialog.textContent = "";
  const body = document.createElement("div");
  body.className = "dialog-body";
  const head = document.createElement("div");
  head.className = "row between";
  const heading = document.createElement("h2");
  heading.textContent = title;
  const close = document.createElement("button");
  close.className = "btn";
  close.textContent = "Close";
  close.addEventListener("click", () => dialog.close());
  head.append(heading, close);
  body.append(head, contentNode);
  dialog.append(body);

  const previousOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  const releaseFocusTrap = trapFocus(dialog);
  dialog.addEventListener("close", () => {
    releaseFocusTrap();
    document.body.style.overflow = previousOverflow;
  }, { once: true });

  dialog.showModal();
}

export function setupCommandPalette(onCommand) {
  const trigger = document.getElementById("command-btn");
  const palette = document.getElementById("command-palette");
  function open() {
    const wrapper = document.createElement("div");
    const input = document.createElement("input");
    input.className = "input";
    input.placeholder = "Type a prompt and press Enter";
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && input.value.trim()) {
        onCommand(input.value.trim());
        palette.close();
      }
    });
    const hint = document.createElement("p");
    hint.className = "text-muted";
    hint.textContent = "Try: Compare completion rates by course.";
    wrapper.append(input, hint);
    openDialog(palette, "Command palette", wrapper);
  }
  trigger.addEventListener("click", open);
  window.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      open();
    }
  });
}

export function selectPanel(tabName) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === tabName);
  });
  document.querySelectorAll(".panel[data-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.panel === tabName);
  });
}
