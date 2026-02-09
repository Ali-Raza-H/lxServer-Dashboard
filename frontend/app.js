let selectedProjectId = null;
let logsSocket = null;

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
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
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

async function loadSystem() {
  const res = await apiFetch("/api/system");
  if (!res.ok) {
    document.getElementById("sysSummary").textContent = await readErrorMessage(res);
    return;
  }
  const data = await res.json();
  const sys = document.getElementById("sysSummary");
  const load = data.load_avg?.length ? data.load_avg.map((x) => x.toFixed(2)).join(", ") : "n/a";
  sys.textContent = `${data.hostname} • CPU ${data.cpu_percent.toFixed(0)}% • Load ${load} • RAM ${fmtBytes(data.mem_used)}/${fmtBytes(
    data.mem_total
  )} • Disk ${fmtBytes(data.disk_used)}/${fmtBytes(data.disk_total)}`;
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
      await runAction(pid, action);
    });
  });
}

async function runAction(projectId, action) {
  setOutput(`${action} • ${projectId}`, "Running…");
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    if (!res.ok) {
      setOutput(`error • ${res.status}`, await readErrorMessage(res));
      return;
    }
    const data = await res.json();
    const meta = `exit=${data.exit_code} • ${data.duration_ms}ms`;
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
    setLogs(`error • ${res.status}`, await readErrorMessage(res));
    return;
  }
  const data = await res.json();
  setLogs(`Tail • ${pid}`, data.lines.join("\n"));
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
  setLogs(`Live • ${pid}`, "");

  const socket = new WebSocket(wsUrl(`/ws/projects/${encodeURIComponent(pid)}/logs`));
  logsSocket = socket;
  document.getElementById("logsStopBtn").disabled = false;

  socket.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "init") {
        setLogs(`Live • ${pid}`, (msg.lines || []).join("\n"));
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
  document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadSystem();
    await loadProjects();
  });
  document.getElementById("logoutBtn").addEventListener("click", logout);

  document.getElementById("logsTailBtn").addEventListener("click", tailLogs);
  document.getElementById("logsLiveBtn").addEventListener("click", startLiveLogs);
  document.getElementById("logsStopBtn").addEventListener("click", stopLogs);

  await loadSystem();
  await loadProjects();

  setInterval(() => {
    loadSystem().catch(() => {});
  }, 5000);
});
