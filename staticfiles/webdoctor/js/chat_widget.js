// JavaScript for WebDoctor Chat Widget - COMPLETE VERSION WITH HEIGHT MANAGEMENT
// File: static/webdoctor/js/chat_widget.js

class WebDoctorChat {
  constructor() {
    console.log("WebDoctorChat constructor called");

    this.isTyping = false;
    this.messageCount = 0;
    this.currentStage = "initial";
    this.formOffered = false;
    this.formAccepted = false;
    this.sendInProgress = false; // prevent double-sending
    this.audioEnabled = false;   // track audio state
    this.userHasInteracted = false; // track user interaction

    this.greetings = [
      "Hey there! I'm Shirley, your website's doctor. What seems to be the issue today?",
      "Hi! Shirley here—ready to help diagnose your website troubles. What's going on?",
      "Welcome! I'm Shirley. Tell me what's bugging your website and I'll help fix it.",
    ];

    // Initialize audio for typing sound
    this.initializeAudio();

    console.log("About to call init()");
    this.init();
  }

  // Initialize audio with autoplay attempt; silent fallback on first interaction
  initializeAudio() {
    console.log("🔊 Initializing typing sound...");

    this.audioEnabled = false;
    this.userHasInteracted = false;

    try {
      this.typingSound = new Audio();
      this.typingSound.preload = "auto";
      this.typingSound.src = "/static/webdoctor/sounds/bong.mp3";
      this.typingSound.volume = 0.3;

      this.typingSound.addEventListener("canplaythrough", () => {
        console.log("✅ Typing sound loaded successfully");
      });

      this.typingSound.addEventListener("error", (e) => {
        console.warn("⚠️ Could not load typing sound:", e);
        console.warn("Sound file should be at: /static/webdoctor/sounds/bong.mp3");
      });

      const tryEnableAutoplay = () => {
        if (this.audioEnabled || !this.typingSound) return;
        this.typingSound
          .play()
          .then(() => {
            this.typingSound.pause();
            this.typingSound.currentTime = 0;
            this.audioEnabled = true;
            this.userHasInteracted = true;
            console.log("🔊 Audio enabled automatically (autoplay permitted).");
          })
          .catch((err) => {
            console.log("🔇 Autoplay blocked; will enable on first interaction.", err?.message || "");
            this.setupUserInteractionDetection();
          });
      };

      this.typingSound.load();

      if (document.readyState === "complete" || document.readyState === "interactive") {
        tryEnableAutoplay();
      } else {
        document.addEventListener("DOMContentLoaded", tryEnableAutoplay, { once: true });
      }

      const visHandler = () => {
        if (!document.hidden && !this.audioEnabled) {
          tryEnableAutoplay();
          document.removeEventListener("visibilitychange", visHandler);
        }
      };
      document.addEventListener("visibilitychange", visHandler);
    } catch (error) {
      console.warn("⚠️ Audio initialization failed:", error);
      this.typingSound = null;
    }
  }

  // Detect user interaction and enable audio silently
  setupUserInteractionDetection() {
    const enableAudio = () => {
      if (this.audioEnabled || !this.typingSound) return;

      this.typingSound
        .play()
        .then(() => {
          this.typingSound.pause();
          this.typingSound.currentTime = 0;
          this.audioEnabled = true;
          this.userHasInteracted = true;
          console.log("🔊 Audio enabled successfully after first interaction");
          detach();
        })
        .catch(() => {
          // keep listeners; some browsers need a different interaction event
        });
    };

    const interactionEvents = ["click", "keydown", "touchstart", "mousedown", "pointerdown", "scroll", "focus"];
    const detach = () => interactionEvents.forEach((eventType) => {
      document.removeEventListener(eventType, enableAudio, true);
    });

    interactionEvents.forEach((eventType) => {
      document.addEventListener(eventType, enableAudio, true);
    });

    setTimeout(() => {
      const userInput = document.getElementById("user-input");
      if (userInput) {
        try { userInput.focus({ preventScroll: true }); } catch (e) {}
      }
    }, 300);
  }

