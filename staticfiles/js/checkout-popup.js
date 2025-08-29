// checkout-popup.js
(function () {
  // Open a centered popup for Stripe Checkout. Fallback to full redirect if blocked.
  function openStripePopup(url) {
    try {
      const w = 520, h = 720;
      const topWin = window.top || window;
      const y = (topWin.outerHeight / 2) + topWin.screenY - (h / 2);
      const x = (topWin.outerWidth / 2) + topWin.screenX - (w / 2);

      const popup = topWin.open(
        url,
        "stripeCheckout",
        `width=${w},height=${h},left=${x},top=${y},menubar=no,toolbar=no,location=yes,status=no`
      );

      if (!popup) {
        // Popup blocked — fallback to normal redirect
        topWin.location.href = url;
      }
      return popup;
    } catch (e) {
      console.warn("Popup open failed, redirecting normally:", e);
      (window.top || window).location.href = url;
      return null;
    }
  }

  // Listen for success message from the success page and forward a CustomEvent
  function installPaidListener() {
    window.addEventListener("message", (e) => {
      // We only care that our success page posted *something* with this type.
      if (e && e.data && e.data.type === "barista:paid") {
        // If the widget defines a handler, call it
        if (typeof window.BaristaPaidHandler === "function") {
          try { window.BaristaPaidHandler(e.data); } catch (_) {}
        }
        // Also dispatch a DOM event for any other listeners
        try {
          const evt = new CustomEvent("barista:paid", { detail: e.data });
          window.dispatchEvent(evt);
        } catch (_) {}
      }
    });
  }

  // Expose globally
  window.openStripePopup = openStripePopup;
  installPaidListener();
})();
