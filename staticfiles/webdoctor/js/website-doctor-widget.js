document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("wd-chat-toggle");
  const chatBox = document.getElementById("wd-chat-box");
  const messagesDiv = document.getElementById("wd-messages");
  const input = document.getElementById("wd-input");
  const sendButton = document.getElementById("wd-send");
  const reportForm = document.getElementById("wd-report-form");
  const reportEmail = document.getElementById("wd-report-email");
  const reportSubmit = document.getElementById("wd-report-submit");
  const nudgeButtons = document.getElementById("wd-nudge-buttons");

  let sessionId = localStorage.getItem("wd_session_id") || null;
  let stage = localStorage.getItem("wd_stage") || "conversation";
  let yesCount = 0;

  const typingSound = new Audio("/static/webdoctor/sounds/typing.mp3"); // Updated to local path

  toggle.addEventListener("click", () => {
    chatBox.style.display = chatBox.style.display === "none" ? "flex" : "none";
    if (chatBox.style.display === "flex" && !sessionId) {
      initializeChat();
    }
  });

  sendButton.addEventListener("click", sendMessage);
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  reportSubmit.addEventListener("click", submitReport);
  nudgeButtons.addEventListener("click", (e) => {
    if (e.target.id === "wd-nudge-consult") {
      appendMessage("Assistant", "Scheduling a free consultation...");
    } else if (e.target.id === "wd-nudge-review") {
      appendMessage("Assistant", "Requesting a site review...");
    }
  });

  function initializeChat() {
    sessionId =
      sessionId ||
      (crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2));
    localStorage.setItem("wd_session_id", sessionId);
    appendMessage(
      "Assistant",
      "Welcome to Website Doctor! How can I help with your website?"
    );
  }

  async function sendMessage() {
    const message = input.value.trim();
    if (!message) return;

    appendMessage("User", message);
    input.value = "";
    typingSound.play();

    const botMessageDiv = appendMessage("Assistant", "", true);
    try {
      const response = await fetch("/webdoctor/ask/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message, stage }),
      });
      const data = await response.json();

      if (data.error) {
        botMessageDiv.innerHTML = `<div class="wd-text">Error: ${data.error}</div>`;
        return;
      }

      sessionId = data.session_id;
      stage = data.stage;
      localStorage.setItem("wd_session_id", sessionId);
      localStorage.setItem("wd_stage", stage);

      botMessageDiv.innerHTML = `<div class="wd-text">${DOMPurify.sanitize(
        data.response
      )}</div>`;
      botMessageDiv.classList.remove("wd-typing");

      if (data.show_form) {
        reportForm.style.display = "block";
        nudgeButtons.style.display = "none";
      } else if (data.diagnostic) {
        handleReportOffer(message);
      } else if (data.is_report_sent) {
        reportForm.style.display = "none";
      }
    } catch (error) {
      botMessageDiv.innerHTML = `<div class="wd-text">Error: Failed to connect to server</div>`;
      botMessageDiv.classList.remove("wd-typing");
    }
  }

  function appendMessage(sender, content, isTyping = false) {
    const div = document.createElement("div");
    div.className = `wd-msg wd-${sender.toLowerCase()} ${
      isTyping ? "wd-typing" : ""
    }`;
    const avatar =
      sender === "Assistant"
        ? '<img src="/static/webdoctor/images/bot-avatar.png" class="wd-avatar" alt="Bot avatar">'
        : "";
    const timestamp = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    div.innerHTML = `${avatar}<div class="wd-text">${DOMPurify.sanitize(
      marked.parse(content)
    )}</div><div class="wd-timestamp">${timestamp}</div>`;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return div;
  }

  function handleReportOffer(userMessage) {
    if (userMessage.toLowerCase() === "yes") {
      yesCount++;
      if (yesCount >= 2) {
        reportForm.style.display = "block";
        nudgeButtons.style.display = "none";
        appendMessage(
          "Assistant",
          "Please enter your email to receive the report."
        );
      } else {
        appendMessage("Assistant", 'Please confirm again by typing "yes".');
      }
    } else if (userMessage.toLowerCase() === "no") {
      yesCount = 0;
      reportForm.style.display = "none";
      nudgeButtons.style.display = "flex";
      appendMessage(
        "Assistant",
        "Would you like a free consultation or a site review?"
      );
    }
  }

  async function submitReport() {
    const email = reportEmail.value.trim();
    if (!email) {
      appendMessage("Assistant", "Please enter a valid email address.");
      return;
    }

    try {
      const response = await fetch("/webdoctor/ask/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          stage,
          email,
          report_confirmed: true,
        }),
      });
      const data = await response.json();

      if (data.error) {
        appendMessage("Assistant", `Error: ${data.error}`);
        return;
      }

      appendMessage("Assistant", data.message);
    } catch (error) {
      appendMessage("Assistant", "Error: Failed to send report");
    }
  }
});
