// Adds the top bar (part name, six-step progress, group label) to every slide.
const PARTS = ["Intro", "Task 1 · Using an agent", "Task 2 · Our own agent", "Task 3 · RAG", "Task 4 · Tools", "Wrap-up"];
document.querySelectorAll(".slide").forEach((slide) => {
  const part = Number(slide.dataset.part);
  const bar = document.createElement("div");
  bar.className = "bar";
  bar.innerHTML = `<b>${part} · ${PARTS[part - 1]}</b>` +
    `<span class="steps">${PARTS.map((_, i) => `<i class="${i === part - 1 ? "on" : ""}"></i>`).join("")}</span>` +
    `<span>${document.body.dataset.group} · Lab 1</span>`;
  slide.prepend(bar);
});
