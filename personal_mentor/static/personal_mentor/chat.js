/* personal_mentor/static/personal_mentor/chat.js
   Version: v2025-08-11-fixed-03
   Changes:
   - Startup health-check to /api/health/
   - Keeps overlay removal + friendly error handling + iframe resize
*/

(function () {
  "use strict";

  // -------- Overlay helpers --------
  function removeLoadingOverlay() {
    try {
      const el = document.getElementById("pm-loading");
      if (el) el.remove();
    } catch {}
  }
  removeLoadingOverlay();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", removeLoadingOverlay, { once: true });
  } else {
    removeLoadingOverlay();
  }

  // -------- Config --------
  const scriptTag = document.currentScript || document.querySelector('script[data-api-base]');
  const DATA_API_BASE = scriptTag && scriptTag.getAttribute("data-api-base");
  const API_BASE = (window.PERSONAL_MENTOR_API_BASE || DATA_API_BASE || "/personal-mentor").replace(/\/+$/, "");

  // DOM refs
  const $ = (s) => document.querySelector(s);
  const $messages = $("#pm-messages");
  const $form = $("#pm-form");
  const $input = $("#pm-input");
  const $reset = $("#pm-reset");

  if (!$messages || !$form || !$input) {
    console.error("[PersonalMentor] Missing required DOM elements.");
    removeLoadingOverlay();
    return;
  }

  // -------- Message helpers --------
  function addMessage(text, who) {
    const wrap = document.createElement("div");
    wrap.className = `pm-msg ${who}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    $messages.appendChild(wrap);
    scrollToBottom();
    postHeight();
    removeLoadingOverlay();
  }

  function scrollToBottom() {
    $messages.scrollTop = $messages.scrollHeight;
  }

  let typingEl = null;
  function showTyping() {
    if (typingEl) return;
    typingEl = document.createElement("div");
    typingEl.className = "pm-msg bot";
    typingEl.innerHTML = `<div class="bubble pm-typing">Mentor is thinking…</div>`;
    $messages.appendChild(typingEl);
    scrollToBottom();
    postHeight();
  }
  function hideTyping() {
    if (!typingEl) return;
    typingEl.remove();
    typingEl = null;
    postHeight();
  }

  // -------- Resize to parent (iframe) --------
  let heightPostTimer = null;
  function postHeight() {
    if (heightPostTimer) cancelAnimationFrame(heightPostTimer);
    heightPostTimer = requestAnimationFrame(() => {
      const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
      try {
        window.parent && window.parent.postMessage({ type: "personal-mentor-resize", height: h }, "*");
      } catch {}
    });
  }

  if ("ResizeObserver" in window) {
    const ro = new ResizeObserver(() => postHeight());
    ro.observe(document.body);
    ro.observe($messages);
  } else {
    setInterval(postHeight, 800);
  }

  // -------- Network --------
  async function sendMessage(text) {
    showTyping();
    try {
      const res = await fetch(`${API_BASE}/api/send/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: text }),
      });

      let data = {};
      try { data = await res.json(); } catch {}

      hideTyping();

      if (!res.ok || data.ok === false) {
        addMessage(
          data.message || "The mentor hit a snag. Mind trying again in a moment?",
          "bot"
        );
        if (data.code) console.warn("[PersonalMentor] error code:", data.code, data.detail || "");
        return;
      }

      addMessage(data.message || "(No content from assistant)", "bot");
    } catch (e) {
      hideTyping();
      addMessage("Network hiccup. Please try again.", "bot");
      console.error("[PersonalMentor] send error:", e);
    }
  }

  async function resetThread() {
    try {
      await fetch(`${API_BASE}/api/reset/`, { method: "POST", credentials: "include" });
      addMessage("Fresh start. What are we building today?", "bot");
    } catch {
      addMessage("Couldn’t reset right now, but we can keep going.", "bot");
    }
  }

  // -------- Health check on load --------
  async function checkHealthAndGreet() {
    // Default greeting (used if health is OK or health endpoint is missing)
    const greet = () =>
      addMessage("Hey Wayne — I’m your Personal Mentor. What are we building today?", "bot");

    try {
      const res = await fetch(`${API_BASE}/api/health/`, { credentials: "include" });
      if (!res.ok) {
        // Health not available—just greet and continue; don’t block UX
        console.warn("[PersonalMentor] health endpoint not OK:", res.status);
        greet();
        return;
      }
      const data = await res.json().catch(() => ({}));
      const keyOK = !!data.OPENAI_API_KEY_present;
      const asstOK = !!data.PERSONAL_MENTOR_ASSISTANT_ID_present;

      if (!keyOK || !asstOK) {
        let msg = "Heads up: backend isn’t fully configured:";
        if (!keyOK) msg += " OPENAI_API_KEY missing.";
        if (!asstOK) msg += " Assistant ID missing.";
        msg += " I can still chat basics, but replies may fail until that’s set.";
        addMessage(msg, "bot");
        return;
      }

      greet();
    } catch (e) {
      console.warn("[PersonalMentor] health check failed:", e);
      // Don’t block; still greet
      greet();
    }
  }

  // -------- Events --------
  $form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = ($input.value || "").trim();
    if (!text) return;
    addMessage(text, "user");
    $input.value = "";
    sendMessage(text);
  });

  if ($reset) $reset.addEventListener("click", () => resetThread());

  $input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  });

  // -------- Init --------
  (function init() {
    const alreadyHasBot = !!$messages.querySelector(".pm-msg.bot");
    if (!alreadyHasBot) checkHealthAndGreet();
    postHeight();
    removeLoadingOverlay();
  })();
})();
