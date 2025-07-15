(function () {
  let sessionId = localStorage.getItem("wd-session-id");
  if (!sessionId) {
    sessionId = self.crypto.randomUUID();
    localStorage.setItem("wd-session-id", sessionId);
  }

  // ✅ Dynamic endpoint switching: local vs production
  const isLocal = ["127.0.0.1", "localhost"].includes(window.location.hostname);
  const endpoint = isLocal
    ? "http://127.0.0.1:8000/webdoctor/ask/"
    : "https://techwithwayne.pythonanywhere.com/webdoctor/ask/";

  const popSound = new Audio(
    "https://techwithwayne.pythonanywhere.com/static/agent/sounds/pop.mp3"
  );
  popSound.volume = 0.2;

  const botAvatar =
    "https://techwithwayne.com/wp-content/uploads/2025/06/techwithwayne-featured-image-wayne-hatter.jpg";
  const greetingMessage =
    "Hey there! 👋 What’s good? Drop your website issue below and I’ll help get you squared away.";

  const css = `
#wd-chat-toggle {
  position: fixed; bottom: 20px; right: 20px;
  background: #ff6c00; color: white;
  border: none; border-radius: 50%;
  width: 56px; height: 56px; cursor: pointer;
  font-size: 24px; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 10px rgba(0,0,0,0.3); z-index: 9999;
}

#wd-chat-box {
  position: fixed; bottom: 90px; right: 20px;
  width: 360px; max-height: 75vh;
  background: white; border: 1px solid #ddd; border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  display: none; flex-direction: column;
  font-family: 'Segoe UI', sans-serif; overflow: hidden; z-index: 9999;
}

#wd-messages {
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
}

.wd-msg {
  max-width: 80%; padding: 10px 14px;
  border-radius: 16px; word-wrap: break-word;
  position: relative; font-size: 14px; display: flex; align-items: flex-start;
}

.wd-bot {
  background: #f5f5f5; color: #121212;
  align-self: flex-start; border-bottom-left-radius: 4px;
}

.wd-user {
  background: #ff6c00; color: white;
  align-self: flex-end; border-bottom-right-radius: 4px;
}

.wd-avatar {
  width: 32px; height: 32px; border-radius: 50%; margin-right: 8px;
  flex-shrink: 0;
}

.wd-text {
  max-width: calc(100% - 40px);
}

.wd-timestamp {
  font-size: 11px; color: #888; margin-top: 4px;
}

#wd-form {
  display: flex; padding: 10px; gap: 8px; border-top: 1px solid #eee;
}

#wd-input {
  flex: 1; padding: 10px; border: 1px solid #ccc;
  border-radius: 20px; font-size: 14px;
}

#wd-send {
  background: #ff6c00; border: none; color: white;
  border-radius: 50%; width: 40px; height: 40px;
  font-size: 18px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
`;

  const html = `
<div id="wd-chat-box">
  <div id="wd-messages"></div>
  <form id="wd-form">
    <input type="text" id="wd-input" placeholder="Type your message..." required />
    <button type="submit" id="wd-send">➤</button>
  </form>
</div>
<button id="wd-chat-toggle">💬</button>
`;

  function injectStyles() {
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  }

  function injectHTML() {
    const container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);
  }

  function playPop() {
    try {
      popSound.currentTime = 0;
      popSound.play();
    } catch (e) {
      console.warn(e);
    }
  }

  function formatTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function addMessage(text, sender) {
    playPop();
    const msg = document.createElement("div");
    msg.className = `wd-msg wd-${sender}`;

    if (sender === "bot") {
      const avatar = document.createElement("img");
      avatar.src = botAvatar;
      avatar.className = "wd-avatar";

      const textContainer = document.createElement("div");
      textContainer.className = "wd-text";
      textContainer.innerHTML = DOMPurify.sanitize(marked.parse(text));

      msg.appendChild(avatar);
      msg.appendChild(textContainer);
    } else {
      msg.innerHTML = DOMPurify.sanitize(marked.parse(text));
    }

    const timestamp = document.createElement("div");
    timestamp.className = "wd-timestamp";
    timestamp.textContent = formatTime();
    msg.appendChild(timestamp);

    const messages = document.getElementById("wd-messages");
    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
  }

  function initChatWidget() {
    const toggle = document.getElementById("wd-chat-toggle");
    const box = document.getElementById("wd-chat-box");
    const form = document.getElementById("wd-form");
    const input = document.getElementById("wd-input");

    box.style.display = "flex";

    toggle.addEventListener("click", () => {
      box.style.display = box.style.display === "none" ? "flex" : "none";
    });

    addMessage(greetingMessage, "bot");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const userMessage = input.value.trim();
      if (!userMessage) return;

      addMessage(userMessage, "user");
      input.value = "";

      try {
        console.log("Sending to:", endpoint);
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: userMessage, session_id: sessionId }),
        });
        const data = await response.json();
        const fetchedResponse = data.response || JSON.stringify(data);
        addMessage(fetchedResponse, "bot");
      } catch (err) {
        console.error("Fetch error:", err);
        addMessage("Something went wrong. Please try again later.", "bot");
      }
    });
  }

  injectStyles();
  injectHTML();

  loadScripts(
    [
      "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
      "https://cdn.jsdelivr.net/npm/dompurify@3.0.3/dist/purify.min.js",
    ],
    initChatWidget
  );

  function loadScripts(urls, callback) {
    let loaded = 0;
    urls.forEach((url) => {
      const script = document.createElement("script");
      script.src = url;
      script.onload = () => {
        loaded++;
        if (loaded === urls.length) callback();
      };
      document.head.appendChild(script);
    });
  }
})();
