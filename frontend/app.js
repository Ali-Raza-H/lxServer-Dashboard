let selectedProjectId = null;
let logsSocket = null;

const HISTORY_MAX = 60;
const history = {
  cpu: [],
  mem: [],
  disk: [],
  load: [],
};

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

function fmtBytes(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Number(bytes) || 0;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function pct(numerator, denominator) {
  const num = Number(numerator) || 0;
  const den = Number(denominator) || 0;
  if (den <= 0) return 0;
  return (num / den) * 100;
}

function setOutput(meta, text) {
  document.getElementById("outputMeta").textContent = meta || "";
  document.getElementById("outputPre").textContent = text || "";
}

function setLogs(meta, text) {
  document.getElementById("logsMeta").textContent = meta || "";
  document.getElementById("logsPre").textContent = text || "";
}

function appendLogLine(line) {
  const pre = document.getElementById("logsPre");
  pre.textContent += (pre.textContent ? "\n" : "") + line;
  pre.scrollTop = pre.scrollHeight;
}

function wsUrl(path) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
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
}

function toggleTheme() {
  setTheme(getTheme() === "light" ? "dark" : "light");
}

function pushHistory(arr, value) {
  arr.push(value);
  if (arr.length > HISTORY_MAX) arr.splice(0, arr.length - HISTORY_MAX);
}

function sparkPath(values, { min = 0, max = 100 } = {}) {
  if (!values?.length) return "";
  const w = 100;
  const h = 24;
  const n = values.length;
  const safeMin = Number.isFinite(min) ? min : 0;
  let safeMax = Number.isFinite(max) ? max : safeMin + 1;
  if (safeMax <= safeMin) safeMax = safeMin + 1;

  const dx = n > 1 ? w / (n - 1) : 0;
  let d = "";
  for (let i = 0; i < n; i += 1) {
    const v = Number(values[i]);
    const t = Number.isFinite(v) ? (v - safeMin) / (safeMax - safeMin) : 0;
    const clamped = Math.max(0, Math.min(1, t));
    const x = i * dx;
    const y = (h - 1) - clamped * (h - 2);
    d += `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)} `;
  }
  return d.trim();
}

function renderSpark(pathId, values, opts) {
  const path = document.getElementById(pathId);
  if (!path) return;
  path.setAttribute("d", sparkPath(values, opts));
}

function updatePerformance(data) {
  const cpu = Number(data?.cpu_percent);
  const memUsed = Number(data?.mem_used) || 0;
  const memTotal = Number(data?.mem_total) || 0;
  const diskUsed = Number(data?.disk_used) || 0;
  const diskTotal = Number(data?.disk_total) || 0;
  const load1 = Number(data?.load_avg?.[0]) || 0;

  const cpuPct = Number.isFinite(cpu) ? Math.max(0, Math.min(100, cpu)) : 0;
  const memPct = Math.max(0, Math.min(100, pct(memUsed, memTotal)));
  const diskPct = Math.max(0, Math.min(100, pct(diskUsed, diskTotal)));

  pushHistory(history.cpu, cpuPct);
  pushHistory(history.mem, memPct);
  pushHistory(history.disk, diskPct);
  pushHistory(history.load, Math.max(0, load1));

  document.getElementById("metricCpuValue").textContent = `${cpuPct.toFixed(0)}%`;
  document.getElementById("metricMemValue").textContent = `${memPct.toFixed(0)}%`;
  document.getElementById("metricMemSub").textContent = `${fmtBytes(memUsed)}/${fmtBytes(memTotal)}`;
  document.getElementById("metricDiskValue").textContent = `${diskPct.toFixed(0)}%`;
  document.getElementById("metricDiskSub").textContent = `${fmtBytes(diskUsed)}/${fmtBytes(diskTotal)}`;
  document.getElementById("metricLoadValue").textContent = load1.toFixed(2);

  renderSpark("sparkCpu", history.cpu, { min: 0, max: 100 });
  renderSpark("sparkMem", history.mem, { min: 0, max: 100 });
  renderSpark("sparkDisk", history.disk, { min: 0, max: 100 });
  const loadMax = Math.max(1, ...history.load);
  renderSpark("sparkLoad", history.load, { min: 0, max: loadMax });

  const perfMeta = document.getElementById("perfMeta");
  const t = data?.local_time_iso ? new Date(String(data.local_time_iso)) : new Date();
  if (!Number.isNaN(t.getTime())) {
    perfMeta.textContent = `Updated ${t.toLocaleTimeString()}`;
  } else {
    perfMeta.textContent = "";
  }
}

async function loadSystem() {
  const res = await apiFetch("/api/system");
  if (!res.ok) {
    document.getElementById("sysSummary").textContent = await readErrorMessage(res);
    document.getElementById("perfMeta").textContent = "";
    return;
  }

  const data = await res.json();
  const hostname = data.hostname || "host";
  const cpu = Number(data.cpu_percent) || 0;
  const load1 = Number(data?.load_avg?.[0]) || 0;
  const memUsed = Number(data.mem_used) || 0;
  const memTotal = Number(data.mem_total) || 0;
  const diskUsed = Number(data.disk_used) || 0;
  const diskTotal = Number(data.disk_total) || 0;

  document.getElementById("sysSummary").textContent =
    `${hostname} | CPU ${cpu.toFixed(0)}% | Load ${load1.toFixed(2)} | ` +
    `RAM ${fmtBytes(memUsed)}/${fmtBytes(memTotal)} | Disk ${fmtBytes(diskUsed)}/${fmtBytes(diskTotal)}`;

  updatePerformance(data);
}

