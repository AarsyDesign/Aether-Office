/**
 * AETHER OFFICE - 2D PIXEL ART GAME DASHBOARD & LIVE MULTI-AGENT BUILDER
 * Connects HTML5 2D Canvas Engine, Real-Time SSE Event Stream,
 * Real Multi-Agent Pipeline Execution, and Code Inspector with live Pytest.
 */

// =============================================================================
// 1. 8-BIT SOUND SYNTHESIZER (Web Audio API, Zero Dependencies)
// =============================================================================
class RetroSoundEngine {
  constructor() {
    this.ctx = null;
    this.muted = localStorage.getItem("aether_sfx_muted") === "true";
  }

  _init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  toggleMute() {
    this.muted = !this.muted;
    localStorage.setItem("aether_sfx_muted", this.muted);
    return !this.muted;
  }

  playClick() {
    if (this.muted) return;
    this._init();
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = "square";
    osc.frequency.setValueAtTime(440, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, this.ctx.currentTime + 0.05);
    gain.gain.setValueAtTime(0.1, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.05);
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.05);
  }

  playTick() {
    if (this.muted) return;
    this._init();
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(220, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(110, this.ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.15, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.08);
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.08);
  }

  playChime() {
    if (this.muted) return;
    this._init();
    if (!this.ctx) return;
    const notes = [987.77, 1318.51];
    notes.forEach((freq, idx) => {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = "square";
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime + idx * 0.08);
      gain.gain.setValueAtTime(0.1, this.ctx.currentTime + idx * 0.08);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + idx * 0.08 + 0.15);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(this.ctx.currentTime + idx * 0.08);
      osc.stop(this.ctx.currentTime + idx * 0.08 + 0.15);
    });
  }

  playFanfare() {
    if (this.muted) return;
    this._init();
    if (!this.ctx) return;
    const notes = [523.25, 659.25, 783.99, 1046.50];
    notes.forEach((freq, idx) => {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = "square";
      const start = this.ctx.currentTime + idx * 0.1;
      const dur = idx === 3 ? 0.35 : 0.1;
      osc.frequency.setValueAtTime(freq, start);
      gain.gain.setValueAtTime(0.12, start);
      gain.gain.exponentialRampToValueAtTime(0.01, start + dur);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(start);
      osc.stop(start + dur);
    });
  }
}

const sfx = new RetroSoundEngine();


// =============================================================================
// 2. PROCEDURAL PIXEL AVATAR GENERATOR (SVG)
// =============================================================================
function generatePixelAvatarSVG(name, role, department) {
  let hash = 0;
  const str = (name || "") + (role || "") + (department || "");
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  hash = Math.abs(hash);

  const skinColors = ["#fbcfe8", "#fde047", "#fed7aa", "#fcd34d", "#e2e8f0", "#d1d5db"];
  const hairColors = ["#1e293b", "#7c2d12", "#b45309", "#475569", "#0f172a", "#92400e"];
  const deptColors = {
    executive: "#d97706",
    product: "#8b5cf6",
    architecture: "#0284c7",
    engineering: "#2563eb",
    qa: "#ea580c",
    design: "#ec4899",
    marketing: "#10b981",
    hr: "#059669"
  };

  const skin = skinColors[hash % skinColors.length];
  const hair = hairColors[(hash >> 2) % hairColors.length];
  const shirt = deptColors[department] || "#3b82f6";

  return `
    <svg viewBox="0 0 16 16" width="100%" height="100%" shape-rendering="crispEdges">
      <rect width="16" height="16" fill="#0f172a" />
      <rect x="4" y="2" width="8" height="3" fill="${hair}" />
      <rect x="3" y="4" width="10" height="2" fill="${hair}" />
      <rect x="4" y="5" width="8" height="6" fill="${skin}" />
      <rect x="5" y="7" width="2" height="2" fill="#0f172a" />
      <rect x="9" y="7" width="2" height="2" fill="#0f172a" />
      <rect x="6" y="9" width="4" height="1" fill="#be123c" />
      <rect x="3" y="11" width="10" height="5" fill="${shirt}" />
    </svg>
  `;
}


// =============================================================================
// 3. MAIN DASHBOARD APPLICATION CONTROLLER
// =============================================================================
class AetherGameDashboard {
  constructor() {
    this.state = null;
    this.realProjects = [];
    this.activeProjectId = null;
    this.activeProjectFiles = {};
    this.currentInspectedFile = null;

    this.autoTickTimer = null;
    this.autoTickInterval = 4000;
    this.activeTab = "projects"; // default to Real Projects tab
    this.viewMode = "canvas";   // "canvas" | "grid"

    this.initElements();
    this.initTheme();
    this.initPixelCanvasWorld();
    this.attachEventListeners();
    this.initSSE();
    this.fetchState();
    this.fetchRealProjects();

    // Auto refresh projects list periodically
    setInterval(() => this.fetchRealProjects(), 8000);
  }

