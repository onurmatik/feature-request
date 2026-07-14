(() => {
  const panel = document.querySelector("[data-fr-panel]");
  if (!panel) return;

  const form = panel.querySelector("[data-fr-form]");
  const feedback = panel.querySelector("[data-fr-feedback]");
  const success = panel.querySelector("[data-fr-success]");
  const submitButton = form?.querySelector('button[type="submit"]');
  const preview = panel.dataset.preview === "true";

  function csrfToken() {
    const part = document.cookie
      .split(";")
      .map((value) => value.trim())
      .find((value) => value.startsWith("csrftoken="));
    return part ? decodeURIComponent(part.slice("csrftoken=".length)) : "";
  }

  function message(type) {
    window.parent.postMessage({ source: "feature-request-widget", type }, "*");
  }

  panel.querySelector("[data-fr-close]")?.addEventListener("click", () => message("close"));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") message("close");
  });
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return;
    if (event.data?.source !== "feature-request-widget-host") return;
    if (event.data.type === "focus") {
      window.setTimeout(() => form?.querySelector("input, select, textarea, button")?.focus(), 0);
    }
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (preview || !form.reportValidity()) return;

    const turnstileToken = form.querySelector('[name="cf-turnstile-response"]')?.value || "";
    if (!turnstileToken) {
      feedback.textContent = "Complete the human verification challenge.";
      feedback.dataset.tone = "error";
      return;
    }

    const values = new FormData(form);
    const body = {
      display_name: String(values.get("display_name") || "").trim(),
      email: String(values.get("email") || "").trim(),
      issue_type: String(values.get("issue_type") || "feature"),
      title: String(values.get("title") || "").trim(),
      description: String(values.get("description") || "").trim(),
      turnstile_token: turnstileToken,
    };

    submitButton.disabled = true;
    submitButton.textContent = "Sending...";
    feedback.textContent = "";
    feedback.dataset.tone = "";
    try {
      const response = await fetch(panel.dataset.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        feedback.textContent = payload.detail || "The request could not be sent.";
        feedback.dataset.tone = "error";
        window.turnstile?.reset();
        return;
      }
      form.hidden = true;
      success.hidden = false;
      message("submitted");
    } catch {
      feedback.textContent = "The request could not be sent. Please try again.";
      feedback.dataset.tone = "error";
      window.turnstile?.reset();
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Submit";
    }
  });

  message("ready");
})();
