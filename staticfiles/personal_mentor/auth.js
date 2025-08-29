(function () {
  const VERSION = "auth.js v2025-08-12-RESEND";
  console.log("%cPersonal Mentor Auth:", "font-weight:bold", VERSION);

  // Elements
  const overlay = document.getElementById("pm-auth-overlay");
  const cardRegister = document.getElementById("pm-auth-register");
  const cardLogin = document.getElementById("pm-auth-login");
  const cardConfirm = document.getElementById("pm-auth-confirm");

  const formRegister = document.getElementById("pm-auth-register-form");
  const formLogin = document.getElementById("pm-auth-login-form");
  const formConfirm = document.getElementById("pm-auth-confirm-form");

  const errRegister = document.getElementById("pm-auth-register-error");
  const errLogin = document.getElementById("pm-auth-login-error");
  const errConfirm = document.getElementById("pm-auth-confirm-error");

  const linkLogin = document.getElementById("pm-link-login");
  const linkRegister = document.getElementById("pm-link-register");
  const btnResend = document.getElementById("pm-resend");

  // Endpoints
  const E_REGISTER = "/personal-mentor/auth/register/";
  const E_CONFIRM = "/personal-mentor/auth/confirm/";
  const E_LOGIN = "/personal-mentor/auth/login/";
  const E_RESEND = "/personal-mentor/auth/resend/";

  // Gate the chat UI (disable input until verified)
  const chatForm = document.getElementById("pm-form");
  const chatInput = document.getElementById("pm-input");
  const chatSendBtn = chatForm?.querySelector("button[type='submit']");
  if (chatInput) chatInput.disabled = true;
  if (chatSendBtn) chatSendBtn.disabled = true;

  function unlockChat() {
    overlay.hidden = true;
    if (chatInput) chatInput.disabled = false;
    if (chatSendBtn) chatSendBtn.disabled = false;
  }

  function showCard(which) {
    cardRegister.hidden = which !== "register";
    cardLogin.hidden = which !== "login";
    cardConfirm.hidden = which !== "confirm";
    console.log("[Auth] Showing card:", which);
  }

  // CSRF helper
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
  }
  function csrftoken() {
    return getCookie("csrftoken");
  }

  // Fetch wrapper
  async function postForm(url, data) {
    const formData = new FormData();
    Object.entries(data).forEach(([k, v]) => formData.append(k, v));
    const res = await fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrftoken() || "" },
      body: formData,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || json.ok === false) {
      const msg = json.error || `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return json;
  }

  // Buttons → loading state
  function setLoading(btn, isLoading) {
    if (!btn) return;
    if (isLoading) {
      btn.dataset._label = btn.textContent;
      btn.disabled = true;
      btn.classList.add("pm-loading");
      btn.textContent = "Processing…";
    } else {
      btn.disabled = false;
      btn.classList.remove("pm-loading");
      btn.textContent = btn.dataset._label || "Submit";
    }
  }

  // Eye toggles for password fields
  function bindEyes() {
    document.querySelectorAll(".pm-eye").forEach((eye) => {
      const input = eye.previousElementSibling;
      if (!(input && input.tagName === "INPUT")) return;
      const toggle = () => {
        input.type = input.type === "password" ? "text" : "password";
        eye.setAttribute("aria-pressed", input.type !== "password");
      };
      eye.addEventListener("click", toggle);
      eye.addEventListener("mousedown", (e) => {
        e.preventDefault();
        input.type = "text";
      });
      eye.addEventListener("mouseup", () => {
        input.type = "password";
      });
      eye.addEventListener("mouseleave", () => {
        input.type = "password";
      });
    });
  }
  bindEyes();

  function clearErrors() {
    errRegister.textContent = "";
    errLogin.textContent = "";
    errConfirm.textContent = "";
  }

  // Resend cooldown timer
  let cooldownTimer = null;
  function startCooldown(seconds) {
    if (!btnResend) return;
    clearInterval(cooldownTimer);
    let remaining = Math.max(0, seconds | 0);
    const update = () => {
      if (remaining > 0) {
        btnResend.disabled = true;
        btnResend.textContent = `Resend code (${remaining}s)`;
        remaining -= 1;
      } else {
        btnResend.disabled = false;
        btnResend.textContent = "Resend code";
        clearInterval(cooldownTimer);
      }
    };
    update();
    cooldownTimer = setInterval(update, 1000);
  }

  // Nav links
  linkLogin?.addEventListener("click", () => {
    clearErrors();
    showCard("login");
  });
  linkRegister?.addEventListener("click", () => {
    clearErrors();
    showCard("register");
  });

  // Resend code flow
  btnResend?.addEventListener("click", async () => {
    errConfirm.textContent = "";
    try {
      btnResend.disabled = true;
      btnResend.textContent = "Resending…";
      const r = await postForm(E_RESEND, {});
      console.log("[Auth] resend:", r);
      if (typeof r.cooldown_remaining_seconds === "number") {
        startCooldown(r.cooldown_remaining_seconds);
      }
      if (r.email_sent === false) {
        console.warn("[Auth] Email NOT sent. Check EMAIL_BACKEND and Mailgun env on server.");
      }
      // Keep user on confirm screen
    } catch (err) {
      console.error("[Auth] resend error:", err);
      errConfirm.textContent = err.message || "Could not resend code.";
      btnResend.disabled = false;
      btnResend.textContent = "Resend code";
    }
  });

  // Forms
  formRegister.addEventListener("submit", async (e) => {
    e.preventDefault();
    errRegister.textContent = "";
    const name = document.getElementById("pm-name").value.trim();
    const email = document.getElementById("pm-email").value.trim().toLowerCase();
    const password = document.getElementById("pm-password").value;

    const submitBtn = formRegister.querySelector(".pm-auth-submit");
    try {
      setLoading(submitBtn, true);
      const r = await postForm(E_REGISTER, { name, email, password });
      console.log("[Auth] register result:", r);
      if (r.email_sent === false) {
        console.warn("[Auth] Email NOT sent. Check EMAIL_BACKEND and Mailgun env on server.");
      }
      if (r.next === "confirm") {
        showCard("confirm");
        // After fresh registration, cooldown starts at 0; allow immediate resend if needed.
        startCooldown(0);
      }
    } catch (err) {
      console.error("[Auth] register error:", err);
      errRegister.textContent = err.message || "Could not create account.";
    } finally {
      setLoading(submitBtn, false);
    }
  });

  formLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    errLogin.textContent = "";
    const email = document.getElementById("pm-login-email").value.trim().toLowerCase();
    const password = document.getElementById("pm-login-password").value;

    const submitBtn = formLogin.querySelector(".pm-auth-submit");
    try {
      setLoading(submitBtn, true);
      const r = await postForm(E_LOGIN, { email, password });
      console.log("[Auth] login result:", r);
      if (r.next === "confirm") {
        if (r.email_sent === false) {
          console.warn("[Auth] Email NOT sent. Check EMAIL_BACKEND and Mailgun env on server.");
        }
        showCard("confirm");
        // Give users feedback that a new email was just sent by starting full cooldown (~120s)
        startCooldown(120);
      } else if (r.ok) {
        unlockChat();
      }
    } catch (err) {
      console.error("[Auth] login error:", err);
      errLogin.textContent = err.message || "Login failed.";
    } finally {
      setLoading(submitBtn, false);
    }
  });

  formConfirm.addEventListener("submit", async (e) => {
    e.preventDefault();
    errConfirm.textContent = "";
    const email = document.getElementById("pm-confirm-email").value.trim().toLowerCase() || "";
    const code = document.getElementById("pm-confirm-code").value.trim();

    const submitBtn = formConfirm.querySelector(".pm-auth-submit");
    try {
      setLoading(submitBtn, true);
      const r = await postForm(E_CONFIRM, { email, code });
      console.log("[Auth] confirm result:", r);
      if (r.ok) {
        unlockChat();
      }
    } catch (err) {
      console.error("[Auth] confirm error:", err);
      errConfirm.textContent = err.message || "Invalid code.";
    } finally {
      setLoading(submitBtn, false);
    }
  });
})();
