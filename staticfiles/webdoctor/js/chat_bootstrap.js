// static/webdoctor/js/chat_bootstrap.js
(function () {
  // Make endpoints available before the widget initializes
  const root = document.getElementById("webdoctor-root") || document.body;

  // Provide correct URLs to JavaScript from data-* attributes
  window.webdoctorUrls = {
    handleMessage: root?.dataset.handleMessage || "/agent/handle_message/",
    submitForm: root?.dataset.submitForm || "/agent/submit_form/",
    resetUrl: root?.dataset.resetUrl || "/agent/reset_conversation/",
  };

  // Lightweight CSRF helper exposed globally (chat_widget uses its own too, this is a helper)
  window.getCsrfToken = function getCsrfToken() {
    if (window.csrfToken) return window.csrfToken;

    // meta tag
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta?.content) return meta.content;

    // hidden input (if present)
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input?.value) return input.value;

    // cookie fallback
    const cookieValue = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1];
    return cookieValue || "";
  };

  // Optional: mark environment
  window.isLocal =
    location.hostname === "127.0.0.1" || location.hostname === "localhost";

  console.log("🔧 webdoctorUrls:", window.webdoctorUrls);
})();
