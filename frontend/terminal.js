let terminalSocket = null;
let terminalSupported = false;
let terminalEnabled = false;
let selectedProjectId = null;
let term = null;
let fitAddon = null;
let termResizeTimer = null;

const termDecoder = new TextDecoder();
const termEncoder = new TextEncoder();

const FONT_MIN = 10;
const FONT_MAX = 22;

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
  if (res.status === 401) {
    window.location.href = "/login.html";
    throw new Error("unauthorized");
  }
  return res;
}

async function readErrorMessage(res) {
  const fallback = `HTTP ${res.status} ${res.statusText}`.trim();
  const text = await res.text().catch(() => "");
  if (!text) return fallback;
  try {
    const data = JSON.parse(text);
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return text;
  }
}

function wsUrl(path) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

function setTermMeta(text) {
  document.getElementById("termMeta").textContent = text || "";
}

function getTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function updateThemeToggleLabel() {
  const btn = document.getElementById("themeToggleBtn");
  if (!btn) return;
  btn.textContent = `Theme: ${getTheme() === "light" ? "Light" : "Dark"}`;
}

function setTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("theme", next);
  } catch {
    // ignore
  }
  updateThemeToggleLabel();
  applyTermTheme();
}

function toggleTheme() {
  setTheme(getTheme() === "light" ? "dark" : "light");
}

function getCssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function termTheme() {
  return {
    background: "rgba(0,0,0,0)",
    foreground: getCssVar("--term-fg", undefined),
    cursor: getCssVar("--term-cursor", undefined),
    selectionBackground: getCssVar("--term-selection", undefined),
  };
}

function applyTermTheme() {
  if (!term) return;
  try {
    term.options.theme = termTheme();
  } catch {
    // ignore
  }
}

function loadFontSize() {
  try {
    const raw = localStorage.getItem("terminalFontSize");
    const v = raw ? parseInt(raw, 10) : NaN;
    if (Number.isFinite(v)) return Math.max(FONT_MIN, Math.min(FONT_MAX, v));
  } catch {
    // ignore
  }
  return 14;
}

function saveFontSize(v) {
  try {
    localStorage.setItem("terminalFontSize", String(v));
  } catch {
    // ignore
  }
}

function ensureXterm() {
  if (term) return term;
  if (typeof window.Terminal !== "function") {
    setTermMeta("Terminal UI failed to load (xterm.js missing).");
    return null;
  }

  const container = document.getElementById("termContainer");
  container.innerHTML = "";

  term = new window.Terminal({
    cursorBlink: true,
    fontSize: loadFontSize(),
    scrollback: 5000,
    theme: termTheme(),
  });

  if (window.FitAddon?.FitAddon) {
    fitAddon = new window.FitAddon.FitAddon();
    term.loadAddon(fitAddon);
  }

  term.open(container);
  fitAddon?.fit?.();

  term.onData((data) => {
    if (!terminalSocket || terminalSocket.readyState !== WebSocket.OPEN) return;
    if (!data) return;
    terminalSocket.send(termEncoder.encode(data));
  });

  return term;
}

function updateButtons() {
  const connectBtn = document.getElementById("termConnectBtn");
  const disconnectBtn = document.getElementById("termDisconnectBtn");
  const projectSelect = document.getElementById("projectSelect");

  const canUse = terminalSupported && terminalEnabled;
  const hasProject = !!(projectSelect?.value || selectedProjectId);
  const connected = !!terminalSocket;

  connectBtn.disabled = !canUse || !hasProject || connected;
  disconnectBtn.disabled = !connected;
  projectSelect.disabled = !canUse;
}

function sendTerminalResize() {
  if (!term) return;
  fitAddon?.fit?.();
  if (!terminalSocket || terminalSocket.readyState !== WebSocket.OPEN) return;
  terminalSocket.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
}

function scheduleTerminalResize() {
  if (termResizeTimer) window.clearTimeout(termResizeTimer);
  termResizeTimer = window.setTimeout(() => {
    sendTerminalResize();
  }, 80);
}

function disconnectTerminal() {
  if (terminalSocket) {
    terminalSocket.close();
    terminalSocket = null;
  }
  updateButtons();
}