  // Play typing sound with autoplay handling
  playTypingSound() {
    if (!this.typingSound) {
      console.log("🔇 No typing sound available");
      return;
    }
    if (!this.audioEnabled) {
      console.log("🔇 Audio not enabled yet (browser policy)");
      return;
    }

    try {
      this.typingSound.currentTime = 0;
      const playPromise = this.typingSound.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => console.log("🔊 Typing sound played successfully"))
          .catch((error) => {
            console.log("🔇 Could not play typing sound:", error.message);
            this.audioEnabled = false;
            this.setupUserInteractionDetection();
          });
      }
    } catch (error) {
      console.warn("⚠️ Error playing typing sound:", error);
      this.audioEnabled = false;
    }
  }

  init() {
    console.log("🔧 Init method called");
    try {
      this.bindEvents();
      console.log("✅ Events bound successfully");

      this.showInitialGreeting();
      console.log("✅ Initial greeting scheduled");

      this.focusInput();
      console.log("✅ Input focus scheduled");
    } catch (error) {
      console.error("❌ Error in init:", error);
    }
  }

  bindEvents() {
    console.log("🔗 Binding events...");

    const sendBtn = document.getElementById("send-button");
    const userInput = document.getElementById("user-input");
    const submitBtn = document.getElementById("submit-button");

    console.log("📋 Elements found:", {
      sendBtn: !!sendBtn,
      userInput: !!userInput,
      submitBtn: !!submitBtn,
    });

    if (sendBtn) {
      console.log("🔘 Binding send button click event");
      sendBtn.addEventListener("click", (e) => {
        console.log("🖱️ Send button clicked!");
        e.preventDefault();
        this.sendMessage();
      });
      sendBtn.style.backgroundColor = "#ff6c00";
      console.log("🎨 Send button styled successfully");
    } else {
      console.error("❌ Send button not found!");
    }

    if (userInput) {
      console.log("⌨️ Binding input events");
      userInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          console.log("⏎ Enter key pressed");
          e.preventDefault();
          this.sendMessage();
        }
      });

      userInput.addEventListener("input", this.handleInputChange.bind(this));
    } else {
      console.error("❌ User input not found!");
    }

    if (submitBtn) {
      console.log("📝 Binding submit button");
      submitBtn.addEventListener("click", (e) => {
        console.log("📤 Submit button clicked");
        e.preventDefault();
        this.submitForm();
      });
    } else {
      console.error("❌ Submit button not found!");
    }
  }

  handleInputChange(e) {
    const sendBtn = document.getElementById("send-button");
    if (sendBtn) {
      sendBtn.style.opacity = e.target.value.trim() ? "1" : "0.6";
    }
  }

  showInitialGreeting() {
    console.log("Scheduling initial greeting...");

    setTimeout(() => {
      console.log("Timeout fired - showing greeting");
      const greeting = this.greetings[Math.floor(Math.random() * this.greetings.length)];
      console.log("Selected greeting:", greeting);

      try {
        this.addBotMessage(greeting, true);
        console.log("Greeting added successfully");
      } catch (error) {
        console.error("Error adding greeting:", error);
      }
    }, 500);
  }

  focusInput() {
    console.log("🎯 Focusing input...");
    const userInput = document.getElementById("user-input");
    if (userInput) {
      setTimeout(() => {
        userInput.focus();
        console.log("✅ Input focused");
      }, 100);
    } else {
      console.error("❌ Cannot focus - input not found");
    }
  }

  addUserMessage(message) {
    console.log("👤 Adding user message:", message);

    const chatBody = document.getElementById("chat-body");
    if (!chatBody) {
      console.error("❌ Chat body not found!");
      return;
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = "chat-bubble user";
    messageDiv.innerHTML = `<strong>You:</strong> ${this.escapeHtml(message)}`;
    chatBody.appendChild(messageDiv);
    this.scrollToBottom();
    this.messageCount++;

    // Trigger height update after adding message
    if (window.iframeHeightManager) {
      window.iframeHeightManager.triggerHeightUpdate();
    }

    console.log("✅ User message added, total messages:", this.messageCount);
  }

  // Add bot message with optional typing animation and callback
  addBotMessage(message, animate = false, callback = null) {
    console.log("🤖 Adding bot message:", message, "animate:", animate);

    const chatBody = document.getElementById("chat-body");
    if (!chatBody) {
      console.error("❌ Chat body not found for bot message!");
      return;
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = "chat-bubble bot";

    if (animate) {
      console.log("🎬 Starting animation...");
      this.playTypingSound();
      this.animateTyping(messageDiv, message, callback);
    } else {
      messageDiv.innerHTML = `<strong>Shirley:</strong> ${this.escapeHtml(message)}`;
      chatBody.appendChild(messageDiv);
      this.scrollToBottom();
      console.log("✅ Bot message added instantly");

      if (callback) setTimeout(callback, 100);

      if (window.iframeHeightManager) {
        window.iframeHeightManager.triggerHeightUpdate();
      }
    }
  }

  // Typing animation with height updates and optional callback
  animateTyping(messageDiv, message, callback = null) {
    console.log("⌨️ Animating typing for message:", message);

    const chatBody = document.getElementById("chat-body");
    messageDiv.innerHTML = '<strong>Shirley:</strong> <span class="typing-text"></span>';
    chatBody.appendChild(messageDiv);

    const typingSpan = messageDiv.querySelector(".typing-text");
    if (!typingSpan) {
      console.error("❌ Typing span not found!");
      return;
    }

    let index = 0;
    const delay = Math.max(30, Math.min(50, 1000 / message.length));
    console.log("⏱️ Typing delay:", delay);

    const typeInterval = setInterval(() => {
      if (index < message.length) {
        typingSpan.textContent += message.charAt(index);
        index++;
        this.scrollToBottom();

        // Periodic height updates during typing
        if (window.iframeHeightManager && index % 10 === 0) {
          window.iframeHeightManager.triggerHeightUpdate();
        }
      } else {
        console.log("✅ Typing animation complete");
        clearInterval(typeInterval);
        this.isTyping = false;

        if (window.iframeHeightManager) {
          window.iframeHeightManager.triggerHeightUpdate();
        }

        this.checkForFormTrigger(message);

        if (callback) setTimeout(callback, 50);
      }
    }, delay);
  }

  showTypingIndicator() {
    console.log("💭 Showing typing indicator...");

    const chatBody = document.getElementById("chat-body");
    if (!chatBody) return;

    const typingDiv = document.createElement("div");
    typingDiv.className = "chat-bubble bot typing-bubble";
    typingDiv.id = "typing-indicator";
    typingDiv.innerHTML = '<strong>Shirley:</strong> <span class="dots"><span>•</span><span>•</span><span>•</span></span>';
    chatBody.appendChild(typingDiv);
    this.scrollToBottom();

    if (window.iframeHeightManager) {
      window.iframeHeightManager.triggerHeightUpdate();
    }

    console.log("✅ Typing indicator shown");
    return typingDiv;
  }

  removeTypingIndicator() {
    const typingIndicator = document.getElementById("typing-indicator");
    if (typingIndicator) {
      typingIndicator.remove();
      console.log("✅ Typing indicator removed");

      if (window.iframeHeightManager) {
        window.iframeHeightManager.triggerHeightUpdate();
      }
    }
  }

  checkForFormTrigger(message) {
    const reportOffers = [
      "diagnostic report",
      "free report",
      "send you",
      "email you",
      "would you like",
      "want me to send",
      "report with",
    ];

    const messageText = message.toLowerCase();
    const offeredReport = reportOffers.some((phrase) => messageText.includes(phrase));

    if (offeredReport) {
      this.formOffered = true;
      console.log("📋 Form trigger detected");
    }
  }

  showForm() {
    console.log("📝 Showing form...");
    const formSection = document.getElementById("form-section");
    if (formSection) {
      formSection.style.display = "flex";
      setTimeout(() => {
        const nameInput = document.getElementById("form-name");
        if (nameInput) nameInput.focus();

        if (window.iframeHeightManager) {
          setTimeout(() => {
            window.iframeHeightManager.triggerHeightUpdate();
          }, 300);
        }
      }, 300);
      console.log("✅ Form shown");
    }
  }

  hideForm() {
    console.log("📝 Hiding form...");
    const formSection = document.getElementById("form-section");
    if (formSection) {
      formSection.style.display = "none";

      if (window.iframeHeightManager) {
        setTimeout(() => {
          window.iframeHeightManager.triggerHeightUpdate();
        }, 100);
      }

      console.log("✅ Form hidden");
    }
  }

  // Send message with height management hooks
  async sendMessage() {
    console.log("Send message called, isTyping:", this.isTyping, "sendInProgress:", this.sendInProgress);

    if (this.isTyping || this.sendInProgress) {
      console.log("Already processing, skipping...");
      return;
    }

    const userInput = document.getElementById("user-input");
    const message = userInput?.value.trim();

    console.log("Message to send:", message);

    if (!message) {
      console.log("Empty message, skipping...");
      return;
    }

    this.isTyping = true;
    this.sendInProgress = true;
    console.log("Set flags: isTyping=true, sendInProgress=true");

    this.addUserMessage(message);
    userInput.value = "";

    const sendBtn = document.getElementById("send-button");
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.style.opacity = "0.6";
      console.log("Send button disabled");
    }

    let isAcceptingReport = false;
    if (this.formOffered && !this.formAccepted) {
      const acceptanceWords = ["yes","sure","okay","ok","please","send","email","absolutely","definitely"];
      const userResponse = message.toLowerCase();
      if (acceptanceWords.some((word) => userResponse.includes(word))) {
        isAcceptingReport = true;
        this.formAccepted = true;
        console.log("✅ Form acceptance detected - will show form after AI response");
      }
    }

    const typingIndicator = this.showTypingIndicator();

    try {
      const targetUrl = window.webdoctorUrls?.handleMessage || "/agent/handle_message/";
      console.log("🌐 Making fetch request to:", targetUrl);

      const csrfToken = this.getCsrfToken();
      console.log("🔐 CSRF token:", csrfToken ? "Found" : "Missing");

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch(targetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ message, lang: "en" }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      console.log("📡 Response status:", response.status);
      console.log("📡 Response ok:", response.ok);

      if (!response.ok) throw new Error(`Server error: ${response.status}`);

      let data;
      try { data = await response.json(); }
      catch (jsonError) {
        console.error("❌ JSON parsing error:", jsonError);
        throw new Error("Invalid response format from server");
      }

      console.log("📦 Response data:", data);

      this.removeTypingIndicator();

      if (data.response && data.response.trim()) {
        this.currentStage = data.stage || this.currentStage;

        this.addBotMessage(data.response, true, () => {
          if (data.show_form || isAcceptingReport) {
            console.log("✅ Showing form after AI response");
            setTimeout(() => this.showForm(), 500);
          }
        });

        console.log("✅ Bot response added");
      } else {
        this.addBotMessage("Sorry, I didn't get that. Could you try rephrasing?");
        console.log("⚠️ No response in data, showing fallback");
        this.isTyping = false;
      }
    } catch (error) {
      console.error("❌ Error in sendMessage:", error);
      this.removeTypingIndicator();

      let errorMessage;
      if (error.name === "AbortError") {
        errorMessage = "Request timed out. Please try again.";
      } else if (error.message.includes("NetworkError") || error.message.includes("Failed to fetch")) {
        errorMessage = "Connection problem. Please check your internet and try again.";
      } else {
        errorMessage = "Oops! Something went wrong. Please try again.";
      }

      this.addBotMessage(errorMessage);
      this.isTyping = false;
    } finally {
      this.sendInProgress = false;
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.style.opacity = "1";
        console.log("🔓 Send button re-enabled");
      }
      console.log("🔓 Set sendInProgress to false");
    }

    this.focusInput();
  }

  async submitForm() {
    console.log("📋 Submit form called");

    const nameInput = document.getElementById("form-name");
    const emailInput = document.getElementById("form-email");
    const submitBtn = document.getElementById("submit-button");

    const name = nameInput?.value.trim();
    const email = emailInput?.value.trim();

    console.log("📋 Form data:", { name, email });

    if (!name || !email) {
      this.addBotMessage("Please fill in both your name and email address.");
      return;
    }

    if (!this.isValidEmail(email)) {
      this.addBotMessage("Please enter a valid email address.");
      return;
    }

    const chatBody = document.getElementById("chat-body");
    const userMessages = Array.from(chatBody.querySelectorAll(".chat-bubble.user"))
      .map((msg) => msg.textContent.replace("You: ", ""))
      .join(" | ");

    const originalButtonText = submitBtn.textContent;
    submitBtn.textContent = "Sending...";
    submitBtn.disabled = true;

    try {
      const targetUrl = "/agent/submit_form/";
      console.log("🌐 Submitting form to:", targetUrl);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch(targetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this.getCsrfToken(),
        },
        body: JSON.stringify({
          name,
          email,
          issue: userMessages || "General website consultation",
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      let data;
      try { data = await response.json(); }
      catch (jsonError) {
        console.error("❌ Form response JSON parsing error:", jsonError);
        throw new Error("Invalid response format");
      }

      console.log("📋 Form response:", data);

      if (response.ok && data.message) {
        const firstName = (name || "").trim().split(" ")[0] || name || "";
        const finalMsg = firstName ? `Thanks ${firstName}! 🎉 ${data.message}` : data.message;

        this.addBotMessage(finalMsg);
        this.hideForm();
      } else {
        throw new Error(data.error || "Failed to send report");
      }
    } catch (error) {
      console.error("❌ Form submission error:", error);

      let errorMessage;
      if (error.name === "AbortError") {
        errorMessage = "Form submission timed out. Please try again.";
      } else if (error.message.includes("NetworkError") || error.message.includes("Failed to fetch")) {
        errorMessage = "Connection problem. Please check your internet and try again.";
      } else {
        errorMessage = "Sorry, there was an issue sending your report. Please try again.";
      }

      this.addBotMessage(errorMessage);
    } finally {
      submitBtn.textContent = originalButtonText;
      submitBtn.disabled = false;
    }
  }

  // Hard reset the conversation safely
  async forceReset() {
    try {
      console.log("🔄 Sending force reset message...");

      const csrf = this.getCsrfToken
        ? this.getCsrfToken()
        : document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";

      const resp = await fetch("/agent/handle_message/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ message: "__FORCE_RESET__", force_reset: true, lang: "en" }),
      });

      if (!resp.ok) {
        const txt = await resp.text();
        console.error("Reset failed:", resp.status, txt);
        this.addBotMessage("Reset failed. Please refresh and try again.");
        return;
      }

      const data = await resp.json();
      console.log("✅ Reset result:", data);

      const chatBody = document.getElementById("chat-body");
      if (chatBody) chatBody.innerHTML = "";
      this.currentStage = "initial";
      this.formOffered = false;
      this.formAccepted = false;
      this.messageCount = 0;

      this.showInitialGreeting();
    } catch (e) {
      console.error("Reset error:", e);
      this.addBotMessage("Reset error. Please refresh the page.");
    }
  }

  isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  getCsrfToken() {
    console.log("Getting CSRF token...");

    if (window.csrfToken) {
      console.log("CSRF token from window variable: Found");
      return window.csrfToken;
    }

    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (csrfInput && csrfInput.value) {
      console.log("CSRF token from hidden input: Found");
      return csrfInput.value;
    }

    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) {
      const token = metaToken.getAttribute("content");
      console.log("CSRF token from meta tag:", token ? "Found" : "Empty");
      return token;
    }

    const cookieValue = document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1];
    if (cookieValue) {
      console.log("CSRF token from cookie: Found");
      return cookieValue;
    }

    console.warn("CSRF token not found - this may cause request failures");
    return "";
  }

  escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  scrollToBottom() {
    const chatBody = document.getElementById("chat-body");
    if (chatBody) {
      setTimeout(() => {
        chatBody.scrollTop = chatBody.scrollHeight;
      }, 50);
    }
  }
}

