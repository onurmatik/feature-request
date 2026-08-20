(() => {
  const panel = document.querySelector("[data-fr-panel]");
  if (!panel) return;

  const form = panel.querySelector("[data-fr-form]");
  const feedback = panel.querySelector("[data-fr-feedback]");
  const success = panel.querySelector("[data-fr-success]");
  const feedbackField = form?.querySelector('textarea[name="feedback"]');
  const issueLink = success?.querySelector("[data-fr-issue-link]");
  const submitButton = form?.querySelector('button[type="submit"]');
  const preview = panel.dataset.preview === "true";
  const minimumFeedbackLength = 20;

  function submissionId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    const values = new Uint8Array(16);
    window.crypto.getRandomValues(values);
    values[6] = (values[6] & 0x0f) | 0x40;
    values[8] = (values[8] & 0x3f) | 0x80;
    const hex = Array.from(values, (value) => value.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }

  const clientSubmissionId = submissionId();

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
      window.setTimeout(() => feedbackField?.focus(), 0);
    }
  });

  feedbackField?.addEventListener("input", () => feedbackField.setCustomValidity(""));

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const normalizedFeedback = String(feedbackField?.value || "").trim();
    if (normalizedFeedback.length < minimumFeedbackLength) {
      feedbackField?.setCustomValidity(
        `Feedback must be at least ${minimumFeedbackLength} characters.`
      );
    } else {
      feedbackField?.setCustomValidity("");
    }
    if (preview || !form.reportValidity()) return;

    const turnstileToken = form.querySelector('[name="cf-turnstile-response"]')?.value || "";
    if (!turnstileToken) {
      feedback.textContent = "Complete the human verification challenge.";
      feedback.dataset.tone = "error";
      return;
    }

    const body = {
      feedback: normalizedFeedback,
      submission_id: clientSubmissionId,
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
      if (!payload.issue_url) {
        feedback.textContent = "The request was created, but its link is unavailable.";
        feedback.dataset.tone = "error";
        return;
      }
      issueLink.href = payload.issue_url;
      form.hidden = true;
      success.hidden = false;
      message("submitted");
    } catch {
      feedback.textContent = "The request could not be sent. Please try again.";
      feedback.dataset.tone = "error";
      window.turnstile?.reset();
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Send feedback";
    }
  });

  message("ready");
})();