function connectTerminal(projectId) {
  if (!terminalSupported) {
    setTermMeta("Terminal not supported on this server. (On Windows, install pywinpty; on Linux, PTY must be available.)");
    return;
  }
  if (!terminalEnabled) {
    setTermMeta("Terminal disabled by server config.");
    return;
  }
  if (!projectId) {
    setTermMeta("Select a project to connect.");
    return;
  }

  selectedProjectId = projectId;
  disconnectTerminal();

  const t = ensureXterm();
  if (!t) return;
  t.clear();
  t.writeln?.(`Connecting to ${projectId}...`);
  setTermMeta(`Connecting | ${projectId}`);

  const socket = new WebSocket(wsUrl(`/ws/projects/${encodeURIComponent(projectId)}/terminal`));
  socket.binaryType = "arraybuffer";
  terminalSocket = socket;
  updateButtons();

  socket.addEventListener("open", () => {
    sendTerminalResize();
  });

  socket.addEventListener("message", (ev) => {
    if (!term) return;
    if (typeof ev.data === "string") {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "ready") {
          setTermMeta(`Connected | ${msg.path || projectId}`);
          return;
        }
        if (msg.type === "error") {
          setTermMeta(`Terminal error: ${msg.message || "unknown"}`);
          return;
        }
      } catch {
        // ignore
      }
      return;
    }

    try {
      const text = termDecoder.decode(new Uint8Array(ev.data));
      term.write(text);
    } catch {
      // ignore
    }
  });

  socket.addEventListener("close", (ev) => {
    if (terminalSocket === socket) {
      terminalSocket = null;
      updateButtons();
    }
    if (ev.code === 4401) {
      window.location.href = "/login.html";
      return;
    }
    setTermMeta(`Disconnected | code=${ev.code || 0}`);
  });

  socket.addEventListener("error", () => {
    setTermMeta("Terminal connection error.");
  });
}

async function loadTerminalCapability() {
  terminalEnabled = false;
  terminalSupported = false;
  updateButtons();

  try {
    const res = await apiFetch("/api/terminal");
    if (!res.ok) {
      setTermMeta(await readErrorMessage(res));
      return;
    }
    const data = await res.json();
    terminalSupported = !!data.supported;
    terminalEnabled = !!data.enabled;
  } catch (err) {
    setTermMeta(String(err));
    return;
  }

  if (!terminalSupported) {
    setTermMeta("Terminal not supported on this server. (On Windows, install pywinpty; on Linux, PTY must be available.)");
  } else if (!terminalEnabled) {
    setTermMeta("Terminal disabled by server. Set ENABLE_WEB_TERMINAL=true to enable.");
  } else if (selectedProjectId) {
    setTermMeta(`Ready | ${selectedProjectId}`);
  } else {
    setTermMeta("Ready | select a project then connect.");
  }
  updateButtons();
}

async function loadProjects() {
  const select = document.getElementById("projectSelect");
  select.innerHTML = `<option value="">Loading projects...</option>`;
  select.disabled = true;

  const res = await apiFetch("/api/projects");
  if (!res.ok) {
    setTermMeta(await readErrorMessage(res));
    select.innerHTML = `<option value="">(failed to load projects)</option>`;
    return;
  }
  const projects = await res.json();
  if (!projects.length) {
    select.innerHTML = `<option value="">(no projects found)</option>`;
    return;
  }

  const options = projects
    .map((p) => `<option value="${p.id}">${p.name} (${p.path})</option>`)
    .join("");
  select.innerHTML = `<option value="">Select a project</option>${options}`;

  if (selectedProjectId && projects.some((p) => p.id === selectedProjectId)) {
    select.value = selectedProjectId;
  }

  select.addEventListener("change", () => {
    selectedProjectId = select.value || null;
    updateButtons();
  });
}

function changeFontSize(delta) {
  const t = ensureXterm();
  if (!t) return;
  const current = Number(t.options.fontSize) || 14;
  const next = Math.max(FONT_MIN, Math.min(FONT_MAX, current + delta));
  t.options.fontSize = next;
  saveFontSize(next);
  scheduleTerminalResize();
}

async function logout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.href = "/login.html";
  }
}

function applyQueryParams() {
  const params = new URLSearchParams(window.location.search || "");
  const pid = (params.get("project") || "").trim();
  if (pid) selectedProjectId = pid;
  return params.get("connect") === "1";
}

document.addEventListener("DOMContentLoaded", async () => {
  const autoConnect = applyQueryParams();
  updateThemeToggleLabel();

  document.getElementById("themeToggleBtn")?.addEventListener("click", toggleTheme);
  document.getElementById("logoutBtn")?.addEventListener("click", logout);

  document.getElementById("termConnectBtn")?.addEventListener("click", () => {
    const select = document.getElementById("projectSelect");
    connectTerminal(select?.value || selectedProjectId);
  });
  document.getElementById("termDisconnectBtn")?.addEventListener("click", disconnectTerminal);

  document.getElementById("termFontDownBtn")?.addEventListener("click", () => changeFontSize(-1));
  document.getElementById("termFontUpBtn")?.addEventListener("click", () => changeFontSize(1));

  window.addEventListener("resize", scheduleTerminalResize);
  window.addEventListener("beforeunload", () => disconnectTerminal());

  await loadProjects();
  await loadTerminalCapability();

  const select = document.getElementById("projectSelect");
  if (selectedProjectId && select?.value !== selectedProjectId) {
    select.value = selectedProjectId;
  }
  updateButtons();

  if (autoConnect && selectedProjectId) {
    connectTerminal(selectedProjectId);
  }
});