// Iframe Height Manager Class (FIXED: no window.innerHeight; clamped range)
class IframeHeightManager {
  constructor() {
    this.lastHeight = 0;
    this.resizeObserver = null;
    this.debounceTimeout = null;

    // sane bounds for column layout
    this.MIN = 420;
    this.MAX = 620;
    this.BUFFER = 16;
    this.CHANGE_THRESHOLD = 8;

    this.init();
  }

  init() {
    console.log("📏 Initializing iframe height manager");

    this.startHeightMonitoring();

    // Initial sends
    setTimeout(() => this.sendHeightToParent(), 300);
    window.addEventListener("load", () => this.sendHeightToParent());
  }

  startHeightMonitoring() {
    if (window.ResizeObserver) {
      this.resizeObserver = new ResizeObserver(() => this.debounceHeightUpdate());
      const chatWidget = document.querySelector(".chat-widget");
      if (chatWidget) this.resizeObserver.observe(chatWidget);
      this.resizeObserver.observe(document.body);
    }

    const observer = new MutationObserver(() => this.debounceHeightUpdate());
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["style", "class"],
    });

    // light periodic sanity check
    setInterval(() => this.sendHeightToParent(), 4000);
  }

  debounceHeightUpdate() {
    if (this.debounceTimeout) clearTimeout(this.debounceTimeout);
    this.debounceTimeout = setTimeout(() => this.sendHeightToParent(), 120);
  }

  getOptimalHeight() {
    // Measure CONTENT, not viewport — removes feedback loop with parent.
    const bodyScrollHeight = document.body.scrollHeight || 0;
    const documentHeight = document.documentElement.scrollHeight || 0;

    let widgetHeight = 0;
    const chatWidget = document.querySelector(".chat-widget");
    if (chatWidget) {
      const rect = chatWidget.getBoundingClientRect();
      widgetHeight = Math.ceil(rect.height);
    }

    const content = Math.max(bodyScrollHeight, documentHeight, widgetHeight);
    const unclamped = Math.ceil(content + this.BUFFER);
    const clamped = Math.max(this.MIN, Math.min(unclamped, this.MAX));
    return clamped;
  }

  sendHeightToParent() {
    const newHeight = this.getOptimalHeight();

    if (Math.abs(newHeight - this.lastHeight) > this.CHANGE_THRESHOLD) {
      this.lastHeight = newHeight;

      try {
        const msg = { type: "resize", height: newHeight, timestamp: Date.now(), source: "webdoctor-widget" };
        window.parent.postMessage(msg, "*");
        window.parent.postMessage({ type: "iframeResize", height: newHeight, timestamp: Date.now(), source: "webdoctor-widget" }, "*");
        console.log(`📤 Sent height to parent: ${newHeight}px`);
      } catch (error) {
        console.warn("Failed to send height to parent:", error);
      }
    }
  }

  triggerHeightUpdate() {
    setTimeout(() => this.sendHeightToParent(), 100);
  }

  forceHeightUpdate() {
    this.lastHeight = 0;
    this.sendHeightToParent();
  }
}

