// JavaScript for WebDoctor Chat Widget - FIXED VERSION WITH SOUND
class WebDoctorChat {
  constructor() {
    console.log("WebDoctorChat constructor called");

    this.isTyping = false;
    this.messageCount = 0;
    this.currentStage = "initial";
    this.formOffered = false;
    this.formAccepted = false;
    this.sendInProgress = false; // ✅ Add flag to prevent double-sending

    this.greetings = [
      "Hey there! I'm Shirley, your website's doctor. What seems to be the issue today?",
      "Hi! Shirley here—ready to help diagnose your website troubles. What's going on?",
      "Welcome! I'm Shirley. Tell me what's bugging your website and I'll help fix it.",
    ];

    // ✅ Initialize audio for typing sound
    this.initializeAudio();

    console.log("About to call init()");
    this.init();
  }

  // ✅ New method to initialize audio
  initializeAudio() {
    console.log("🔊 Initializing typing sound...");

    try {
      // Create audio element for typing sound
      this.typingSound = new Audio();
      this.typingSound.preload = "auto";

      // Set the path to your sound file
      // Django will serve this from static/webdoctor/sounds/bong.mp3
      this.typingSound.src = "/static/webdoctor/sounds/bong.mp3";

      // Set volume (adjust as needed - 0.0 to 1.0)
      this.typingSound.volume = 0.3;

      // Handle audio loading
      this.typingSound.addEventListener("canplaythrough", () => {
        console.log("✅ Typing sound loaded successfully");
      });

      this.typingSound.addEventListener("error", (e) => {
        console.warn("⚠️ Could not load typing sound:", e);
        console.warn(
          "Sound file should be at: /static/webdoctor/sounds/bong.mp3"
        );
      });

      // Preload the audio
      this.typingSound.load();
    } catch (error) {
      console.warn("⚠️ Audio initialization failed:", error);
      this.typingSound = null;
    }
  }

