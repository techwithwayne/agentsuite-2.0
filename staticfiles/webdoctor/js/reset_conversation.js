// static/webdoctor/js/reset_conversation.js
(function () {
  async function resetConversationOnLoad() {
    const urls = window.webdoctorUrls || {};
    const resetUrl = urls.resetUrl || "/agent/reset_conversation/";
    const handleUrl = urls.handleMessage || "/agent/handle_message/";
    const csrf = (window.getCsrfToken && window.getCsrfToken()) || "";

    console.log("🔄 Starting conversation reset...");

    // Method 1: server reset endpoint
    try {
      const res = await fetch(resetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ force_reset: true, reason: "page_load" }),
      });
      if (res.ok) {
        const data = await res.json();
        console.log("✅ Server-side conversation reset successful:", data);
      } else {
        console.warn("⚠️ Server-side reset failed, status:", res.status);
      }
    } catch (e) {
      console.warn("⚠️ Server-side reset error:", e);
    }

    // Method 2: backup forced first-message reset
    try {
      const res2 = await fetch(handleUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({
          message: "__FORCE_RESET__",
          force_reset: true,
          lang: "en",
        }),
      });
      if (res2.ok) console.log("✅ Force reset message sent successfully");
    } catch (e) {
      console.warn("⚠️ Force reset message failed:", e);
    }

    console.log("🔄 Conversation reset complete");
  }

  // multiple triggers—same behavior as your inline version
  document.addEventListener("DOMContentLoaded", resetConversationOnLoad);
  window.addEventListener("load", resetConversationOnLoad);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) setTimeout(resetConversationOnLoad, 100);
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) setTimeout(resetConversationOnLoad, 100);
  });
})();