function projectCard(project) {
  const dirty = project.git_dirty ? `<span class="pill pill--warn" title="Git dirty">dirty</span>` : "";
  const git = project.is_git
    ? `<span class="pill">${project.git_branch || "git"}</span>${dirty}`
    : `<span class="pill pill--muted">no git</span>`;
  const typ = `<span class="pill pill--muted">${project.detected_type}</span>`;

  const disabledGit = project.is_git ? "" : "disabled";

  return `
    <div class="card project-card" data-project-id="${project.id}">
      <div class="project-card__head">
        <div class="project-title">${project.name}</div>
        <div class="project-meta">${git}${typ}</div>
      </div>
      <div class="muted project-path">${project.path}</div>
      <div class="muted project-modified">Last modified: ${new Date(project.last_modified).toLocaleString()}</div>
      <div class="btn-row">
        <button class="btn btn--small" data-action="git_status" ${disabledGit}>Git Status</button>
        <button class="btn btn--small" data-action="git_pull" ${disabledGit}>Git Pull</button>
        <button class="btn btn--small" data-action="list_files">Files</button>
        <button class="btn btn--small" data-action="view_logs">View Logs</button>
        <button class="btn btn--small" data-action="terminal">Terminal</button>
      </div>
    </div>
  `;
}

async function loadProjects() {
  const res = await apiFetch("/api/projects");
  if (!res.ok) {
    document.getElementById("projectsMeta").textContent = await readErrorMessage(res);
    document.getElementById("projectsGrid").innerHTML = "";
    return;
  }
  const projects = await res.json();
  const grid = document.getElementById("projectsGrid");
  grid.innerHTML = projects.map(projectCard).join("");
  document.getElementById("projectsMeta").textContent = `${projects.length} found`;

  grid.querySelectorAll(".project-card").forEach((card) => {
    card.addEventListener("click", async (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      const action = btn.dataset.action;
      const pid = card.dataset.projectId;
      selectedProjectId = pid;

      if (action === "view_logs") {
        await tailLogs();
        return;
      }
      if (action === "terminal") {
        window.location.href = `/terminal?project=${encodeURIComponent(pid)}&connect=1`;
        return;
      }
      await runAction(pid, action);
    });
  });
}

async function runAction(projectId, action) {
  setOutput(`${action} | ${projectId}`, "Running...");
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    if (!res.ok) {
      setOutput(`error | ${res.status}`, await readErrorMessage(res));
      return;
    }
    const data = await res.json();
    const meta = `exit=${data.exit_code} | ${data.duration_ms}ms`;
    let out = "";
    if (data.stdout) out += data.stdout.trimEnd();
    if (data.stderr) out += (out ? "\n\n" : "") + data.stderr.trimEnd();
    setOutput(meta, out || "(no output)");
  } catch (err) {
    setOutput("error", String(err));
  }
}

async function tailLogs() {
  if (!selectedProjectId) {
    setLogs("No project selected.", "");
    return;
  }
  stopLogs();
  const pid = selectedProjectId;
  const res = await apiFetch(`/api/projects/${encodeURIComponent(pid)}/logs?lines=200`);
  if (!res.ok) {
    setLogs(`error | ${res.status}`, await readErrorMessage(res));
    return;
  }
  const data = await res.json();
  setLogs(`Tail | ${pid}`, data.lines.join("\n"));
}

function stopLogs() {
  if (logsSocket) {
    logsSocket.close();
    logsSocket = null;
  }
  document.getElementById("logsStopBtn").disabled = true;
}

function startLiveLogs() {
  if (!selectedProjectId) {
    setLogs("No project selected.", "");
    return;
  }
  stopLogs();
  const pid = selectedProjectId;
  setLogs(`Live | ${pid}`, "");

  const socket = new WebSocket(wsUrl(`/ws/projects/${encodeURIComponent(pid)}/logs`));
  logsSocket = socket;
  document.getElementById("logsStopBtn").disabled = false;

  socket.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "init") {
        setLogs(`Live | ${pid}`, (msg.lines || []).join("\n"));
        return;
      }
      if (msg.type === "line") {
        appendLogLine(msg.line);
      }
    } catch {
      // ignore
    }
  });

  socket.addEventListener("close", () => {
    if (logsSocket === socket) {
      logsSocket = null;
      document.getElementById("logsStopBtn").disabled = true;
    }
  });
}

async function logout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.href = "/login.html";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("themeToggleBtn")?.addEventListener("click", toggleTheme);
  updateThemeToggleLabel();

  document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadSystem();
    await loadProjects();
  });
  document.getElementById("logoutBtn").addEventListener("click", logout);

  document.getElementById("logsTailBtn").addEventListener("click", tailLogs);
  document.getElementById("logsLiveBtn").addEventListener("click", startLiveLogs);
  document.getElementById("logsStopBtn").addEventListener("click", stopLogs);

  window.addEventListener("beforeunload", () => stopLogs());

  await loadSystem();
  await loadProjects();

  setInterval(() => {
    loadSystem().catch(() => {});
  }, 5000);
});

