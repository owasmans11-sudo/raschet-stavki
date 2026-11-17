(() => {
  if (customElements.get("dash-sources")) return;

  const blocks = "dash-block[id], experimental-dash-block[id], [data-dashboard-block][id]";
  const template = document.createElement("template");
  template.innerHTML = `
    <style>
      :host { display: inline-block; font: 400 14px/1.45 var(--font-sans, system-ui);
        color: var(--foreground, CanvasText); }
      *, *::before, *::after { box-sizing: border-box; }
      [hidden] { display: none !important; }
      button { font: inherit; color: inherit; background: transparent; border: 0; cursor: pointer; }
      button:focus-visible { outline: 2px solid var(--ring, Highlight); outline-offset: 2px; }
      .trigger { display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px;
        border: 1px solid var(--border, #d5d5d5); border-radius: 99px;
        background: var(--background, Canvas); font-weight: 500; }
      button:hover { background: var(--secondary, ButtonFace); }
      svg { width: 16px; height: 16px; fill: none; stroke: currentColor;
        stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
      .panel { position: fixed; inset: 12px 12px 12px auto; margin: 0; padding: 0;
        width: min(350px, calc(100% - 24px)); height: calc(100% - 24px);
        overflow: auto; overscroll-behavior: contain; scrollbar-gutter: stable;
        background: var(--background, Canvas); color: var(--foreground, CanvasText);
        border: 1px solid var(--border, #d5d5d5); border-radius: 16px;
        box-shadow: 0 8px 32px #0002, 0 2px 8px #0001; z-index: 50; }
      @media (prefers-reduced-motion: no-preference) {
        .panel:popover-open { animation: slide-in 160ms ease-out; }
        @keyframes slide-in { from { opacity: 0; transform: translateX(16px); } }
      }
      header { position: sticky; top: 0; display: flex; align-items: center;
        justify-content: space-between; gap: 12px; padding: 14px 16px 10px;
        background: var(--background, Canvas); }
      h2, h3, h4, p { margin: 0; }
      h2, h3 { font-size: 16px; font-weight: 600; }
      h4, .kind, .back, .description { color: var(--muted-foreground, GrayText); }
      h4 { margin: 16px 0 6px; font-size: 12px; font-weight: 500; }
      .close { display: grid; place-items: center; width: 30px; height: 30px;
        border-radius: 99px; background: var(--secondary, ButtonFace); }
      main { padding: 2px 12px 20px; overflow-wrap: anywhere; }
      .back { display: flex; align-items: center; gap: 6px; margin: 0 0 12px;
        padding: 5px 7px; border-radius: 7px; font-size: 12px; }
      .back::before, .row::after { content: ""; width: 5px; height: 5px; flex: none;
        border-block-start: 1px solid; border-inline-end: 1px solid; transform: rotate(45deg); }
      .back::before { transform: rotate(-135deg); }
      .heading, .description, h4, pre, details { margin-inline: 6px; }
      .description { margin-top: 4px; }
      .row { width: 100%; display: flex; align-items: center; gap: 8px;
        padding: 10px 8px; border-radius: 8px; text-align: start; }
      .row::after { margin-inline-start: auto; color: var(--muted-foreground, GrayText); }
      .kind { font-size: 12px; }
      pre { margin-block: 0; padding: 10px; max-height: 220px; overflow: auto;
        white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.5 ui-monospace, monospace;
        background: var(--secondary, ButtonFace); border-radius: 8px; }
      .table-wrap { overflow: auto; margin: 0 6px; border: 1px solid var(--border, #d5d5d5);
        border-radius: 8px; }
      table { width: 100%; border-collapse: collapse; font-size: 12px; }
      th, td { padding: 5px 7px; text-align: start; max-width: 24ch; white-space: nowrap;
        text-overflow: ellipsis; overflow: hidden; }
      th { font-weight: 500; background: var(--secondary, ButtonFace); }
      tr + tr { border-top: 1px solid var(--border, #d5d5d5); }
      .count { margin: 4px 6px; color: var(--muted-foreground, GrayText); font-size: 12px; }
      details { margin-block-start: 10px; }
      summary { cursor: pointer; }
      details pre { margin: 6px 0 0; }
    </style>
    <button class="trigger" type="button" aria-haspopup="dialog" aria-expanded="false">
      <svg aria-hidden="true" viewBox="0 0 20 20"><ellipse cx="10" cy="4.5" rx="6.5" ry="2.5"/>
        <path d="M3.5 4.5v5c0 3.3 13 3.3 13 0v-5M3.5 9.5v5c0 3.3 13 3.3 13 0v-5"/></svg>
      Sources
    </button>
    <section class="panel" role="dialog" aria-labelledby="sources-title" popover="manual" hidden>
      <header><h2 id="sources-title" tabindex="-1">Sources</h2>
        <button type="button" class="close" aria-label="Close sources">
          <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m5 5 10 10M15 5 5 15"/></svg>
        </button>
      </header>
      <main></main>
    </section>`;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function button(label, onClick, className = "row") {
    const node = element("button", label, className);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function blockBindings(block) {
    return new Set((block.getAttribute("sources") || "").split(/\s+/).filter(Boolean));
  }

  function blockTitle(block) {
    return (
      block.getAttribute("heading") ||
      block.getAttribute("aria-label") ||
      block.querySelector("h1,h2,h3,h4,h5,h6")?.textContent?.trim() ||
      block.id
    );
  }

  function sourceKind(binding) {
    if (binding.type === "tool") {
      return binding.tool.startsWith("mcp__codex_apps__kepler_") ? "Kepler" : "Connector";
    }
    return { file: "File", image: "Image", json: "Inline JSON", library: "Library" }[binding.type];
  }

  function clipped(value, limit) {
    return value.length > limit ? value.slice(0, limit - 1) + "…" : value;
  }

  function isScalar(value) {
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
  }

  function renderPreview(section, value, rowsField) {
    section.replaceChildren();
    let records;
    if (rowsField === undefined && Array.isArray(value)) {
      records = value;
    } else {
      const key = rowsField === undefined ? "results" : rowsField.trim();
      if (!key || key.length > 64 || value == null || typeof value !== "object"
        || Array.isArray(value) || !Object.hasOwn(value, key)) return;
      records = value[key];
    }
    if (!Array.isArray(records)) return;
    // Include the final bucket, which often feeds the headline metric.
    const sample = records.length > 10 ? [...records.slice(0, 9), records.at(-1)] : records;
    const rows = sample.filter((row) => row && typeof row === "object" && !Array.isArray(row));
    const columns = new Set();
    for (const row of rows) {
      for (const key of Object.keys(row)) {
        if (isScalar(row[key])) columns.add(key);
        if (columns.size === 8) break;
      }
      if (columns.size === 8) break;
    }
    if (!columns.size) return;
    const table = element("table");
    table.setAttribute("aria-label", "Data preview");
    const header = table.createTHead().insertRow();
    for (const key of columns) {
      const label = element("th", clipped(key, 48));
      label.scope = "col";
      header.append(label);
    }
    const body = table.createTBody();
    for (const row of rows) {
      const record = body.insertRow();
      for (const key of columns) {
        record.insertCell().textContent =
          Object.hasOwn(row, key) && isScalar(row[key]) ? clipped(String(row[key]), 80) : "—";
      }
    }
    const container = element("div", null, "table-wrap");
    container.append(table);
    section.append(element("h4", "Data preview"), container);
    if (records.length > rows.length) {
      section.append(element("p", rows.length + " of " + records.length + " rows", "count"));
    }
  }

  class DashboardSources extends HTMLElement {
    #root = this.attachShadow({ mode: "open" });
    #panel;
    #body;
    #trigger;
    #returnFocus;
    #events;
    #unsubscribe;

    constructor() {
      super();
      this.#root.append(template.content.cloneNode(true));
      this.#panel = this.#root.querySelector(".panel");
      this.#body = this.#root.querySelector("main");
      this.#trigger = this.#root.querySelector(".trigger");
      this.#trigger.addEventListener("click", () => this.showAll());
      this.#root.querySelector(".close").addEventListener("click", () => this.close());
    }

    connectedCallback() {
      this.#events = new AbortController();
      const options = { signal: this.#events.signal };
      document.addEventListener(
        "sourceinspect",
        (event) => {
          if (window.openai?.sandboxDocumentState?.dashboardSourcePanel === true
            || event.defaultPrevented || document.querySelector("dash-sources") !== this) return;
          const block = event.target instanceof Element ? event.target.closest(blocks) : null;
          if (block != null && block.id === event.detail?.id) this.showBlock(block.id);
        },
        options,
      );
      window.addEventListener("openai:set_globals", (event) => {
        const state = event.detail?.globals?.sandboxDocumentState;
        if (state?.dashboardSourcePanel === true) {
          this.#trigger.setAttribute("aria-expanded", String(state.dashboardSourcesOpen === true));
        }
      }, options);
      document.addEventListener(
        "keydown",
        (event) => {
          if (event.key !== "Escape" || event.defaultPrevented || this.#panel.hidden) return;
          event.preventDefault();
          this.close();
        },
        options,
      );
    }

    disconnectedCallback() {
      this.#events.abort();
      this.#stopPreview();
      this.#panel.hidden = true;
      this.#trigger.setAttribute("aria-expanded", "false");
      this.#returnFocus = null;
    }

    close() {
      if (this.#panel.hidden) return;
      this.#stopPreview();
      this.#panel.hidePopover?.();
      this.#panel.hidden = true;
      this.#trigger.setAttribute("aria-expanded", "false");
      const focus = this.#returnFocus?.isConnected ? this.#returnFocus : this.#trigger;
      focus.focus({ preventScroll: true });
      this.#returnFocus = null;
    }

    #stopPreview() {
      this.#unsubscribe?.();
      this.#unsubscribe = null;
    }

    #open() {
      this.#stopPreview();
      const focused = this.#root.activeElement ?? document.activeElement;
      if (
        focused === this.#trigger ||
        (focused && !this.#root.contains(focused) && focused !== document.body)
      ) {
        this.#returnFocus = focused;
      }
      if (this.#panel.hidden) {
        this.#panel.hidden = false;
        this.#panel.showPopover?.();
        this.#trigger.setAttribute("aria-expanded", "true");
      }
      this.#body.replaceChildren();
      this.#panel.scrollTop = 0;
    }

    #heading(title) {
      const heading = element("h3", title, "heading");
      heading.tabIndex = -1;
      this.#body.append(
        button("All sources", () => this.showAll(), "back"),
        heading,
      );
      heading.focus({ preventScroll: true });
    }

    #bindings() {
      return window.openai?.visualization?.bindings ?? {};
    }

    #metadata(name) {
      return Array.from(document.querySelectorAll('meta[name="visualize-source"]')).find(
        (meta) => meta.content === name,
      )?.dataset;
    }

    #sourceRows(names) {
      const bindings = this.#bindings();
      let found = false;
      for (const name of names) {
        if (!Object.hasOwn(bindings, name)) continue;
        found = true;
        const row = button(this.#metadata(name)?.title || name, () => this.showSource(name));
        row.append(element("span", sourceKind(bindings[name]), "kind"));
        this.#body.append(row);
      }
      if (!found) this.#body.append(element("p", "No sources declared.", "description"));
    }

    #requestInspection(selection) {
      if (window.openai?.sandboxDocumentState?.dashboardSourcePanel !== true) return false;
      return !this.dispatchEvent(new CustomEvent("dashboard-source-inspection", {
        bubbles: true, composed: true, cancelable: true, detail: selection,
      }));
    }

    showAll() {
      if (this.#requestInspection({ kind: "all" })) return;
      this.#open();
      this.#sourceRows(Object.keys(this.#bindings()));
      this.#root.querySelector("h2").focus({ preventScroll: true });
    }

    showBlock(id) {
      const block = document.getElementById(id);
      if (!block?.matches(blocks) || this.#requestInspection({ kind: "block", id })) return;
      this.#open();
      this.#heading(blockTitle(block));
      const description = block.getAttribute("description");
      if (description) this.#body.append(element("p", description, "description"));
      this.#sourceRows(blockBindings(block));
    }

    showSource(name) {
      const bindings = this.#bindings();
      if (!Object.hasOwn(bindings, name) || this.#requestInspection({ kind: "source", id: name })) return;
      const binding = bindings[name];
      const metadata = this.#metadata(name);
      this.#open();
      this.#heading(metadata?.title || name);
      if (metadata?.description)
        this.#body.append(element("p", metadata.description, "description"));
      const entity = metadata?.entity?.trim();
      if (entity && entity.length <= 256) this.#body.append(element("p", entity, "kind description"));
      const field = (label, value) =>
        this.#body.append(element("h4", label), element("pre", value));
      if (metadata?.title && metadata.title !== name) field("Binding", name);
      if (binding.type === "tool") {
        const kind = sourceKind(binding);
        if (kind === "Kepler") this.#body.append(element("p", kind, "description"));
        else field("Connector tool", binding.tool);
        const { query } = binding.arguments;
        if (typeof query === "string") {
          field("Query", query);
        } else {
          field("Arguments", JSON.stringify(binding.arguments, null, 2));
        }
        const detail = element("details");
        detail.append(
          element("summary", "Tool details"),
          element("pre", JSON.stringify(binding, null, 2)),
        );
        this.#body.append(detail);
      } else if (binding.type === "file") {
        field("File", binding.path);
      } else if (binding.type === "image") {
        field("Image URL", binding.url);
      } else if (binding.type === "library") {
        field("Library file", binding.libraryFileId);
      } else if (binding.type === "json") {
        field("Inline JSON", JSON.stringify(binding.value, null, 2));
      }

      if (binding.type === "tool" || binding.type === "json") {
        const preview = element("section");
        this.#body.append(preview);
        this.#unsubscribe = window.openai?.visualization?.onData?.(name, (value) =>
          renderPreview(preview, value, metadata?.rows),
        );
      }

      const consumers = Array.from(document.querySelectorAll(blocks)).filter((block) =>
        blockBindings(block).has(name),
      );
      this.#body.append(element("h4", "Used by"));
      if (!consumers.length)
        this.#body.append(element("p", "No blocks declare this source.", "description"));
      for (const block of consumers) {
        this.#body.append(button(blockTitle(block), () => this.showBlock(block.id)));
      }
    }
  }

  customElements.define("dash-sources", DashboardSources);
})();
