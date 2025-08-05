(function () {
  const apiBase = "https://apps.techwithwayne.com//api";

  const toggleButton = document.createElement("button");
  toggleButton.id = "barista-assistant-toggle";
  toggleButton.textContent = "☕";
  document.body.appendChild(toggleButton);

  const chatContainer = document.createElement("div");
  chatContainer.id = "barista-assistant-container";
  chatContainer.style.display = "none";
  document.body.appendChild(chatContainer);

  const style = document.createElement("style");

  style.textContent = `
  #barista-assistant-toggle {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background-color: #c00000;
    color: white;
    border: none;
    border-radius: 50%;
    width: 60px;
    height: 60px;
    font-size: 24px;
    cursor: pointer;
    z-index: 9999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  }

  #barista-assistant-container {
    position: fixed;
    bottom: 100px;
    right: 20px;
    width: 350px;
    max-height: 90vh;
    background: #121212;
    color: white;
    border-radius: 16px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    overflow-y: auto;
    padding: 16px;
    z-index: 9999;
    font-family: 'Segoe UI', sans-serif;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
  }

  .msg {
    background: #1e1e1e;
    margin: 6px 0;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 14px;
    line-height: 1.4;
    box-sizing: border-box;
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
  .menu-item-btn:hover {
    background: #e65a00;
  }

  @media (max-width: 480px) {
    #barista-assistant-container {
      width: 90%;
      right: 5%;
      bottom: 80px;
    }
  }
`;


  document.head.appendChild(style);

  toggleButton.addEventListener("click", () => {
    chatContainer.style.display =
      chatContainer.style.display === "none" ? "flex" : "none";
    if (!chatContainer.dataset.initialized) {
      initializeChat();
      chatContainer.dataset.initialized = "true";
    }
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

    const customerFirstNameInput = createInput("First Name");
    const customerLastNameInput = createInput("Last Name");
    const customerEmailInput = createInput("Your Email");
    const pickupTimeInput = createInput("Pickup Time", "datetime-local");
    const submitCustomerBtn = createButton("Continue to Menu");

    chatContainer.appendChild(customerFirstNameInput);
    chatContainer.appendChild(customerLastNameInput);
    chatContainer.appendChild(customerEmailInput);
    chatContainer.appendChild(pickupTimeInput);
    chatContainer.appendChild(submitCustomerBtn);

    submitCustomerBtn.addEventListener("click", async () => {
      const customerFirstName = customerFirstNameInput
        .querySelector("input")
        .value.trim();
      const customerLastName = customerLastNameInput
        .querySelector("input")
        .value.trim();
      const customerEmail = customerEmailInput
        .querySelector("input")
        .value.trim();
      const pickupTimeRaw = pickupTimeInput.querySelector("input").value;

      if (
        !customerFirstName ||
        !customerLastName ||
        !customerEmail ||
        !pickupTimeRaw
      ) {
        addMessage("⚠️ Please complete all fields to continue.");
        return;
      }

      let pickupTimeFormatted = pickupTimeRaw;
      if (!pickupTimeRaw.endsWith("Z")) {
        pickupTimeFormatted = pickupTimeRaw + ":00Z";
      }
      const pickupTime = new Date(pickupTimeFormatted).toISOString();

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
            customer_last_name: customerLastName,
            customer_email: customerEmail,
            pickup_time: pickupTime,
            order_items: [{ item: item.name, quantity: 1, price: item.price }],
          };
          sendOrder(order);
        });
        chatContainer.appendChild(btn);
      });

      submitCustomerBtn.disabled = true;
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
  }

  async function fetchMenu() {
    try {
      const res = await fetch(`${apiBase}/menu/`);
      return await res.json();
    } catch (e) {
      console.error(e);
      return [];
    }
  }

  async function sendOrder(order) {
    try {
      const res = await fetch(`${apiBase}/order/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrftoken,
        },
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

      const res = await fetch(`${apiBase}/create-checkout-session/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrftoken,
        },
        credentials: "same-origin",
        body: JSON.stringify({ order_id: orderId }),
      });

      const data = await res.json();
      console.log("🟢 Stripe session response:", data);

      if (!data.id) {
        console.error("❌ Stripe session ID missing from response:", data);
        addMessage("⚠️ Stripe session creation failed.");
        return;
      }

      const keyRes = await fetch(`${apiBase}/stripe/publishable-key/`);
      const keyData = await keyRes.json();
      console.log("🟢 Stripe publishable key response:", keyData);

      if (!keyData.publishableKey) {
        console.error("❌ Stripe publishableKey is missing:", keyData);
        addMessage("⚠️ Stripe key fetch failed.");
        return;
      }

      // ✅ Load Stripe.js if not already present
      if (typeof Stripe === "undefined") {
        console.log("🧪 Loading Stripe.js...");
        await new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://js.stripe.com/v3/";
          script.onload = resolve;
          script.onerror = reject;
          document.head.appendChild(script);
        });
        console.log("🧠 Stripe.js loaded.");
      }

      const stripe = Stripe(keyData.publishableKey);
      console.log("🟢 Stripe instance created. Redirecting now...");

      const result = await stripe.redirectToCheckout({ sessionId: data.id });

      if (result.error) {
        console.error(
          "❌ Stripe redirectToCheckout error:",
          result.error.message
        );
        addMessage("⚠️ Redirect error: " + result.error.message);
      } else {
        console.log("✅ Stripe redirect initiated successfully.");
      }
    } catch (e) {
      console.error("🔥 Stripe redirect failed:", e);
      addMessage("⚠️ Failed to redirect to payment.");
    }
  }


})();
