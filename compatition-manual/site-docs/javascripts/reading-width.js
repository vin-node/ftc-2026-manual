(() => {
  const storageKey = "biobuzz-reading-width";
  const modes = ["comfortable", "wide", "full"];

  function savedMode() {
    try {
      const value = localStorage.getItem(storageKey);
      return modes.includes(value) ? value : "wide";
    } catch {
      return "wide";
    }
  }

  function applyMode(mode, control) {
    document.documentElement.dataset.manualWidth = mode;
    control?.querySelectorAll("button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.width === mode));
    });
  }

  function mountControl() {
    const content = document.querySelector(".md-content__inner");
    if (!content || content.querySelector(".reading-width-control")) return;

    const control = document.createElement("div");
    control.className = "reading-width-control";
    control.setAttribute("role", "group");
    control.setAttribute("aria-label", "Reading width");

    const label = document.createElement("span");
    label.className = "reading-width-label";
    label.textContent = "Reading width";
    control.append(label);

    for (const mode of modes) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.width = mode;
      button.textContent = mode[0].toUpperCase() + mode.slice(1);
      button.addEventListener("click", () => {
        try {
          localStorage.setItem(storageKey, mode);
        } catch {
          // The current page still receives the selected width.
        }
        applyMode(mode, control);
      });
      control.append(button);
    }

    content.prepend(control);
    applyMode(savedMode(), control);
  }

  applyMode(savedMode());
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountControl, { once: true });
  } else {
    mountControl();
  }
})();