  initElements() {
    // Top HUD Elements
    this.elCycleCounter = document.getElementById("hud-cycle");
    this.elTreasuryVal = document.getElementById("hud-treasury");
    this.elStaffVal = document.getElementById("hud-staff");
    this.elRealApps = document.getElementById("hud-real-apps");
    this.elHealthVal = document.getElementById("hud-health");
    this.bridgeStatusText = document.getElementById("bridge-status-text");

    // Controls
    this.btnLaunchReal = document.getElementById("btn-launch-real-project");
    this.btnToggleView = document.getElementById("btn-toggle-view");
    this.btnTick = document.getElementById("btn-step-tick");
    this.btnAutoTick = document.getElementById("btn-auto-tick");
    this.btnSfxToggle = document.getElementById("btn-sfx-toggle");
    this.btnCrtToggle = document.getElementById("btn-crt-toggle");
    this.btnThemeToggle = document.getElementById("btn-theme-toggle");
    this.crtOverlay = document.querySelector(".crt-overlay");

    // Viewport Containers
    this.canvasWrapper = document.getElementById("canvas-wrapper");
    this.elFloorGrid = document.getElementById("floor-grid");

    // Sidebar & Tabs
    this.tabProjects = document.getElementById("tab-projects");
    this.tabQuests = document.getElementById("tab-quests");
    this.tabCron = document.getElementById("tab-cron");
    this.tabLogs = document.getElementById("tab-logs");
    this.countProjects = document.getElementById("count-projects");
    this.elCronsVal = document.getElementById("hud-crons");
    this.elSidebarContent = document.getElementById("sidebar-content");

    // Ticker
    this.elTickerText = document.getElementById("ticker-text");

    // Modals
    this.modalLaunchProject = document.getElementById("modal-launch-project");
    this.modalCodeInspector = document.getElementById("modal-code-inspector");
    this.modalDossier = document.getElementById("modal-dossier");
    this.modalWhiteboard = document.getElementById("modal-whiteboard");
    this.modalNewQuest = document.getElementById("modal-new-quest");

    // Code Inspector Inner Elements
    this.inspectProjId = document.getElementById("inspect-proj-id");
    this.inspectorFileList = document.getElementById("inspector-file-list");
    this.inspectActiveFile = document.getElementById("inspect-active-file");
    this.inspectCodeContent = document.getElementById("inspect-code-content");
    this.btnCopyCode = document.getElementById("btn-copy-code");
    this.btnRunPytest = document.getElementById("btn-run-pytest");
    this.testConsoleDrawer = document.getElementById("test-console-drawer");
    this.testConsoleOutput = document.getElementById("test-console-output");
    this.testVerdictBadge = document.getElementById("test-verdict-badge");
  }

  initTheme() {
    const saved = localStorage.getItem("aether_theme") || "light";
    this.setTheme(saved === "light");
  }

  setTheme(isLight) {
    document.body.classList.toggle("theme-light", isLight);
    document.documentElement.setAttribute("data-theme", isLight ? "light" : "dark");
    localStorage.setItem("aether_theme", isLight ? "light" : "dark");

    if (this.btnThemeToggle) {
      this.btnThemeToggle.innerHTML = isLight ? "💡 LAMPU: NYALA" : "🌙 LAMPU: REDUP";
      this.btnThemeToggle.classList.toggle("lamp-active", isLight);
      this.btnThemeToggle.classList.toggle("lamp-off", !isLight);
      this.btnThemeToggle.title = isLight ? "Matikan lampu kantor / Mode gelap" : "Nyalakan lampu kantor / Mode terang";
    }

    if (this.pixelWorld && typeof this.pixelWorld.setLightMode === "function") {
      this.pixelWorld.setLightMode(isLight);
    }
  }

  initPixelCanvasWorld() {
    if (window.PixelOfficeWorld) {
      this.pixelWorld = new window.PixelOfficeWorld("pixel-canvas", {
        sfx: sfx,
        onSelectEmployee: (emp) => this.openDossier(emp),
        onSelectWhiteboard: () => this.openWhiteboardModal(),
      });
      const isLight = document.body.classList.contains("theme-light");
      this.pixelWorld.setLightMode(isLight);
    }
  }

