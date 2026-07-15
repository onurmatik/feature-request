(() => {
  const GLOBAL_KEY = "__featureRequestWidgetLoader";
  if (window[GLOBAL_KEY]) {
    window[GLOBAL_KEY].boot();
    return;
  }

  const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
  const OWNER = /^[a-z0-9_]+$/;
  const PROJECT = /^[a-z0-9_-]+$/;

  function safeOrigin(value, fallback) {
    try {
      const parsed = new URL(value || fallback);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.origin : fallback;
    } catch {
      return fallback;
    }
  }

  function contrast(color) {
    const values = [1, 3, 5].map((index) => parseInt(color.slice(index, index + 2), 16));
    return (values[0] * 299 + values[1] * 587 + values[2] * 114) / 1000 > 160
      ? "#111827"
      : "#ffffff";
  }

  function init(script) {
    if (script.dataset.frInitialized === "true") return;
    script.dataset.frInitialized = "true";

    const owner = String(script.dataset.frOwner || "").trim().toLowerCase();
    const project = String(script.dataset.frProject || "").trim().toLowerCase();
    if (!OWNER.test(owner) || !PROJECT.test(project)) {
      console.error("FeatureRequest widget requires valid data-fr-owner and data-fr-project values.");
      return;
    }

    const scriptUrl = new URL(script.src, window.location.href);
    const origin = safeOrigin(script.dataset.frOrigin, scriptUrl.origin);
    const color = HEX_COLOR.test(script.dataset.frColor || "")
      ? script.dataset.frColor.toUpperCase()
      : "#06B6D4";
    const label = String(script.dataset.frLabel || "Feedback").trim().slice(0, 32) || "Feedback";
    const position = script.dataset.frPosition === "left" ? "left" : "right";

    const host = document.createElement("div");
    host.setAttribute("data-feature-request-widget", "");
    const shadow = host.attachShadow({ mode: "open" });

    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = new URL("embed-loader.css", scriptUrl).href;

    const wrapper = document.createElement("div");
    wrapper.className = "fr-widget";
    wrapper.dataset.position = position;
    wrapper.style.setProperty("--fr-widget-accent", color);
    wrapper.style.setProperty("--fr-widget-contrast", contrast(color));

    const panel = document.createElement("div");
    panel.className = "fr-widget__panel";
    panel.id = `fr-widget-panel-${owner}-${project}`;

    const frame = document.createElement("iframe");
    frame.className = "fr-widget__frame";
    frame.title = `Send feedback to ${project}`;
    frame.src = `${origin}/embed/${encodeURIComponent(owner)}/${encodeURIComponent(project)}/?accent=${encodeURIComponent(color)}`;
    frame.loading = "eager";
    frame.setAttribute(
      "sandbox",
      "allow-forms allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
    );
    panel.appendChild(frame);

    const launcher = document.createElement("button");
    launcher.className = "fr-widget__launcher";
    launcher.type = "button";
    launcher.setAttribute("aria-expanded", "false");
    launcher.setAttribute("aria-controls", panel.id);
    launcher.setAttribute("aria-label", `Open ${label}`);
    launcher.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>';

    function setOpen(open) {
      wrapper.classList.toggle("fr-widget--open", open);
      launcher.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        window.setTimeout(() => {
          frame.focus({ preventScroll: true });
          frame.contentWindow?.focus();
          frame.contentWindow?.postMessage(
            { source: "feature-request-widget-host", type: "focus" },
            origin
          );
        }, 0);
      } else {
        launcher.focus({ preventScroll: true });
      }
    }

    launcher.addEventListener("click", () => setOpen(!wrapper.classList.contains("fr-widget--open")));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && wrapper.classList.contains("fr-widget--open")) setOpen(false);
    });
    window.addEventListener("message", (event) => {
      if (event.origin !== origin || event.source !== frame.contentWindow) return;
      if (event.data?.source !== "feature-request-widget") return;
      if (event.data.type === "close") setOpen(false);
    });

    wrapper.append(panel, launcher);
    shadow.append(stylesheet, wrapper);
    document.body.appendChild(host);
  }

  function boot() {
    document.querySelectorAll("script[data-fr-owner][data-fr-project]").forEach(init);
  }

  window[GLOBAL_KEY] = { boot };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
