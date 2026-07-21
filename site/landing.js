(() => {
  const button = document.querySelector("#copy-agent-prompt");
  const prompt = document.querySelector("#home-setup-prompt");
  const status = document.querySelector("#home-copy-status");
  const toggle = document.querySelector("#toggle-agent-prompt");
  const preview = document.querySelector("#home-prompt-preview-text");

  if (!button || !prompt || !status) {
    return;
  }

  const originalLabel = button.dataset.copyLabel || button.textContent;
  const copiedLabel = button.dataset.copiedLabel || originalLabel;

  if (preview) {
    preview.textContent = prompt.value.trim();
  }

  if (toggle && preview) {
    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      const nextExpanded = !expanded;
      toggle.setAttribute("aria-expanded", String(nextExpanded));
      preview.classList.toggle("is-expanded", nextExpanded);
      toggle.textContent = nextExpanded
        ? toggle.dataset.collapseLabel || "Collapse"
        : toggle.dataset.expandLabel || "Expand";
    });
  }

  const fallbackCopy = (text) => {
    const temporary = document.createElement("textarea");
    temporary.value = text;
    temporary.setAttribute("readonly", "");
    temporary.style.position = "fixed";
    temporary.style.inset = "0 auto auto -9999px";
    temporary.style.opacity = "0";
    document.body.appendChild(temporary);
    temporary.focus();
    temporary.select();
    temporary.setSelectionRange(0, temporary.value.length);

    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }

    temporary.remove();
    return copied;
  };

  const markCopied = () => {
    button.textContent = copiedLabel;
    status.textContent = status.dataset.success || "Copied.";
    window.setTimeout(() => {
      button.textContent = originalLabel;
    }, 2400);
  };

  button.addEventListener("click", async () => {
    const text = prompt.value.trim();
    let copied = false;

    if (window.isSecureContext && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch (error) {
        copied = false;
      }
    }

    if (!copied) {
      copied = fallbackCopy(text);
    }

    if (copied) {
      markCopied();
      return;
    }

    status.textContent = status.dataset.failure || "Copy failed.";
  });
})();
