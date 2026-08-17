function normalizeRows(rows) {
  if (!Array.isArray(rows) || !rows.length) return { columns: [], rows: [] };
  const columns = Array.from(rows.reduce((set, row) => {
    Object.keys(row || {}).forEach((key) => set.add(key));
    return set;
  }, new Set()));
  return { columns, rows };
}

export class DataTable {
  constructor(root) {
    this.root = root;
    this.state = { rows: [], columns: [], query: "", filters: {}, sortKey: "", sortDir: "asc", page: 1, pageSize: 8 };
  }

  setRows(rows) {
    const normalized = normalizeRows(rows);
    this.state = { ...this.state, ...normalized, page: 1 };
    this.render();
  }

  render() {
    this.root.textContent = "";
    const controls = document.createElement("div");
    controls.className = "row gap-sm wrap-end";

    const query = document.createElement("input");
    query.className = "input";
    query.placeholder = "Search all columns";
    query.value = this.state.query;
    query.addEventListener("input", () => {
      this.state.query = query.value;
      this.state.page = 1;
      this.render();
    });
    controls.append(query);

    this.state.columns.forEach((column) => {
      const filter = document.createElement("input");
      filter.className = "input";
      filter.placeholder = `Filter ${column}`;
      filter.value = this.state.filters[column] || "";
      filter.setAttribute("aria-label", `Filter ${column}`);
      filter.addEventListener("input", () => {
        this.state.filters[column] = filter.value;
        this.state.page = 1;
        this.render();
      });
      controls.append(filter);
    });

    this.root.append(controls);

    const filteredRows = this.state.rows.filter((row) => {
      const queryMatch = !this.state.query || this.state.columns.some((column) => String(row[column] ?? "").toLowerCase().includes(this.state.query.toLowerCase()));
      if (!queryMatch) return false;
      return this.state.columns.every((column) => {
        const value = this.state.filters[column];
        return !value || String(row[column] ?? "").toLowerCase().includes(value.toLowerCase());
      });
    });

    const sortedRows = filteredRows.sort((a, b) => {
      const key = this.state.sortKey;
      if (!key) return 0;
      const av = a[key];
      const bv = b[key];
      const dir = this.state.sortDir === "asc" ? 1 : -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av ?? "").localeCompare(String(bv ?? "")) * dir;
    });

    const start = (this.state.page - 1) * this.state.pageSize;
    const pageRows = sortedRows.slice(start, start + this.state.pageSize);

    const shell = document.createElement("div");
    shell.className = "table-shell";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    this.state.columns.forEach((column) => {
      const th = document.createElement("th");
      const sortBtn = document.createElement("button");
      sortBtn.type = "button";
      const marker = this.state.sortKey === column ? (this.state.sortDir === "asc" ? " ↑" : " ↓") : "";
      sortBtn.textContent = `${column}${marker}`;
      sortBtn.addEventListener("click", () => {
        if (this.state.sortKey === column) {
          this.state.sortDir = this.state.sortDir === "asc" ? "desc" : "asc";
        } else {
          this.state.sortKey = column;
          this.state.sortDir = "asc";
        }
        this.render();
      });
      th.append(sortBtn);
      headerRow.append(th);
    });

    thead.append(headerRow);
    table.append(thead);

    const tbody = document.createElement("tbody");
    pageRows.forEach((row) => {
      const tr = document.createElement("tr");
      this.state.columns.forEach((column) => {
        const td = document.createElement("td");
        td.textContent = String(row[column] ?? "");
        tr.append(td);
      });
      tbody.append(tr);
    });

    table.append(tbody);
    shell.append(table);
    this.root.append(shell);

    const totalPages = Math.max(1, Math.ceil(sortedRows.length / this.state.pageSize));
    const pager = document.createElement("div");
    pager.className = "pagination";
    const prev = document.createElement("button");
    prev.className = "btn";
    prev.textContent = "Prev";
    prev.disabled = this.state.page <= 1;
    prev.addEventListener("click", () => {
      this.state.page -= 1;
      this.render();
    });
    const next = document.createElement("button");
    next.className = "btn";
    next.textContent = "Next";
    next.disabled = this.state.page >= totalPages;
    next.addEventListener("click", () => {
      this.state.page += 1;
      this.render();
    });
    const status = document.createElement("span");
    status.textContent = `Page ${this.state.page} of ${totalPages}`;
    pager.append(prev, status, next);
    this.root.append(pager);
  }
}
