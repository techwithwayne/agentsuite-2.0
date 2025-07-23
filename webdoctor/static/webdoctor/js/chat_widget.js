document.addEventListener("DOMContentLoaded", () => {
  const userLang = navigator.language.split("-")[0];
  const langSelector = document.getElementById("language-select");
  if (["en", "es", "fr"].includes(userLang)) {
    langSelector.value = userLang;
  }

  document.getElementById("chat-body").innerHTML = "";
  document.getElementById("form-section").style.display = "none";
});

async function sendMessage() {
  const input = document.getElementById("user-input");
  const chatBody = document.getElementById("chat-body");
  const lang = document.getElementById("language-select").value;
  const message = input.value.trim();
  if (!message) return;

  chatBody.innerHTML += `<div class="chat-bubble user"><strong>You:</strong> ${message}</div>`;
  input.value = "";
  chatBody.scrollTop = chatBody.scrollHeight;

  const typingDiv = document.createElement("div");
  typingDiv.className = "typing-bubble";
  typingDiv.innerHTML =
    "<em>Veronica is typing</em><span class='dots'><span>.</span><span>.</span><span>.</span></span>";
  chatBody.appendChild(typingDiv);
  chatBody.scrollTop = chatBody.scrollHeight;

  try {
    const response = await fetch("/webdoctor/handle_message/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, lang }),
    });

    const data = await response.json();

    setTimeout(() => {
      typingDiv.remove();

      if (data.stage === "offered_report") {
        document.getElementById("chat-input").style.display = "none";
        document.getElementById("form-section").style.display = "block";
      }

      chatBody.innerHTML += `<div class="chat-bubble bot"><strong>Veronica:</strong> ${data.response}</div>`;
      chatBody.scrollTop = chatBody.scrollHeight;
    }, data.typing_delay * 1000);
  } catch (error) {
    typingDiv.remove();
    chatBody.innerHTML += `<div class="chat-bubble bot"><strong>Veronica:</strong> Sorry, something went wrong.</div>`;
  }
}

async function submitForm() {
  const name = document.getElementById("form-name").value;
  const email = document.getElementById("form-email").value;
  const issue = document.getElementById("user-input").value || "General issue";

  try {
    const response = await fetch("/webdoctor/submit_form/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, issue }),
    });

    const data = await response.json();
    const chatBody = document.getElementById("chat-body");

    // Hide form, restore input
    document.getElementById("form-section").style.display = "none";
    document.getElementById("chat-input").style.display = "flex";

    // Add Veronica’s final message
    chatBody.innerHTML += `
      <div class="chat-bubble bot">
        <strong>Veronica:</strong> Your report has been sent. Here are some options if you need more help:
      </div>
    `;

    // Add CTA buttons outside bubble
    const ctaContainer = document.createElement("div");
    ctaContainer.style.display = "flex";
    ctaContainer.style.gap = "10px";
    ctaContainer.style.marginTop = "10px";
    ctaContainer.style.flexWrap = "wrap";

    const siteReviewBtn = document.createElement("a");
    siteReviewBtn.href = "https://techwithwayne.com/free-site-review";
    siteReviewBtn.target = "_blank";
    siteReviewBtn.className = "cta-button";
    siteReviewBtn.textContent = "Free Site Review";

    const consultBtn = document.createElement("a");
    consultBtn.href = "https://techwithwayne.com/free-consultation";
    consultBtn.target = "_blank";
    consultBtn.className = "cta-button";
    consultBtn.textContent = "Free Consultation";

    ctaContainer.appendChild(siteReviewBtn);
    ctaContainer.appendChild(consultBtn);
    chatBody.appendChild(ctaContainer);

    chatBody.scrollTop = chatBody.scrollHeight;
  } catch (err) {
    const chatBody = document.getElementById("chat-body");
    chatBody.innerHTML += `<div class="chat-bubble bot"><strong>Veronica:</strong> Sorry, there was an issue submitting your request.</div>`;
  }
}

// ✅ Make globally accessible for inline onclick=
window.sendMessage = sendMessage;
window.submitForm = submitForm;