// Enhanced initialization with DOM ready check
console.log("Script loaded, checking DOM state...");
console.log("Document ready state:", document.readyState);

function initializeChat() {
  console.log("Initializing WebDoctorChat...");

  try {
    const chat = new WebDoctorChat();
    console.log("WebDoctorChat initialized successfully:", chat);

    // Store reference globally for debugging
    window.webdoc = chat;
    window.webdoctorChat = chat;

    // Initialize height manager
    setTimeout(() => {
      window.iframeHeightManager = new IframeHeightManager();
      console.log("✅ Iframe height manager initialized");
    }, 500);

    // Visual test for send button briefly
    setTimeout(() => {
      const sendBtn = document.getElementById("send-button");
      if (sendBtn) {
        console.log("Testing send button after initialization...");
        sendBtn.style.border = "2px solid #ff0000";
        setTimeout(() => { sendBtn.style.border = ""; }, 1000);
      }
    }, 1000);
  } catch (error) {
    console.error("Failed to initialize WebDoctorChat:", error);
  }
}

// DOM ready detection
if (document.readyState === "loading") {
  console.log("DOM still loading, waiting for DOMContentLoaded...");
  document.addEventListener("DOMContentLoaded", initializeChat);
} else {
  console.log("DOM already ready, initializing immediately...");
  setTimeout(initializeChat, 100);
}

// Handle visibility changes
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    const userInput = document.getElementById("user-input");
    if (userInput) setTimeout(() => userInput.focus(), 100);

    if (window.iframeHeightManager) {
      setTimeout(() => { window.iframeHeightManager.forceHeightUpdate(); }, 200);
    }
  }
});

// Handle window resize
window.addEventListener("resize", () => {
  if (window.iframeHeightManager) {
    window.iframeHeightManager.triggerHeightUpdate();
  }
});

// Global unhandled promise rejection logging
window.addEventListener("unhandledrejection", function (event) {
  console.error("Unhandled promise rejection:", event.reason);
  event.preventDefault();
});

// Handle page show (back/forward cache)
window.addEventListener("pageshow", function (event) {
  if (event.persisted && window.iframeHeightManager) {
    setTimeout(() => { window.iframeHeightManager.forceHeightUpdate(); }, 300);
  }
});

console.log("Script execution complete");
