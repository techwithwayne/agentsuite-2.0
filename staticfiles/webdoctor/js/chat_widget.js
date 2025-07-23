document.addEventListener("DOMContentLoaded", () => {
  const userLang = navigator.language.split("-")[0];
  const langSelector = document.getElementById("language-select");
  if (["en", "es", "fr"].includes(userLang)) {
    langSelector.value = userLang;
  }
});

async function sendMessage() {
  const input = document.getElementById("user-input");
  const chatBody = document.getElementById("chat-body");
  const lang = document.getElementById("language-select").value;
  const message = input.value.trim();
  if (!message) return;

  chatBody.innerHTML += `<div><strong>You:</strong> ${message}</div>`;
  input.value = "";
  chatBody.scrollTop = chatBody.scrollHeight;

  const typingDiv = document.createElement("div");
  typingDiv.className = "typing-animation";
  typingDiv.innerHTML = "Veronica is typing";
  chatBody.appendChild(typingDiv);

  try {
    const response = await fetch("/webdoctor/handle_message/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, lang }),
    });

    const data = await response.json();

    setTimeout(() => {
      typingDiv.remove();
      chatBody.innerHTML += `<div><strong>Veronica:</strong> ${data.response}</div>`;
      chatBody.scrollTop = chatBody.scrollHeight;

      // ✅ NEW: Trigger form only when stage is "offered_report"
      if (data.stage === "offered_report") {
        document.getElementById("form-section").style.display = "block";
      }
    }, data.typing_delay * 1000);
  } catch (error) {
    typingDiv.remove();
    chatBody.innerHTML += `<div><strong>Veronica:</strong> Sorry, something went wrong.</div>`;
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
    alert(data.message || data.error);
  } catch (err) {
    alert("There was a problem submitting your request.");
  }
}