  attachEventListeners() {
    // Launch Real Project Modal
    this.btnLaunchReal.addEventListener("click", () => {
      sfx.playClick();
      this.modalLaunchProject.classList.remove("hidden");
    });

    // View Toggle (Canvas vs Grid)
    this.btnToggleView.addEventListener("click", () => {
      sfx.playClick();
      this.viewMode = this.viewMode === "canvas" ? "grid" : "canvas";
      if (this.viewMode === "canvas") {
        this.btnToggleView.textContent = "🎮 2D PIXEL VIEW";
        this.canvasWrapper.classList.remove("hidden");
        this.elFloorGrid.classList.add("hidden");
        if (this.pixelWorld) {
          setTimeout(() => this.pixelWorld.fitToContainer(), 50);
        }
      } else {
        this.btnToggleView.textContent = "📋 ROOM MATRIX";
        this.canvasWrapper.classList.add("hidden");
        this.elFloorGrid.classList.remove("hidden");
        this.renderFloorGrid();
      }
    });

    // Close / Dismiss Hint Pill
    const btnCloseHint = document.getElementById("btn-close-hint");
    const hintPill = document.getElementById("canvas-hint-pill");
    if (btnCloseHint && hintPill) {
      btnCloseHint.addEventListener("click", (e) => {
        e.stopPropagation();
        sfx.playClick();
        hintPill.style.display = "none";
      });
    }

    // Step Tick
    this.btnTick.addEventListener("click", () => {
      sfx.playClick();
      this.triggerTick();
    });

    // Auto-Tick Toggle
    this.btnAutoTick.addEventListener("click", () => {
      sfx.playClick();
      this.toggleAutoTick();
    });

    // SFX Mute Toggle
    this.btnSfxToggle.addEventListener("click", () => {
      const active = sfx.toggleMute();
      this.btnSfxToggle.textContent = active ? "🔊 SFX: ON" : "🔇 SFX: OFF";
      this.btnSfxToggle.classList.toggle("toggled-off", !active);
      if (active) sfx.playClick();
    });
    this.btnSfxToggle.textContent = !sfx.muted ? "🔊 SFX: ON" : "🔇 SFX: OFF";
    this.btnSfxToggle.classList.toggle("toggled-off", sfx.muted);

    // CRT Scanlines Toggle
    this.btnCrtToggle.addEventListener("click", () => {
      sfx.playClick();
      this.crtOverlay.classList.toggle("disabled");
      const isEnabled = !this.crtOverlay.classList.contains("disabled");
      this.btnCrtToggle.textContent = isEnabled ? "📺 CRT: ON" : "📺 CRT: OFF";
      this.btnCrtToggle.classList.toggle("toggled-off", !isEnabled);
    });

    // Lamp / Lighting Theme Toggle
    if (this.btnThemeToggle) {
      this.btnThemeToggle.addEventListener("click", () => {
        sfx.playClick();
        const isCurrentlyLight = document.body.classList.contains("theme-light");
        this.setTheme(!isCurrentlyLight);
      });
    }

    // Sidebar Tabs Navigation
    this.tabProjects.addEventListener("click", () => {
      sfx.playClick();
      this.activeTab = "projects";
      this.updateSidebarTabs();
      this.renderSidebar();
    });

    this.tabQuests.addEventListener("click", () => {
      sfx.playClick();
      this.activeTab = "quests";
      this.updateSidebarTabs();
      this.renderSidebar();
    });

    if (this.tabCron) {
      this.tabCron.addEventListener("click", () => {
        sfx.playClick();
        this.activeTab = "cron";
        this.updateSidebarTabs();
        this.renderSidebar();
      });
    }

    this.tabLogs.addEventListener("click", () => {
      sfx.playClick();
      this.activeTab = "logs";
      this.updateSidebarTabs();
      this.renderSidebar();
    });

    // Close Modals
    document.querySelectorAll(".modal-close, .modal-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        sfx.playClick();
        this.closeModals();
      });
    });

    // Launch Project Form & Template Auto-fill
    const projTemplateSelect = document.getElementById("proj-template");
    const projNameInput = document.getElementById("proj-name");
    const projBriefInput = document.getElementById("proj-brief");

    const templates = {
      todo: {
        name: "fast-todo-cli",
        brief: "Build a robust CLI Todo application in Python with SQLite persistence. Provide add, list, complete, and delete commands. Write test_core.py with pytest suites."
      },
      api: {
        name: "task-rest-api",
        brief: "Create a modular REST API in Python using FastAPI with in-memory storage and Pydantic validation schemas. Include full CRUD endpoints and unit tests in test_core.py."
      },
      calc: {
        name: "scientific-calc-cli",
        brief: "Build a mathematical expression parser and scientific CLI calculator in Python. Handle operator precedence, parentheses, and square root. Include comprehensive unit tests."
      },
      weather: {
        name: "weather-client-cli",
        brief: "Build a weather forecast utility in Python with local disk caching and data formatting. Include test_core.py verifying cache and query logic."
      }
    };

    projTemplateSelect.addEventListener("change", (e) => {
      const selected = templates[e.target.value];
      if (selected) {
        projNameInput.value = selected.name;
        projBriefInput.value = selected.brief;
      }
    });

    const projModeSelect = document.getElementById("proj-mode");
    const groupProjModel = document.getElementById("group-proj-model");
    if (projModeSelect && groupProjModel) {
      projModeSelect.addEventListener("change", () => {
        if (projModeSelect.value === "llm") {
          groupProjModel.style.display = "block";
          this.fetchRouterModels();
        } else {
          groupProjModel.style.display = "none";
        }
      });
    }

    const formLaunchProj = document.getElementById("form-launch-project");
    formLaunchProj.addEventListener("submit", (e) => {
      e.preventDefault();
      this.submitLaunchRealProject();
    });

    // Code Inspector Copy Code
    this.btnCopyCode.addEventListener("click", () => {
      const code = this.inspectCodeContent.textContent;
      navigator.clipboard.writeText(code).then(() => {
        sfx.playClick();
        const orig = this.btnCopyCode.textContent;
        this.btnCopyCode.textContent = "✓ COPIED!";
        setTimeout(() => (this.btnCopyCode.textContent = orig), 2000);
      });
    });

    // Code Inspector Run Pytest
    this.btnRunPytest.addEventListener("click", () => {
      this.executeLivePytest();
    });

    // Form New Quest / Objective
    const formQuest = document.getElementById("form-new-quest");
    if (formQuest) {
      formQuest.addEventListener("submit", (e) => {
        e.preventDefault();
        this.submitNewQuest();
      });
    }
  }

  updateSidebarTabs() {
    if (this.tabProjects) this.tabProjects.classList.toggle("active", this.activeTab === "projects");
    if (this.tabQuests) this.tabQuests.classList.toggle("active", this.activeTab === "quests");
    if (this.tabCron) this.tabCron.classList.toggle("active", this.activeTab === "cron");
    if (this.tabLogs) this.tabLogs.classList.toggle("active", this.activeTab === "logs");
  }

  closeModals() {
    document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
  }

  // ===========================================================================
  // REAL-TIME SERVER-SENT EVENTS (SSE)
  // ===========================================================================
  initSSE() {
    try {
      const evtSource = new EventSource("/api/events/stream");

      evtSource.addEventListener("connected", (e) => {
        console.log("Connected to Aether Office SSE Stream:", e.data);
      });

      evtSource.addEventListener("aether_event", (e) => {
        try {
          const data = JSON.parse(e.data);
          this.handleLiveEvent(data);
        } catch (err) {
          console.error("SSE parse error:", err);
        }
      });

      evtSource.onerror = (err) => {
        console.warn("SSE stream interrupted, reconnecting...", err);
      };
    } catch (e) {
      console.error("Failed to initialize SSE:", e);
    }
  }

  handleLiveEvent(evt) {
    const timeStr = new Date().toLocaleTimeString();
    const eventName = (evt.event_type || "").replace(/_/g, " ");
    const role = evt.agent_role ? `[${evt.agent_role}]` : "";
    const msg = `${timeStr} ⚡ ${eventName} ${role}`;

    // Add to ticker
    if (this.elTickerText) {
      this.elTickerText.textContent = `${msg}  ✦  ${this.elTickerText.textContent.slice(0, 300)}`;
    }

    // Forward to 2D Pixel Canvas World
    if (this.pixelWorld) {
      this.pixelWorld.handleEvent(evt);
    }

    // Audio cues
    if (evt.event_type.includes("COMPLETED")) {
      sfx.playChime();
      this.fetchRealProjects();
    } else if (evt.event_type.includes("STARTED")) {
      sfx.playTick();
    }

    this.fetchState();
  }

  // ===========================================================================
  // API CALLS: STATE, OBJECTIVES & REAL PROJECTS
  // ===========================================================================
  async fetchState() {
    try {
      const res = await fetch("/api/state");
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      this.state = data;
      this.render();
    } catch (err) {
      console.error("Failed to fetch state:", err);
    }
  }

  async fetchRealProjects() {
    try {
      const res = await fetch("/api/projects");
      if (!res.ok) return;
      const data = await res.json();
      this.realProjects = data.projects || [];
      if (this.countProjects) {
        this.countProjects.textContent = this.realProjects.length;
      }
      if (this.elRealApps) {
        this.elRealApps.textContent = `${this.realProjects.length} Built`;
      }
      if (this.activeTab === "projects") {
        this.renderSidebar();
      }
    } catch (err) {
      console.error("Failed to fetch real projects:", err);
    }
  }

  async fetchRouterModels() {
    try {
      const res = await fetch("/api/llm/router");
      if (!res.ok) return;
      const data = await res.json();
      const modelSelect = document.getElementById("proj-model");
      const routerLabel = document.getElementById("router-endpoint-label");
      if (routerLabel && data.endpoint) {
        const count = data.available_models ? data.available_models.length : 0;
        routerLabel.textContent = `${data.endpoint} (${count} Models Available)`;
      }
      if (modelSelect && Array.isArray(data.available_models) && data.available_models.length > 0) {
        modelSelect.innerHTML = data.available_models.map(m => {
          const isDef = m === data.default_model;
          return `<option value="${m}" ${isDef ? "selected" : ""}>${m} ${isDef ? "(Default)" : ""}</option>`;
        }).join("");
      }
    } catch (err) {
      console.warn("Could not load router models:", err);
    }
  }

  async submitLaunchRealProject() {
    const nameInput = document.getElementById("proj-name");
    const briefInput = document.getElementById("proj-brief");
    const modeSelect = document.getElementById("proj-mode");
    const modelSelect = document.getElementById("proj-model");

    const payload = {
      name: nameInput.value.trim(),
      brief: briefInput.value.trim(),
      mode: modeSelect.value,
      model: modeSelect.value === "llm" && modelSelect ? modelSelect.value : undefined,
    };

    if (!payload.brief) {
      alert("Please enter a project brief!");
      return;
    }

    try {
      sfx.playFanfare();
      this.closeModals();

      const res = await fetch("/api/projects/launch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (this.elTickerText) {
        const modelNote = payload.model ? ` [${payload.model}]` : "";
        this.elTickerText.textContent = `🚀 REAL BUILD STARTED: ${data.project.project_id} (Mode: ${payload.mode}${modelNote})  ✦  ${this.elTickerText.textContent}`;
      }

      this.activeTab = "projects";
      this.updateSidebarTabs();
      await this.fetchRealProjects();
    } catch (err) {
      alert(`Failed to launch real build: ${err.message}`);
    }
  }

  async openCodeInspector(projectId) {
    this.activeProjectId = projectId;
    this.inspectProjId.textContent = projectId;
    this.inspectorFileList.innerHTML = "<div style='color: #94a3b8; font-size: 0.7rem; padding: 6px;'>Loading files...</div>";
    this.inspectCodeContent.innerHTML = "<code>Loading source code...</code>";
    this.testConsoleDrawer.classList.add("hidden");

    this.modalCodeInspector.classList.remove("hidden");

    try {
      const res = await fetch(`/api/projects/${projectId}/files`);
      if (!res.ok) throw new Error("Could not load project files");
      const data = await res.json();
      this.activeProjectFiles = data.contents || {};

      this.renderInspectorFiles(data.files || []);
    } catch (err) {
      this.inspectCodeContent.textContent = `Error: ${err.message}`;
    }
  }

  renderInspectorFiles(files) {
    this.inspectorFileList.innerHTML = "";
    if (files.length === 0) {
      this.inspectorFileList.innerHTML = "<div style='color: #94a3b8; font-size: 0.7rem;'>No files yet</div>";
      return;
    }

    files.forEach((filename, idx) => {
      const item = document.createElement("div");
      item.className = `file-item ${idx === 0 ? "active" : ""}`;

      let icon = "📄";
      if (filename.endsWith(".py")) icon = "🐍";
      if (filename.endsWith(".md")) icon = "📝";
      if (filename.endsWith(".json")) icon = "⚙️";

      item.innerHTML = `<span>${icon}</span><span>${filename}</span>`;
      item.addEventListener("click", () => {
        sfx.playClick();
        document.querySelectorAll(".file-item").forEach(el => el.classList.remove("active"));
        item.classList.add("active");
        this.viewFileContent(filename);
      });
      this.inspectorFileList.appendChild(item);
    });

    // Default to first file (or core.py)
    const defFile = files.includes("core.py") ? "core.py" : files[0];
    this.viewFileContent(defFile);
  }

  viewFileContent(filename) {
    this.currentInspectedFile = filename;
    this.inspectActiveFile.textContent = filename;
    const content = this.activeProjectFiles[filename] || "";
    this.inspectCodeContent.textContent = content;
  }

  async executeLivePytest() {
    if (!this.activeProjectId) return;
    sfx.playClick();

    this.btnRunPytest.disabled = true;
    this.btnRunPytest.textContent = "⏳ RUNNING PYTEST...";
    this.testConsoleDrawer.classList.remove("hidden");
    this.testVerdictBadge.textContent = "TESTING...";
    this.testVerdictBadge.className = "badge warning";
    this.testConsoleOutput.textContent = `[Aether Testbench] Executing pytest projects/${this.activeProjectId}...\n`;

    try {
      const res = await fetch(`/api/projects/${this.activeProjectId}/run-tests`, {
        method: "POST",
      });
      const data = await res.json();

      if (data.success) {
        sfx.playFanfare();
        this.testVerdictBadge.textContent = `PASS (${data.duration}s)`;
        this.testVerdictBadge.className = "badge success";
      } else {
        this.testVerdictBadge.textContent = "FAIL";
        this.testVerdictBadge.className = "badge danger";
      }

      this.testConsoleOutput.textContent = data.stdout || data.stderr || data.error || "Execution completed with 0 logs.";
    } catch (err) {
      this.testVerdictBadge.textContent = "ERROR";
      this.testConsoleOutput.textContent = `Failed to run pytest: ${err.message}`;
    } finally {
      this.btnRunPytest.disabled = false;
      this.btnRunPytest.textContent = "▶️ RUN PYTEST LIVE";
    }
  }

  async triggerTick() {
    try {
      this.btnTick.disabled = true;
      this.btnTick.textContent = "⏳ TICKING...";
      await fetch("/api/scheduler/tick", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execute: true }),
      });
      sfx.playTick();
      await this.fetchState();
    } catch (err) {
      console.error("Scheduler tick error:", err);
    } finally {
      this.btnTick.disabled = false;
      this.btnTick.textContent = "⏩ STEP TICK";
    }
  }

  toggleAutoTick() {
    if (this.autoTickTimer) {
      clearInterval(this.autoTickTimer);
      this.autoTickTimer = null;
      this.btnAutoTick.textContent = "▶️ AUTO: OFF";
      this.btnAutoTick.classList.remove("action");
    } else {
      this.btnAutoTick.textContent = "⏸️ AUTO: ON";
      this.btnAutoTick.classList.add("action");
      this.autoTickTimer = setInterval(() => {
        this.triggerTick();
      }, this.autoTickInterval);
    }
  }

  openDossier(emp) {
    if (!emp) return;
    sfx.playClick();
    document.getElementById("dossier-name").textContent = emp.name;
    document.getElementById("dossier-title").textContent = emp.rpg_class || emp.title || emp.role_id;
    document.getElementById("dossier-dept").textContent = (emp.department_id || "OFFICE").toUpperCase();
    document.getElementById("stat-status").textContent = (emp.availability || "AVAILABLE").toUpperCase();
    document.getElementById("stat-task").textContent = emp.current_task ? emp.current_task.title : "Standby";
    document.getElementById("stat-caps").textContent = (emp.capabilities || []).join(", ") || "General specialist";

    const avatarSvg = generatePixelAvatarSVG(emp.name, emp.role_id, emp.department_id);
    document.getElementById("dossier-avatar").innerHTML = avatarSvg;

    this.modalDossier.classList.remove("hidden");
  }

  openWhiteboardModal() {
    sfx.playFanfare();
    this.modalWhiteboard.classList.remove("hidden");
  }

  async submitNewQuest() {
    const titleInput = document.getElementById("quest-title");
    const descInput = document.getElementById("quest-desc");
    const budgetInput = document.getElementById("quest-budget");
    const prioritySelect = document.getElementById("quest-priority");

    const payload = {
      title: titleInput ? titleInput.value.trim() : "",
      description: descInput ? descInput.value.trim() : "",
      budget: budgetInput ? (parseFloat(budgetInput.value) || 0.0) : 0.0,
      priority: prioritySelect ? prioritySelect.value : "normal",
    };

    if (!payload.title) {
      alert("Please provide an objective title!");
      return;
    }

    try {
      const res = await fetch("/api/objectives", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned status ${res.status}`);
      }
      const data = await res.json();
      sfx.playFanfare();
      this.closeModals();
      const formEl = document.getElementById("form-new-quest");
      if (formEl) formEl.reset();
      await this.fetchState();
    } catch (err) {
      alert(`Failed to create objective: ${err.message}`);
    }
  }

  async runObjectiveStep(objectiveId) {
    sfx.playClick();
    try {
      const res = await fetch(`/api/objectives/${objectiveId}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticks: 5 }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        console.error("Error running objective:", errData);
      }
      sfx.playTick();
      await this.fetchState();
    } catch (err) {
      console.error("Error running objective:", err);
    }
  }

  // ===========================================================================
  // UI RENDERING
  // ===========================================================================
  render() {
    if (!this.state) return;
    this.renderHUD();

    // Update 2D Pixel Canvas World
    if (this.pixelWorld) {
      this.pixelWorld.updateState(this.state);
    }

    // Update Room Grid (if visible)
    if (this.viewMode === "grid") {
      this.renderFloorGrid();
    }

    this.renderSidebar();
  }

  renderHUD() {
    const { hud } = this.state;
    if (!hud) return;

    this.elCycleCounter.textContent = `CYCLE #${String(hud.ticks || 0).padStart(4, "0")}`;
    this.elTreasuryVal.textContent = `$${hud.treasury_funds.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    this.elStaffVal.textContent = `${hud.total_workforce} (${hud.available_workforce} Avail / ${hud.busy_workforce} Busy)`;
    this.elHealthVal.textContent = `${hud.system_health}%`;

    if (this.bridgeStatusText && hud.pixel_bridge_target) {
      this.bridgeStatusText.textContent = `PIXELOFFICE: ${hud.pixel_bridge_target.split(' ')[0]}`;
    }
    if (this.elCronsVal) {
      this.elCronsVal.textContent = `${hud.active_crons || 0} Active`;
    }
  }

  renderSidebar() {
    if (!this.elSidebarContent) return;
    this.elSidebarContent.innerHTML = "";

    if (this.activeTab === "projects") {
      this.renderProjectsTab();
    } else if (this.activeTab === "quests") {
      this.renderQuestsTab();
    } else if (this.activeTab === "cron") {
      this.renderCronTab();
    } else {
      this.renderLogsTab();
    }
  }

  renderProjectsTab() {
    if (this.realProjects.length === 0) {
      this.elSidebarContent.innerHTML = `
        <div style="text-align: center; padding: 24px 12px; color: #94a3b8; font-size: 0.75rem;">
          <div style="font-size: 2rem; margin-bottom: 8px;">🚀</div>
          <div style="font-family: var(--font-retro); margin-bottom: 6px; color: #cbd5e1;">NO REAL BUILDS YET</div>
          <p style="margin-bottom: 14px;">Click the green button above to dispatch the AI dev team to write and test real Python code.</p>
          <button class="retro-btn action" id="btn-empty-launch">⚡ LAUNCH FIRST BUILD</button>
        </div>
      `;
      const btn = document.getElementById("btn-empty-launch");
      if (btn) btn.addEventListener("click", () => this.modalLaunchProject.classList.remove("hidden"));
      return;
    }

    this.realProjects.forEach((proj) => {
      const card = document.createElement("div");
      card.className = "real-project-item";

      const statusClass = (proj.status || "PENDING").toLowerCase();

      card.innerHTML = `
        <div class="real-project-title-row">
          <span class="real-project-name">${proj.name}</span>
          <span class="real-project-status ${statusClass}">${proj.status}</span>
        </div>
        <div class="real-project-meta">
          <div>📁 <strong>${proj.files_count} files</strong> generated on disk</div>
          <div style="color: #64748b; font-size: 0.6rem; margin-top: 2px;">${proj.id}</div>
          ${proj.brief_preview ? `<div style="margin-top: 4px; font-style: italic; color: #cbd5e1;">"${proj.brief_preview.slice(0, 80)}..."</div>` : ""}
        </div>
        <div class="real-project-actions">
          <button class="retro-btn small primary btn-inspect" data-pid="${proj.id}">
            📂 INSPECT CODE
          </button>
        </div>
      `;

      card.querySelector(".btn-inspect").addEventListener("click", () => {
        sfx.playClick();
        this.openCodeInspector(proj.id);
      });

      this.elSidebarContent.appendChild(card);
    });
  }

  renderQuestsTab() {
    const objectives = this.state.objectives || [];

    let html = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <span style="font-family: var(--font-retro); font-size: 0.65rem; color: #38bdf8;">🎯 OBJECTIVES (${objectives.length})</span>
        <button class="retro-btn primary btn-open-new-quest" style="font-size: 0.55rem; padding: 3px 8px;">+ NEW QUEST</button>
      </div>
    `;

    if (objectives.length === 0) {
      html += `
        <div style="text-align: center; color: var(--hud-muted); padding: 24px 10px;">
          <div style="font-size: 1.8rem; margin-bottom: 8px;">🎯</div>
          <p style="font-family: var(--font-retro); font-size: 0.7rem; margin-bottom: 8px;">NO ACTIVE QUESTS</p>
          <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 12px;">Launch a corporate campaign to direct your autonomous workforce!</p>
          <button class="retro-btn action btn-open-new-quest">⚡ LAUNCH FIRST QUEST</button>
        </div>
      `;
      this.elSidebarContent.innerHTML = html;
      this.elSidebarContent.querySelectorAll(".btn-open-new-quest").forEach((b) => {
        b.addEventListener("click", () => this.openNewQuestModal());
      });
      return;
    }

    this.elSidebarContent.innerHTML = html;
    this.elSidebarContent.querySelectorAll(".btn-open-new-quest").forEach((b) => {
      b.addEventListener("click", () => this.openNewQuestModal());
    });

    objectives.forEach((obj) => {
      const card = document.createElement("div");
      card.className = "quest-card";

      const statusClass = `status-${(obj.status || "PLANNING").toLowerCase().replace(/_/g, "-")}`;
      const qualityGrade = obj.quality ? `${obj.quality.grade} (${obj.quality.score}/100)` : (obj.quality_info ? obj.quality_info.grade : "Planning");

      let milestoneHtml = "";
      if (obj.milestones && obj.milestones.length > 0) {
        milestoneHtml = `
          <div class="milestones-pipeline" title="Milestones: ${obj.completed_milestones || 0}/${obj.total_milestones || obj.milestones.length} Done">
            ${obj.milestones.map((m) => `<div class="milestone-step ${m.status === 'COMPLETED' ? 'done' : m.status === 'IN_PROGRESS' ? 'active' : ''}" title="${m.title} [${m.status}]"></div>`).join("")}
          </div>
        `;
      }

      const isCompleted = obj.status === "COMPLETED";
      const btnLabel = isCompleted ? "✅ COMPLETED" : "⚡ EXECUTE STEP";
      const btnDisabled = isCompleted ? "disabled" : "";

      card.innerHTML = `
        <div class="quest-header">
          <div class="quest-title">${obj.title}</div>
          <span class="quest-status-badge ${statusClass}">${obj.status}</span>
        </div>
        <div class="quest-meta">
          <span class="tag-badge">Strategy: ${obj.strategy || "auto"}</span>
          <span class="tag-badge">Grade: ${qualityGrade}</span>
          <span class="tag-badge">Budget: $${(obj.spent || 0).toFixed(2)} / $${(obj.budget || 0).toFixed(2)}</span>
        </div>
        ${milestoneHtml}
        <div style="display: flex; justify-content: flex-end; margin-top: 6px;">
          <button class="retro-btn primary btn-run-quest" data-obj-id="${obj.id}" ${btnDisabled} style="padding: 4px 8px; font-size: 0.55rem; ${isCompleted ? 'opacity: 0.7; cursor: default; background: #065f46;' : ''}">
            ${btnLabel}
          </button>
        </div>
      `;

      if (!isCompleted) {
        card.querySelector(".btn-run-quest").addEventListener("click", (e) => {
          e.stopPropagation();
          this.runObjectiveStep(obj.id);
        });
      }

      this.elSidebarContent.appendChild(card);
    });
  }

  renderLogsTab() {
    const logs = this.state.recent_events || [];
    const container = document.createElement("div");
    container.style.display = "flex";
    container.style.flexDirection = "column";
    container.style.gap = "6px";

    logs.forEach(evt => {
      const row = document.createElement("div");
      row.style.background = "#0f172a";
      row.style.padding = "6px 8px";
      row.style.borderRadius = "4px";
      row.style.fontSize = "0.7rem";
      row.style.fontFamily = "var(--font-mono)";
      row.style.color = "#cbd5e1";
      row.innerHTML = `<span style="color: #38bdf8;">${evt.event_type}</span>: ${evt.message || evt.agent_role || ""}`;
      container.appendChild(row);
    });

    this.elSidebarContent.appendChild(container);
  }

  renderFloorGrid() {
    if (!this.state || !this.state.rooms || !this.elFloorGrid) return;
    this.elFloorGrid.innerHTML = "";

    this.state.rooms.forEach((room) => {
      const roomCard = document.createElement("div");
      roomCard.className = "office-room";
      roomCard.style.borderColor = room.theme || "#38bdf8";

      const header = document.createElement("div");
      header.className = "room-header";
      header.innerHTML = `
        <div class="room-title-group">
          <span class="room-icon">${room.icon}</span>
          <span class="room-title" style="color: ${room.theme}">${room.label || room.name}</span>
        </div>
        <span class="room-count">${room.employees.length} Staff</span>
      `;
      roomCard.appendChild(header);

      const interior = document.createElement("div");
      interior.className = "room-interior";

      room.employees.forEach((emp) => {
        const isBusy = emp.availability === "busy" || emp.live_state === "WORKING";
        const isOffline = emp.status === "inactive" || emp.availability === "offline";

        // Status bubble text & source detection
        let bubbleText = "☕ Break";
        let bubbleIcon = "☕";
        let sourceClass = "";
        let sourceTag = "";

        if (isBusy) {
          const task = emp.current_task;
          const source = task && task.source ? task.source.toLowerCase() : "";
          if (source === "hermes") {
            bubbleIcon = "⚡";
            sourceClass = "source-hermes";
            sourceTag = "HERMES";
          } else if (source === "antigravity") {
            bubbleIcon = "🌌";
            sourceClass = "source-antigravity";
            sourceTag = "ANTIGRAVITY";
          } else if (source === "vscode") {
            bubbleIcon = "💻";
            sourceClass = "source-vscode";
            sourceTag = "VS CODE";
          } else if (source === "cron") {
            bubbleIcon = "⏰";
            sourceClass = "source-cron";
            sourceTag = "CRON";
          } else if (source) {
            bubbleIcon = "🛰️";
            sourceClass = "source-custom";
            sourceTag = source.toUpperCase();
          } else {
            bubbleIcon = "💬";
            sourceClass = "source-default";
          }

          const rawText = task ? (task.raw_title || task.title || "Working") : "Working";
          bubbleText = rawText.length > 16 ? rawText.slice(0, 14) + "..." : rawText;
        } else if (isOffline) {
          bubbleText = "Offline";
          bubbleIcon = "💤";
        }

        const workstation = document.createElement("div");
        workstation.className = `workstation ${sourceClass ? "active-task " + sourceClass : ""}`;
        workstation.dataset.empId = emp.id;

        const avatarSvg = generatePixelAvatarSVG(emp.name, emp.role_id, emp.department_id);
        const badgeHtml = sourceTag ? `<span class="workstation-source-badge ${sourceClass}">${sourceTag}</span>` : "";

        workstation.innerHTML = `
          <div class="status-bubble ${sourceClass}">
            <span>${bubbleIcon}</span>
            <span>${bubbleText}</span>
          </div>
          <div class="avatar-container" id="avatar-${emp.id}">
            ${avatarSvg}
          </div>
          <div class="desk-monitor">
            <div class="screen-light ${isBusy ? "active " + sourceClass : isOffline ? "offline" : "idle"}"></div>
          </div>
          ${badgeHtml}
          <div class="emp-name" title="${emp.name}">${emp.name}</div>
          <div class="emp-role" title="${emp.rpg_class}">${emp.rpg_class}</div>
        `;
        workstation.addEventListener("click", () => this.openDossier(emp));
        interior.appendChild(workstation);
      });

      roomCard.appendChild(interior);
      this.elFloorGrid.appendChild(roomCard);
    });
  }
  renderCronTab() {
    const cronJobs = this.state.cron_jobs || [];
    const telemetry = this.state.telemetry_activities || [];

    let html = `
      <div class="cron-section-header">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-family: var(--font-retro); font-size: 0.65rem; color: #a855f7;">⏰ BACKGROUND CRONS</span>
          <span style="font-size: 0.7rem; color: var(--hud-muted);">${cronJobs.filter((j) => j.enabled).length} Enabled</span>
        </div>
      </div>
    `;

    if (cronJobs.length === 0) {
      html += `<div style="color: var(--hud-muted); padding: 10px; font-size: 0.75rem;">No background cron jobs registered.</div>`;
    } else {
      cronJobs.forEach((job) => {
        const isRunning = job.status === "RUNNING";
        const isFailed = job.status === "FAILED";
        const isSuccess = job.status === "SUCCESS";
        const statusColor = isRunning ? "#f59e0b" : isFailed ? "#ef4444" : isSuccess ? "#10b981" : "#94a3b8";
        const statusBadge = `<span class="cron-status-badge" style="background: ${statusColor}22; color: ${statusColor}; border: 1px solid ${statusColor}55;">${job.status}</span>`;
        const nextRunIn = Math.max(0, Math.round(job.next_run_in || 0));
        const lastRunText = job.last_run ? new Date(job.last_run).toLocaleTimeString() : "Never";

        html += `
          <div class="cron-card ${!job.enabled ? 'disabled-job' : ''}">
            <div class="cron-card-header">
              <div>
                <span class="cron-job-name">${job.name}</span>
                <span class="cron-role-tag">${job.target_role || 'Agent'}</span>
              </div>
              ${statusBadge}
            </div>
            <div class="cron-card-desc">${job.description || ''}</div>
            <div class="cron-card-meta">
              <span>⏱ Every ${job.interval_seconds}s</span>
              <span>⏳ Next in ${nextRunIn}s</span>
              <span>🕒 Last: ${lastRunText}</span>
            </div>
            ${job.last_result ? `<div class="cron-last-result" title="${job.last_result}">${job.last_result.slice(0, 75)}${job.last_result.length > 75 ? '...' : ''}</div>` : ''}
            <div class="cron-actions">
              <button class="retro-btn primary btn-run-cron" data-job-id="${job.id}" ${isRunning ? 'disabled' : ''}>
                ${isRunning ? '⏳ RUNNING...' : '▶ RUN NOW'}
              </button>
              <button class="retro-btn secondary btn-toggle-cron" data-job-id="${job.id}">
                ${job.enabled ? '⏸ PAUSE' : '▶ ENABLE'}
              </button>
            </div>
          </div>
        `;
      });
    }

    // Telemetry Feed Section
    html += `
      <div class="cron-section-header" style="margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-family: var(--font-retro); font-size: 0.65rem; color: #38bdf8;">📡 AI AGENT TELEMETRY</span>
          <span style="font-size: 0.7rem; color: var(--hud-muted);">Live Hub</span>
        </div>
        <p style="font-size: 0.7rem; color: #94a3b8; margin-bottom: 8px;">Real AI activities streamed from Hermes, Antigravity, VS Code & Crons.</p>
      </div>
    `;

    if (telemetry.length === 0) {
      html += `
        <div style="background: #090d18; border: 1px dashed var(--border-color); border-radius: 6px; padding: 14px; text-align: center; color: var(--hud-muted); font-size: 0.75rem;">
          <div style="font-size: 1.2rem; margin-bottom: 4px;">🛰️</div>
          <div>Awaiting agent telemetry broadcast...</div>
          <div style="margin-top: 6px; font-size: 0.65rem; color: #64748b; font-family: var(--font-mono);">aether track --role developer "Task Name"</div>
        </div>
      `;
    } else {
      telemetry.forEach((act) => {
        const isWorking = act.status === "WORKING";
        const isCompleted = act.status === "COMPLETED";
        const isFailed = act.status === "FAILED";
        const statusColor = isWorking ? "#38bdf8" : isCompleted ? "#10b981" : "#ef4444";
        const source = (act.source || "agent").toLowerCase();
        const time = act.created_at ? act.created_at.split("T")[1]?.slice(0, 8) : "--:--:--";

        html += `
          <div class="telemetry-card ${source}">
            <div class="telemetry-header">
              <div class="telemetry-source-tag ${source}">[${source.toUpperCase()}]</div>
              <span class="telemetry-status" style="color: ${statusColor}; font-weight: bold; font-size: 0.65rem;">${act.status}</span>
            </div>
            <div class="telemetry-task-title">${act.task_title || act.task_name || 'Active Task'}</div>
            <div class="telemetry-meta">
              <span>👤 ${act.role || act.role_hint || 'agent'} (${act.employee_name || act.employee_id || act.assigned_employee_id || 'unassigned'})</span>
              <span>🕒 ${time}</span>
            </div>
            ${(act.details || act.output) ? `<div class="telemetry-output">${(act.details || act.output).slice(0, 100)}${(act.details || act.output).length > 100 ? '...' : ''}</div>` : ''}
          </div>
        `;
      });
    }

    this.elSidebarContent.innerHTML = html;

    // Attach click handlers
    this.elSidebarContent.querySelectorAll(".btn-run-cron").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const jobId = btn.dataset.jobId;
        if (jobId) this.runCronJob(jobId);
      });
    });

    this.elSidebarContent.querySelectorAll(".btn-toggle-cron").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const jobId = btn.dataset.jobId;
        if (jobId) this.toggleCronJob(jobId);
      });
    });
  }

  async runCronJob(jobId) {
    try {
      sfx.playClick();
      const btn = this.elSidebarContent.querySelector(`.btn-run-cron[data-job-id="${jobId}"]`);
      if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ STARTING...";
      }
      const res = await fetch(`/api/cron/jobs/${jobId}/run`, { method: "POST" });
      const data = await res.json();
      sfx.playChime();
      await this.fetchState();
    } catch (err) {
      console.error("Failed to run cron job:", err);
    }
  }

  async toggleCronJob(jobId) {
    try {
      sfx.playClick();
      const res = await fetch(`/api/cron/jobs/${jobId}/toggle`, { method: "POST" });
      const data = await res.json();
      await this.fetchState();
    } catch (err) {
      console.error("Failed to toggle cron job:", err);
    }
  }

  openNewQuestModal() {
    this.modalNewQuest.classList.remove("hidden");
    const titleInput = document.getElementById("quest-title");
    if (titleInput) titleInput.focus();
  }
}

// Instantiate on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.aetherDashboard = new AetherGameDashboard();
});
