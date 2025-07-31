// static/promptopilot/js/ad_builder.js

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("adForm");
  const resultBox = document.getElementById("result");

  if (!form) {
    console.warn("[PromptoPilot] No form with ID 'adForm' found.");
    return;
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault(); // Prevent page reload

    const formData = new FormData(form);

    try {
      const response = await fetch("/promptopilot/api/ad-builder/", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (data.result) {
        resultBox.hidden = false;
        resultBox.textContent = data.result;
        console.log("[PromptoPilot] Success:", data.result);
      } else {
        resultBox.hidden = false;
        resultBox.textContent = "Something went wrong.";
        console.error("[PromptoPilot] Invalid response:", data);
      }
    } catch (error) {
      resultBox.hidden = false;
      resultBox.textContent = "Error submitting form.";
      console.error("[PromptoPilot] Submission failed:", error);
    }
  });
});
