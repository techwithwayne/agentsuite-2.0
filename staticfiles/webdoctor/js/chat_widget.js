// Array of greeting messages for the chatbot agent Shirley
const greetings = [
  "Hey, I'm Shirley—sorry your website's giving you trouble. Let's sort it out together. What can I do for you today?"
];

// Function to select a random greeting from the array
function getRandomGreeting() {
  return greetings[Math.floor(Math.random() * greetings.length)];
}

// Function to calculate and send the current height of the chat widget to the parent window (for iframe resizing)
function sendHeight() {
  // Attempt to find the main chat widget container; fallback to document body if not found
  const chatWidget = document.getElementById('chat-widget') || document.body;
  // Initialize height with the scroll height of the widget
  let height = chatWidget.scrollHeight;

  // If no main widget container is found, manually sum heights of individual sections
  if (!document.getElementById('chat-widget')) {
    const chatBody = document.getElementById('chat-body');
    const chatInput = document.getElementById('chat-input');
    const formSection = document.getElementById('form-section');
    height = 0;
    // Add chat body height if element exists
    if (chatBody) height += chatBody.scrollHeight;
    // Add chat input height if element exists
    if (chatInput) height += chatInput.scrollHeight;
    // Add form section height if element exists and is visible
    if (formSection && formSection.style.display !== 'none') height += formSection.scrollHeight;
  }

  // Add extra padding to ensure the input area remains visible
  height += 70;
  // Send the height via postMessage to the parent window for resizing the iframe
  window.parent.postMessage({ height: height }, 'https://showcase.techwithwayne.com/');
  // Log the sent height for debugging purposes
  console.log('Sent height to parent:', height);
}

// Event listener for when the DOM content has fully loaded
document.addEventListener("DOMContentLoaded", () => {
  // Detect the user's language from the browser settings (first part before hyphen)
  const userLang = navigator.language.split("-")[0];
  // Get the language selector element
  const langSelector = document.getElementById("language-select");

  // Set the language selector value to user's language if supported, otherwise default to English
  if (langSelector) {
    langSelector.value = ["en", "es", "fr"].includes(userLang) ? userLang : "en";
  }

  // Get the form section element
  const formSection = document.getElementById("form-section");
  // Hide the form section initially if it exists
  if (formSection) {
    formSection.style.display = "none";
  }

  // Use a short delay to ensure DOM is settled before injecting the greeting
  setTimeout(() => {
    // Get the chat body element where messages are displayed
    const chatBody = document.getElementById("chat-body");
    // If chat body not found, log a warning and skip greeting injection
    if (!chatBody) {
      console.warn("chat-body not found. Skipping greeting injection.");
      return;
    }

    // Select a random greeting message
    const greeting = getRandomGreeting();
    // Append the greeting as a bot message bubble to the chat body
    chatBody.innerHTML += `
      <div class="chat-bubble bot">
        <strong>Shirley:</strong> ${greeting}
      </div>
    `;
    // Log the injected greeting for debugging
    console.log("Greeting injected:", greeting);
    // Update the widget height after adding the greeting
    sendHeight();
    // Dispatch a custom event to signal chat update
    document.dispatchEvent(new Event('chatUpdated'));
  }, 100);

  // Create a ResizeObserver to monitor size changes and update height accordingly
  const observer = new ResizeObserver(() => {
    // Call sendHeight on resize
    sendHeight();
  });
  // Select the element to observe (chat widget, chat body, or body as fallback)
  const chatWidget = document.getElementById('chat-widget') || document.getElementById('chat-body') || document.body;
  // Start observing the selected element
  observer.observe(chatWidget);
});

