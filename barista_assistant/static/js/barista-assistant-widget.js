// barista-assistant-widget.js - Enhanced Version with Height Management & Centered Layout
(function () {
  // API base (prod default). Can be overridden by window.BARISTA_API_BASE.
  const API_BASE = (
    window.BARISTA_API_BASE || "https://apps.techwithwayne.com/api"
  ).replace(/\/+$/, "");

  // --- Flatpickr loader fallback (in case vendor loader isn't included) ---
  async function ensureFlatpickrLocal() {
    if (window.flatpickr) return window.flatpickr;

    function loadCSS(href) {
      return new Promise((res, rej) => {
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = href;
        l.onload = res;
        l.onerror = rej;
        document.head.appendChild(l);
      });
    }
    function loadJS(src) {
      return new Promise((res, rej) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = res;
        s.onerror = rej;
        document.head.appendChild(s);
      });
    }

    const css = "https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css";
    const js  = "https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js";
    await Promise.all([loadCSS(css), loadJS(js)]);
    return window.flatpickr;
  }
  // Prefer global ensureFlatpickr (if you added vendor/flatpickr-loader.js), else fallback
  async function ensureFlatpickr() {
    if (typeof window.ensureFlatpickr === "function") return window.ensureFlatpickr();
    return ensureFlatpickrLocal();
  }
  // -------------------------------------------------------------------------

  // Create toggle button
  const toggleButton = document.createElement("button");
  toggleButton.id = "barista-assistant-toggle";
  toggleButton.textContent = "☕";
  document.body.appendChild(toggleButton);

  // Create chat container
  const chatContainer = document.createElement("div");
  chatContainer.id = "barista-assistant-container";
  chatContainer.style.display = "none";
  document.body.appendChild(chatContainer);

  // Enhanced styles for centered layout
  const style = document.createElement("style");
  style.textContent = `
  body {
    margin: 0;
    padding: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #121212;
    font-family: 'Segoe UI', sans-serif;
    overflow: hidden; /* Prevent outer scrollbars on the page body */
  }
  #barista-assistant-toggle {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background-color: #c00000;
    color: white;
    border: none;
    border-radius: 50%;
    width: 50px;
    height: 50px;
    font-size: 24px;
    cursor: pointer;
    z-index: 10000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    transition: all 0.3s ease;
  }
  #barista-assistant-toggle:hover {
    transform: scale(1.1);
    background-color: #e00000;
  }
  #barista-assistant-container {
    width: 90%;
    max-width: 450px;
    height: auto;
    max-height: 580px;
    background: #121212;
    color: white;
    border-radius: 16px;
    box-shadow: 0 10px 24px rgba(0,0,0,0.4);
    overflow-y: auto;
    padding: 16px;
    z-index: 9999;
    font-family: 'Segoe UI', sans-serif;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    margin: 20px auto;
    position: relative;
  }
  .msg {
    background: #1e1e1e;
    margin: 6px 0;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 14px;
    line-height: 1.4;
    box-sizing: border-box;
    animation: fadeIn 0.3s ease-out;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .input-row {
    width: 100%;
    margin: 8px 0;
    box-sizing: border-box;
  }
  .input-row input {
    width: 100%;
    padding: 12px;
    border-radius: 8px;
    border: none;
    font-size: 14px;
    background: #2a2a2a;
    color: white;
    box-sizing: border-box;
  }
  .input-row input:focus {
    outline: none;
    box-shadow: 0 0 0 2px #ff6c00;
  }
  .input-row button,
  .menu-item-btn {
    width: 100%;
    padding: 12px;
    margin-top: 6px;
    background: #ff6c00;
    color: white;
    font-weight: bold;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.3s ease;
    box-sizing: border-box;
  }
  .input-row button:hover,
  .menu-item-btn:hover { background: #e65a00; }
  .input-row button:disabled { opacity: 0.6; cursor: not-allowed; }

  /* Scrollbar styling */
  #barista-assistant-container::-webkit-scrollbar { width: 6px; }
  #barista-assistant-container::-webkit-scrollbar-track { background: #2a2a2a; border-radius: 3px; }
  #barista-assistant-container::-webkit-scrollbar-thumb { background: #ff6c00; border-radius: 3px; }
  #barista-assistant-container::-webkit-scrollbar-thumb:hover { background: #e65a00; }

  @media (max-width: 480px) {
    #barista-assistant-container { width: 95%; max-width: 100%; margin: 10px auto; }
  }
`;
  document.head.appendChild(style);

  // IframeHeightManager class
  class IframeHeightManager {
    constructor() {
      this.lastHeight = 0;
      this.resizeObserver = null;
      this.debounceTimeout = null;
      this.init();
    }
    init() {
      console.log("📏 Initializing iframe height manager for Barista widget");
      this.startHeightMonitoring();
      setTimeout(() => { this.sendHeightToParent(); }, 1000);
    }
    startHeightMonitoring() {
      // Use ResizeObserver if available
      if (window.ResizeObserver) {
        this.resizeObserver = new ResizeObserver(() => { this.debounceHeightUpdate(); });
        const container = document.getElementById("barista-assistant-container");
        if (container) this.resizeObserver.observe(container);
        this.resizeObserver.observe(document.body);
      }
      // Monitor DOM changes
      const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
          if (m.type === "childList" || m.type === "attributes" || m.type === "subtree") {
            this.debounceHeightUpdate(); break;
          }
        }
      });
      observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["style", "class"] });
      // Periodic height check
      setInterval(() => { this.sendHeightToParent(); }, 3000);
    }
    debounceHeightUpdate() {
      clearTimeout(this.debounceTimeout);
      this.debounceTimeout = setTimeout(() => { this.sendHeightToParent(); }, 150);
    }
    getOptimalHeight() {
      const bodyScrollHeight = document.body.scrollHeight;
      const documentHeight = document.documentElement.scrollHeight;
      const windowHeight = window.innerHeight;
      const container = document.getElementById("barista-assistant-container");

      let containerHeight = 0;
      if (container && container.style.display !== "none") {
        const rect = container.getBoundingClientRect();
        containerHeight = rect.height;
      }
      const maxHeight = Math.max(bodyScrollHeight, documentHeight, windowHeight, containerHeight);
      const finalHeight = Math.max(400, maxHeight + 50);
      return Math.min(finalHeight, 800);
    }
    sendHeightToParent() {
      const newHeight = this.getOptimalHeight();
      if (Math.abs(newHeight - this.lastHeight) > 15) {
        this.lastHeight = newHeight;
        try {
          const heightMessage = { type: "resize", height: newHeight, timestamp: Date.now(), source: "barista-widget" };
          window.parent.postMessage(heightMessage, "*");
          window.parent.postMessage({ type: "iframeResize", height: newHeight, timestamp: Date.now(), source: "barista-widget" }, "*");
          console.log(`📤 Sent height to parent: ${newHeight}px`);
        } catch (error) { console.warn("Failed to send height to parent:", error); }
      }
    }
    triggerHeightUpdate() { setTimeout(() => { this.sendHeightToParent(); }, 100); }
    forceHeightUpdate() { this.lastHeight = 0; this.sendHeightToParent(); }
  }

  // Initialize height manager
  let heightManager = null;

  // Toggle button event with height management
  toggleButton.addEventListener("click", () => {
    chatContainer.style.display = chatContainer.style.display === "none" ? "flex" : "none";
    if (chatContainer.style.display === "flex") {
      if (!chatContainer.dataset.initialized) {
        initializeChat();
        chatContainer.dataset.initialized = "true";
      }
      if (heightManager) heightManager.forceHeightUpdate();
    }
  });

  // Auto-open on page load
  window.addEventListener("load", () => {
    setTimeout(() => {
      chatContainer.style.display = "flex";
      if (!chatContainer.dataset.initialized) {
        initializeChat();
        chatContainer.dataset.initialized = "true";
      }
      if (!heightManager) {
        heightManager = new IframeHeightManager();
        window.baristaHeightManager = heightManager;
      } else {
        heightManager.forceHeightUpdate();
      }
    }, 500);
  });

  // CSRF helper for Django
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  const csrftoken = getCookie("csrftoken");

  async function initializeChat() {
    addMessage("👋 Hi, I'm your Barista Assistant. Let's place your order!");

    // Inputs
    const customerFirstNameInput = createInput("First Name");
    const customerLastNameInput  = createInput("Last Name");
    const customerEmailInput     = createInput("Your Email");

    // Flatpickr DateTime field (no native datepicker)
    const pickupTimeRow = createInput("Pickup Date & Time", "text");
    const pickupEl = pickupTimeRow.querySelector("input");
    pickupEl.readOnly = true; // prevent mobile keyboard pop-up

    // Append inputs to DOM
    chatContainer.appendChild(customerFirstNameInput);
    chatContainer.appendChild(customerLastNameInput);
    chatContainer.appendChild(customerEmailInput);
    chatContainer.appendChild(pickupTimeRow);

    // Load & init Flatpickr with limited time window
    await ensureFlatpickr();
    const OPEN_TIME = "07:00";   // tweak hours here
    const CLOSE_TIME = "18:00";  // tweak hours here
    const MINUTE_STEP = 15;

    const pickupPicker = flatpickr(pickupEl, {
      enableTime: true,
      dateFormat: "Y-m-d H:i",
      minDate: "today",
      minuteIncrement: MINUTE_STEP,
      time_24hr: false,  // set true if you prefer 24h clock
      minTime: OPEN_TIME,  // earliest time
      maxTime: CLOSE_TIME, // latest time
      onOpen:  () => { if (heightManager) heightManager.triggerHeightUpdate(); },
      onChange:() => { if (heightManager) heightManager.triggerHeightUpdate(); },
    });

    // Continue button
    const submitCustomerBtn = createButton("Continue to Menu");
    chatContainer.appendChild(submitCustomerBtn);

    // Trigger height update after adding elements
    if (heightManager) heightManager.triggerHeightUpdate();

    submitCustomerBtn.addEventListener("click", async () => {
      const customerFirstName = customerFirstNameInput.querySelector("input").value.trim();
      const customerLastName  = customerLastNameInput.querySelector("input").value.trim();
      const customerEmail     = customerEmailInput.querySelector("input").value.trim();

      const selected = pickupPicker && pickupPicker.selectedDates
        ? pickupPicker.selectedDates[0]
        : null;

      if (!customerFirstName || !customerLastName || !customerEmail || !selected) {
        addMessage("⚠️ Please complete all fields to continue.");
        return;
      }

      const pickupTime = selected.toISOString(); // same ISO format your backend expects

      const menu = await fetchMenu();
      if (menu.length === 0) {
        addMessage("⚠️ Menu is currently unavailable.");
        return;
      }

      addMessage("✅ Select an item to add to your order:");
      menu.forEach((item) => {
        const btn = createButton(`${item.name} - $${item.price}`);
        btn.classList.add("menu-item-btn");
        btn.addEventListener("click", () => {
          const order = {
            customer_first_name: customerFirstName,
            customer_last_name:  customerLastName,
            customer_email:      customerEmail,
            pickup_time:         pickupTime,
            order_items: [{ item: item.name, quantity: 1, price: item.price }],
          };
          sendOrder(order);
        });
        chatContainer.appendChild(btn);
      });

      submitCustomerBtn.disabled = true;

      // Trigger height update after adding menu items
      if (heightManager) heightManager.triggerHeightUpdate();
    });
  }

  function createInput(placeholder, type = "text") {
    const div = document.createElement("div");
    div.className = "input-row";
    const input = document.createElement("input");
    input.placeholder = placeholder;
    input.type = type;
    div.appendChild(input);
    return div;
  }
  function createButton(text) {
    const btn = document.createElement("button");
    btn.textContent = text;
    return btn;
  }
  function addMessage(text) {
    const msg = document.createElement("div");
    msg.className = "msg";
    msg.textContent = text;
    chatContainer.appendChild(msg);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    if (heightManager) heightManager.triggerHeightUpdate();
  }

  async function fetchMenu() {
    async function tryUrl(url) {
      let res;
      try { res = await fetch(url, { credentials: "omit" }); } catch (_e) { return null; }
      if (!res.ok) return null;
      let data;
      try { data = await res.json(); } catch (_e) { return null; }
      if (Array.isArray(data)) return data;                 // plain list
      if (data && Array.isArray(data.results)) return data.results; // DRF paginated
      return null;
    }
    let items = await tryUrl(`${API_BASE}/menu/`);
    if (items && items.length) return items;
    items = await tryUrl(`${API_BASE}/`); // fallback
    return items || [];
  }

  async function sendOrder(order) {
    try {
      const res = await fetch(`${API_BASE}/order/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken },
        credentials: "same-origin",
        body: JSON.stringify(order),
      });
      if (res.ok) {
        const data = await res.json();
        addMessage("✅ Order created! Redirecting to payment...");
        await redirectToStripeCheckout(data.id);
      } else {
        addMessage("⚠️ Failed to place order.");
      }
    } catch (e) {
      console.error(e);
      addMessage("⚠️ Error placing order.");
    }
  }

  async function redirectToStripeCheckout(orderId) {
    try {
      console.log("🟡 Starting Stripe checkout for order:", orderId);

      // Create Checkout Session
      const res = await fetch(`${API_BASE}/create-checkout-session/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken },
        credentials: "same-origin",
        body: JSON.stringify({ order_id: orderId }),
      });

      const { id, url } = await res.json();
      console.log("🟢 Stripe session response:", { id, url });

      if (!url) {
        console.error("❌ Missing session.url in response.");
        addMessage("⚠️ Stripe session creation failed.");
        return;
      }

      // 🔁 Open centered popup; fallback to redirect if blocked
      if (typeof openStripePopup === "function") {
        openStripePopup(url);
      } else {
        (window.top || window).location.href = url;
      }

      // Friendly note while user is in the popup
      if (typeof addMessage === "function") {
        addMessage("Almost there—complete your payment in the popup window.");
      }

      // ✅ When success page posts back, show confirmation
      window.BaristaPaidHandler = function () {
        if (typeof addMessage === "function") {
          addMessage("✅ Payment received. Thanks!");
        }
        // TODO: reset cart or UI if you track one
      };
    } catch (e) {
      console.error("🔥 Stripe popup flow failed:", e);
      addMessage("⚠️ Failed to start payment.");
    }
  }

  // Handle window resize
  window.addEventListener("resize", () => { if (heightManager) heightManager.triggerHeightUpdate(); });
  // Handle visibility changes
  document.addEventListener("visibilitychange", () => { if (!document.hidden && heightManager) heightManager.forceHeightUpdate(); });
  // Handle page show event (back/forward navigation)
  window.addEventListener("pageshow", function (event) {
    if (event.persisted && heightManager) { setTimeout(() => { heightManager.forceHeightUpdate(); }, 300); }
  });
})();
