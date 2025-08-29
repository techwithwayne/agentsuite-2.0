// checkout-success.js
(function () {
  try {
    // Notify opener (widget) and close this window
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: "barista:paid" }, "*");
      // Give the message a tick to travel before closing
      setTimeout(() => window.close(), 50);
    }
  } catch (e) {
    // If cross-window fails, just ignore
  }
})();
