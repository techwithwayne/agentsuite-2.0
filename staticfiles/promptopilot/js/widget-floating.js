// static/promptopilot/js/widget-floating.js

document.addEventListener("DOMContentLoaded", function () {
  // Create the floating button
  const launcher = document.createElement("button");
  launcher.id = "promptopilot-launcher";
  launcher.innerHTML = "🚀 Build Ad";
  document.body.appendChild(launcher);

  // Create the modal container
  const modal = document.createElement("div");
  modal.id = "promptopilot-modal";
  modal.innerHTML = `
    <div class="promptopilot-backdrop"></div>
    <div class="promptopilot-widget-container">
      <iframe id="promptopilot-iframe" src="/promptopilot/ad-builder/" frameborder="0"></iframe>
      <button id="promptopilot-close">&times;</button>
    </div>
  `;
  document.body.appendChild(modal);

  // Show/hide behavior
  launcher.onclick = () => modal.classList.add("visible");
  modal.querySelector("#promptopilot-close").onclick = () =>
    modal.classList.remove("visible");
  modal.querySelector(".promptopilot-backdrop").onclick = () =>
    modal.classList.remove("visible");

  // Optional: sync iframe height to content (if needed)
  window.addEventListener("message", (event) => {
    if (event.data?.type === "promptopilot-resize" && event.data.height) {
      const iframe = document.getElementById("promptopilot-iframe");
      iframe.style.height = event.data.height + "px";
    }
  });
});