// Asynchronous function to handle sending user messages and receiving bot responses
async function sendMessage() {
  // Get the user input element
  const input = document.getElementById("user-input");
  // Get the chat body element
  const chatBody = document.getElementById("chat-body");

  // If required elements are missing, log warning and exit
  if (!input || !chatBody) {
    console.warn("Chat elements not found. Cannot send message.");
    return;
  }

  // Trim the user's message input
  const message = input.value.trim();
  // Exit if message is empty
  if (!message) return;

  // Get current time for timestamp
  const now = new Date();
  // Format timestamp as HH:MM (24-hour format)
  const timestamp = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  // Append the user's message as a bubble with timestamp to the chat body
  chatBody.innerHTML += `
    <div class="chat-bubble user">
      ${message}
      <div class="timestamp">${timestamp}</div>
    </div>
  `;
  // Clear the input field
  input.value = "";
  // Scroll to the bottom of the chat body
  chatBody.scrollTop = chatBody.scrollHeight;
  // Update widget height after adding message
  sendHeight();
  // Dispatch chat update event
  document.dispatchEvent(new Event('chatUpdated'));

  // Create and append a typing indicator bubble
  const typingDiv = document.createElement("div");
  typingDiv.className = "typing-bubble";
  typingDiv.innerHTML = "Shirley is typing...";
  chatBody.appendChild(typingDiv);
  // Scroll to bottom after adding typing indicator
  chatBody.scrollTop = chatBody.scrollHeight;

  // Try block for handling the API request to send message
  try {
    // Send POST request to handle_message endpoint with user message
    const response = await fetch("/webdoctor/handle_message/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    // Parse the JSON response from the server
    const data = await response.json();
    // Remove the typing indicator
    typingDiv.remove();

    // Get current time for bot timestamp
    const botTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    // Append the bot's response as a bubble with timestamp
    chatBody.innerHTML += `
      <div class="chat-bubble bot">
        ${data.response}
        <div class="timestamp">${botTime}</div>
      </div>
    `;
    // Scroll to bottom after adding response
    chatBody.scrollTop = chatBody.scrollHeight;
    // Update widget height
    sendHeight();
    // Dispatch chat update event
    document.dispatchEvent(new Event('chatUpdated'));

    // Check if the stage requires showing the form (offered_report)
    if (String(data.stage).trim() === "offered_report") {
      // Get the chat input section
      const chatInput = document.getElementById("chat-input");
      // Hide chat input if exists
      if (chatInput) {
        chatInput.style.display = "none";
      }
      // Get the form section
      const formSection = document.getElementById("form-section");
      // Show form section if exists
      if (formSection) {
        formSection.style.display = "flex";
      }
      // Update widget height after visibility change
      sendHeight();
      // Dispatch chat update event
      document.dispatchEvent(new Event('chatUpdated'));
    }
  // Catch block for handling errors in message sending
  } catch (error) {
    // Remove typing indicator on error
    typingDiv.remove();
    // Append an error message bubble
    chatBody.innerHTML += `<div class="chat-bubble bot">Oops! Something went wrong.</div>`;
    // Log the error for debugging
    console.error("Error in sendMessage:", error);
    // Update widget height
    sendHeight();
    // Dispatch chat update event
    document.dispatchEvent(new Event('chatUpdated'));
  }
}

// Asynchronous function to handle form submission for diagnostic report
async function submitForm() {
  // Get form name input element
  const nameEl = document.getElementById("form-name");
  // Get form email input element
  const emailEl = document.getElementById("form-email");
  // Get user input element (fallback for issue description)
  const inputEl = document.getElementById("user-input");

  // If required form elements missing, log warning and exit
  if (!nameEl || !emailEl) {
    console.warn("Form elements not found. Cannot submit form.");
    return;
  }

  // Get name value from form
  const name = nameEl.value;
  // Get email value from form
  const email = emailEl.value;
  // Get issue description from user input or default
  const issue = (inputEl ? inputEl.value : "") || "General issue";

  // Try block for handling form submission API request
  try {
    // Send POST request to submit_form endpoint with form data
    const response = await fetch("/webdoctor/submit_form/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, issue }),
    });

    // Parse JSON response
    const data = await response.json();
    // Get chat body element
    const chatBody = document.getElementById("chat-body");

    // If chat body not found, log warning and exit
    if (!chatBody) {
      console.warn("chat-body not found. Cannot update chat after form submission.");
      return;
    }

    // Get form section and hide it
    const formSection = document.getElementById("form-section");
    if (formSection) {
      formSection.style.display = "none";
    }
    // Get chat input and show it
    const chatInput = document.getElementById("chat-input");
    if (chatInput) {
      chatInput.style.display = "flex";
    }

    // Append success message to chat body
    chatBody.innerHTML += `
      <div class="chat-bubble bot">
        <strong>Shirley:</strong> Your report has been sent. Here are some options if you need more help:
      </div>
    `;

    // Create container for CTA buttons
    const ctaContainer = document.createElement("div");
    // Style the CTA container for layout
    ctaContainer.style.display = "flex";
    ctaContainer.style.gap = "10px";
    ctaContainer.style.marginTop = "10px";
    ctaContainer.style.flexWrap = "wrap";

    // Create link button for free site review
    const siteReviewBtn = document.createElement("a");
    siteReviewBtn.href = "https://techwithwayne.com/free-site-review";
    siteReviewBtn.target = "_blank";
    siteReviewBtn.className = "cta-button";
    siteReviewBtn.textContent = "Free Site Review";

    // Create link button for free consultation
    const consultBtn = document.createElement("a");
    consultBtn.href = "https://techwithwayne.com/free-consultation";
    consultBtn.target = "_blank";
    consultBtn.className = "cta-button";
    consultBtn.textContent = "Free Consultation";

    // Append buttons to CTA container
    ctaContainer.appendChild(siteReviewBtn);
    ctaContainer.appendChild(consultBtn);
    // Append CTA container to chat body
    chatBody.appendChild(ctaContainer);

    // Scroll to bottom of chat body
    chatBody.scrollTop = chatBody.scrollHeight;
    // Update widget height
    sendHeight();
    // Dispatch chat update event
    document.dispatchEvent(new Event('chatUpdated'));
  // Catch block for handling errors in form submission
  } catch (err) {
    // Log error for debugging
    console.error("Error in submitForm:", err);
    // Get chat body
    const chatBody = document.getElementById("chat-body");
    // If chat body exists, append error message
    if (chatBody) {
      chatBody.innerHTML += `<div class="chat-bubble bot"><strong>Shirley:</strong> Sorry, there was an issue submitting your request.</div>`;
      // Update height
      sendHeight();
      // Dispatch chat update event
      document.dispatchEvent(new Event('chatUpdated'));
    }
  }
}

// Expose sendMessage and submitForm functions to global scope for HTML onclick events
window.sendMessage = sendMessage;
window.submitForm = submitForm;