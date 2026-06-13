const toast = document.querySelector("[data-toast]");
function notify(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2200);
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  document.execCommand("copy");
  field.remove();
}

document.querySelectorAll("[data-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    const group = button.closest("[data-filter-group]");
    group?.querySelectorAll("[data-filter]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    const filter = button.dataset.filter;
    document.querySelectorAll("[data-company]").forEach((card) => {
      card.hidden = filter !== "all" && card.dataset.company !== filter;
    });
  });
});

document.querySelectorAll("[data-share]").forEach((button) => {
  button.addEventListener("click", async () => {
    const text = button.dataset.share || document.title;
    if (navigator.share) {
      try {
        await navigator.share({ title: document.title, text, url: location.href });
      } catch (error) {
        if (error.name !== "AbortError") notify("Sharing was not available.");
      }
    } else {
      await copyText(`${text} ${location.href}`);
      notify("Case link copied to the clerk's ledger.");
    }
  });
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    await copyText(button.dataset.copy);
    notify("Roast excerpt copied.");
  });
});

const transcript = document.querySelector("[data-transcript]");
if (transcript) {
  const lines = [
    ["Judge Mycelia", "Court is in session. The model will distinguish sourced language from the composite demo claim."],
    ["Prosecutor Thorn", "Exhibit A records a public timeline prediction. Exhibit B records the later qualification. I ask the court to compare confidence, date, and scope."],
    ["Witness 2030", "I have arrived from the promised quarter. The robots are capable, the deployment memo is delayed, and the definition of ‘most work’ has developed unusual flexibility."],
    ["AI Clerk", "Semantic comparison complete: 0.81 contradiction risk. Confidence increased by temporal drift across sources."],
    ["Judge Mycelia", "The claim may be visionary and still be over-broad. Proceed to the credibility test."]
  ];
  const speakers = document.querySelectorAll(".character");
  const thinking = document.querySelector("[data-thinking]");
  const meter = document.querySelector("[data-meter]");
  let lineIndex = 0;
  let courtBusy = false;

  function addLine(role, text, system = false) {
    const row = document.createElement("div");
    row.className = `line${system ? " system" : ""}`;
    row.innerHTML = `<div class="speaker">${role}</div><p>${text}</p>`;
    transcript.appendChild(row);
    transcript.scrollTop = transcript.scrollHeight;
  }

  async function runStep() {
    if (courtBusy) return;
    if (lineIndex >= lines.length) {
      document.querySelector("[data-verdict]")?.classList.add("show");
      notify("Verdict rendered from cited evidence.");
      return;
    }
    courtBusy = true;
    thinking?.classList.add("show");
    document.querySelectorAll("[data-trial-action], [data-convene]").forEach((button) => button.disabled = true);
    await new Promise((resolve) => setTimeout(resolve, 650));
    const [role, text] = lines[lineIndex];
    speakers.forEach((speaker) => speaker.classList.toggle("speaking", speaker.dataset.role === role));
    addLine(role, text, role === "AI Clerk");
    if (meter) meter.style.width = `${64 + lineIndex * 6}%`;
    document.querySelectorAll(".timeline-item")[Math.min(lineIndex, 2)]?.classList.add("active");
    lineIndex += 1;
    thinking?.classList.remove("show");
    courtBusy = false;
    document.querySelectorAll("[data-trial-action], [data-convene]").forEach((button) => button.disabled = false);
  }

  document.querySelectorAll("[data-trial-action]").forEach((button) => {
    button.addEventListener("click", runStep);
  });
  document.querySelector("[data-convene]")?.addEventListener("click", async () => {
    for (let i = 0; i < 3; i += 1) await runStep();
  });
}

function initializeIcons() {
  if (window.lucide) window.lucide.createIcons();
}

initializeIcons();
window.addEventListener("load", initializeIcons, { once: true });
