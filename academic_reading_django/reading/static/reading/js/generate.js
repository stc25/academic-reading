document.addEventListener("DOMContentLoaded", () => {
  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : null;
  }
  const csrftoken = getCookie("arm_csrftoken");

  async function streamInto(url, body, outEl, indicatorEl, button) {
    outEl.hidden = false;
    outEl.textContent = "";
    indicatorEl.classList.add("active");
    if (button) button.disabled = true;

    const headers = { "X-CSRFToken": csrftoken };
    if (!(body instanceof FormData)) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    }

    try {
      const resp = await fetch(url, { method: "POST", headers, body: body || "" });
      if (resp.status === 409) {
        // Already generated (e.g. a second tab): just show the stored result.
        if (window.keepWorkInView) window.keepWorkInView();
        window.location.reload();
        return;
      }
      if (!resp.ok || !resp.body) {
        outEl.textContent = "Something went wrong (" + resp.status + "). Try again.";
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        outEl.textContent += decoder.decode(value, { stream: true });
        outEl.scrollTop = outEl.scrollHeight;
      }
      // The server has now saved the full turn — reload to get the
      // sanitised, markdown-rendered version (and, for close commentary,
      // the anchored text pane) rather than building a second render path
      // client-side.
      if (window.keepWorkInView) window.keepWorkInView();
      window.location.reload();
    } catch (err) {
      outEl.textContent = "Network error — try again.";
    } finally {
      indicatorEl.classList.remove("active");
      if (button) button.disabled = false;
    }
  }

  const genBtn = document.getElementById("generate-btn");
  if (genBtn) {
    genBtn.addEventListener("click", () => {
      streamInto(
        genBtn.dataset.url,
        "",
        document.getElementById("live-output"),
        document.getElementById("streaming-indicator"),
        genBtn
      );
    });
  }

  const draftForm = document.getElementById("draft-form");
  if (draftForm) {
    draftForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const submitBtn = draftForm.querySelector("button[type=submit]");
      streamInto(
        draftForm.dataset.url,
        new FormData(draftForm),
        document.getElementById("live-output"),
        document.getElementById("streaming-indicator"),
        submitBtn
      );
    });
  }
});
