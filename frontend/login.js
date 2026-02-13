async function apiFetch(path, options = {}) {
  const opts = {
    credentials: "include",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  };
  const res = await fetch(path, opts);
  return res;
}

function setError(msg) {
  const el = document.getElementById("error");
  if (!msg) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = msg;
}

async function checkAlreadyAuthed() {
  try {
    const res = await apiFetch("/api/auth/me", { method: "GET" });
    if (res.ok) window.location.href = "/";
  } catch {
    // ignore
  }
}

document.addEventListener("DOMContentLoaded", () => {
  checkAlreadyAuthed();

  const form = document.getElementById("loginForm");
  const btn = document.getElementById("loginBtn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError("");

    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;

    btn.disabled = true;
    btn.textContent = "Logging in...";

    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        window.location.href = "/";
        return;
      }
      const data = await res.json().catch(() => ({}));
      setError(data.detail || "Login failed.");
    } catch (err) {
      setError("Network error.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Log in";
    }
  });
});