  // ✅ New method to play typing sound
  playTypingSound() {
    if (!this.typingSound) {
      console.log("🔇 No typing sound available");
      return;
    }

    try {
      // Reset audio to beginning in case it was played recently
      this.typingSound.currentTime = 0;

      // Play the sound
      const playPromise = this.typingSound.play();

      // Handle the play promise (required for modern browsers)
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            console.log("🔊 Typing sound played successfully");
          })
          .catch((error) => {
            console.warn("⚠️ Could not play typing sound:", error);
            // This is common if user hasn't interacted with page yet
          });
      }
    } catch (error) {
      console.warn("⚠️ Error playing typing sound:", error);
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

      // Test button immediately
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

      const greeting =
        this.greetings[Math.floor(Math.random() * this.greetings.length)];
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

    console.log("✅ User message added, total messages:", this.messageCount);
  }

  // In your chat_widget.js, replace the addBotMessage function with this:

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
      // ✅ Play typing sound when animation starts
      this.playTypingSound();
      this.animateTyping(messageDiv, message, callback); // ✅ Pass callback to animation
    } else {
      messageDiv.innerHTML = `<strong>Shirley:</strong> ${this.escapeHtml(
        message
      )}`;
      chatBody.appendChild(messageDiv);
      this.scrollToBottom();
      console.log("✅ Bot message added instantly");

      // ✅ Execute callback if provided
      if (callback) {
        setTimeout(callback, 100);
      }
    }
  }

  // ✅ Also update the animateTyping function to handle callback:
  animateTyping(messageDiv, message, callback = null) {
    console.log("⌨️ Animating typing for message:", message);

    const chatBody = document.getElementById("chat-body");
    messageDiv.innerHTML =
      '<strong>Shirley:</strong> <span class="typing-text"></span>';
    chatBody.appendChild(messageDiv);

    const typingSpan = messageDiv.querySelector(".typing-text");
    if (!typingSpan) {
      console.error("❌ Typing span not found!");
      return;
    }

    let index = 0;
    const delay = Math.max(20, Math.min(50, 1000 / message.length));
    console.log("⏱️ Typing delay:", delay);

    const typeInterval = setInterval(() => {
      if (index < message.length) {
        typingSpan.textContent += message.charAt(index);
        index++;
        this.scrollToBottom();
      } else {
        console.log("✅ Typing animation complete");
        clearInterval(typeInterval);
        this.isTyping = false;

        // ✅ Execute callback after typing is complete
        if (callback) {
          console.log("🎯 Executing callback after typing animation");
          setTimeout(callback, 200); // Small delay for better UX
        }

        this.checkForFormTrigger(message);
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
    typingDiv.innerHTML =
      '<strong>Shirley:</strong> <span class="dots"><span>•</span><span>•</span><span>•</span></span>';
    chatBody.appendChild(typingDiv);
    this.scrollToBottom();

    console.log("✅ Typing indicator shown");
    return typingDiv;
  }

  removeTypingIndicator() {
    const typingIndicator = document.getElementById("typing-indicator");
    if (typingIndicator) {
      typingIndicator.remove();
      console.log("✅ Typing indicator removed");
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
    const offeredReport = reportOffers.some((phrase) =>
      messageText.includes(phrase)
    );

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
      }, 300);
      console.log("✅ Form shown");
    }
  }

  hideForm() {
    console.log("📝 Hiding form...");
    const formSection = document.getElementById("form-section");
    if (formSection) {
      formSection.style.display = "none";
      console.log("✅ Form hidden");
    }
  }

  // In your chat_widget.js, replace the sendMessage function with this fixed version:

  async sendMessage() {
    console.log(
      "Send message called, isTyping:",
      this.isTyping,
      "sendInProgress:",
      this.sendInProgress
    );

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

    // ✅ Check if user is accepting report offer (but DON'T show form yet)
    let isAcceptingReport = false;
    if (this.formOffered && !this.formAccepted) {
      const acceptanceWords = [
        "yes",
        "sure",
        "okay",
        "ok",
        "please",
        "send",
        "email",
        "absolutely",
        "definitely",
      ];
      const userResponse = message.toLowerCase();

      if (acceptanceWords.some((word) => userResponse.includes(word))) {
        isAcceptingReport = true;
        this.formAccepted = true;
        console.log(
          "✅ Form acceptance detected - will show form after AI response"
        );
      }
    }

    const typingIndicator = this.showTypingIndicator();

    try {
      const targetUrl =
        window.webdoctorUrls?.handleMessage || "/agent/handle_message/";
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
        body: JSON.stringify({
          message: message,
          lang: "en",
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      console.log("📡 Response status:", response.status);
      console.log("📡 Response ok:", response.ok);

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      let data;
      try {
        data = await response.json();
      } catch (jsonError) {
        console.error("❌ JSON parsing error:", jsonError);
        throw new Error("Invalid response format from server");
      }

      console.log("📦 Response data:", data);

      this.removeTypingIndicator();

      if (data.response && data.response.trim()) {
        this.currentStage = data.stage || this.currentStage;

        // ✅ Add bot message with callback to show form after typing animation
        this.addBotMessage(data.response, true, () => {
          // ✅ Show form AFTER the AI response is fully typed out
          if (isAcceptingReport) {
            console.log("✅ Showing form after AI response");
            setTimeout(() => this.showForm(), 500);
          }
        });

        console.log("✅ Bot response added");
      } else {
        this.addBotMessage(
          "Sorry, I didn't get that. Could you try rephrasing?"
        );
        console.log("⚠️ No response in data, showing fallback");
        this.isTyping = false;
      }
    } catch (error) {
      console.error("❌ Error in sendMessage:", error);
      this.removeTypingIndicator();

      let errorMessage;
      if (error.name === "AbortError") {
        errorMessage = "Request timed out. Please try again.";
      } else if (
        error.message.includes("NetworkError") ||
        error.message.includes("Failed to fetch")
      ) {
        errorMessage =
          "Connection problem. Please check your internet and try again.";
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
    const userMessages = Array.from(
      chatBody.querySelectorAll(".chat-bubble.user")
    )
      .map((msg) => msg.textContent.replace("You: ", ""))
      .join(" | ");

    const originalButtonText = submitBtn.textContent;
    submitBtn.textContent = "Sending...";
    submitBtn.disabled = true;

    try {
      const targetUrl = "/agent/submit_form/";
      console.log("🌐 Submitting form to:", targetUrl);

      // ✅ Enhanced request with timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch(targetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this.getCsrfToken(),
        },
        body: JSON.stringify({
          name: name,
          email: email,
          issue: userMessages || "General website consultation",
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // ✅ Enhanced response handling
      let data;
      try {
        data = await response.json();
      } catch (jsonError) {
        console.error("❌ Form response JSON parsing error:", jsonError);
        throw new Error("Invalid response format");
      }

      console.log("📋 Form response:", data);

      if (response.ok && data.message) {
        this.addBotMessage(
          `Thanks ${name}! 🎉 ${data.message} Check your inbox in a few minutes.`
        );
        this.hideForm();
      } else {
        throw new Error(data.error || "Failed to send report");
      }
    } catch (error) {
      console.error("❌ Form submission error:", error);

      // ✅ Better error messages
      let errorMessage;
      if (error.name === "AbortError") {
        errorMessage = "Form submission timed out. Please try again.";
      } else if (
        error.message.includes("NetworkError") ||
        error.message.includes("Failed to fetch")
      ) {
        errorMessage =
          "Connection problem. Please check your internet and try again.";
      } else {
        errorMessage =
          "Sorry, there was an issue sending your report. Please try again.";
      }

      this.addBotMessage(errorMessage);
    } finally {
      submitBtn.textContent = originalButtonText;
      submitBtn.disabled = false;
    }
  }

  isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  getCsrfToken() {
    console.log("Getting CSRF token...");

    // Method 1: From JavaScript window variable (most reliable)
    if (window.csrfToken) {
      console.log("CSRF token from window variable: Found");
      return window.csrfToken;
    }

    // Method 2: From hidden input
    const csrfInput = document.querySelector(
      'input[name="csrfmiddlewaretoken"]'
    );
    if (csrfInput && csrfInput.value) {
      console.log("CSRF token from hidden input: Found");
      return csrfInput.value;
    }

    // Method 3: From meta tag (fallback)
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) {
      const token = metaToken.getAttribute("content");
      console.log("CSRF token from meta tag:", token ? "Found" : "Empty");
      return token;
    }

    // Method 4: From cookie (last resort)
    const cookieValue = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1];
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

// Enhanced initialization with DOM ready check
console.log("Script loaded, checking DOM state...");
console.log("Document ready state:", document.readyState);

function initializeChat() {
  console.log("Initializing WebDoctorChat...");

  try {
    const chat = new WebDoctorChat();
    console.log("WebDoctorChat initialized successfully:", chat);

    // ✅ Store reference globally for debugging
    window.webdoctorChat = chat;

    // Test button immediately after initialization
    setTimeout(() => {
      const sendBtn = document.getElementById("send-button");
      if (sendBtn) {
        console.log("Testing send button after initialization...");
        sendBtn.style.border = "2px solid #ff0000";
        setTimeout(() => {
          sendBtn.style.border = "";
        }, 1000);
      }
    }, 1000);
  } catch (error) {
    console.error("Failed to initialize WebDoctorChat:", error);
  }
}

// ✅ Enhanced DOM ready detection
if (document.readyState === "loading") {
  // DOM is still loading, wait for it
  console.log("DOM still loading, waiting for DOMContentLoaded...");
  document.addEventListener("DOMContentLoaded", initializeChat);
} else {
  // DOM is already ready, initialize immediately
  console.log("DOM already ready, initializing immediately...");
  // ✅ Use setTimeout to ensure all elements are rendered
  setTimeout(initializeChat, 100);
}

// Handle visibility changes
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    const userInput = document.getElementById("user-input");
    if (userInput) {
      setTimeout(() => userInput.focus(), 100);
    }
  }
});

// ✅ Add global error handler for unhandled promise rejections
window.addEventListener("unhandledrejection", function (event) {
  console.error("Unhandled promise rejection:", event.reason);
  // Prevent the default browser behavior
  event.preventDefault();
});

console.log("Script execution complete");
