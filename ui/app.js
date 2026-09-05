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
    this.crtOverlay = document.querySelector(".crt-overlay");

    // Viewport Containers
    this.canvasWrapper = document.getElementById("canvas-wrapper");
    this.elFloorGrid = document.getElementById("floor-grid");

    // Sidebar & Tabs
    this.tabProjects = document.getElementById("tab-projects");
    this.tabQuests = document.getElementById("tab-quests");
    this.tabLogs = document.getElementById("tab-logs");
    this.countProjects = document.getElementById("count-projects");
    this.elSidebarContent = document.getElementById("sidebar-content");
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

  initPixelCanvasWorld() {
    if (window.PixelOfficeWorld) {
      this.pixelWorld = new window.PixelOfficeWorld("pixel-canvas", {
        sfx: sfx,
        onSelectEmployee: (emp) => this.openDossier(emp),
        onSelectWhiteboard: () => this.openWhiteboardModal(),
      });
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
      } else {
        this.btnToggleView.textContent = "📋 ROOM MATRIX";
        this.canvasWrapper.classList.add("hidden");
        this.elFloorGrid.classList.remove("hidden");
        this.renderFloorGrid();
      }
    });

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
  }

  updateSidebarTabs() {
    this.tabProjects.classList.toggle("active", this.activeTab === "projects");
    this.tabQuests.classList.toggle("active", this.activeTab === "quests");
    this.tabLogs.classList.toggle("active", this.activeTab === "logs");
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

  async submitLaunchRealProject() {
    const nameInput = document.getElementById("proj-name");
    const briefInput = document.getElementById("proj-brief");
    const modeSelect = document.getElementById("proj-mode");

    const payload = {
      name: nameInput.value.trim(),
      brief: briefInput.value.trim(),
      mode: modeSelect.value,
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
        this.elTickerText.textContent = `🚀 REAL BUILD STARTED: ${data.project.project_id} (Mode: ${payload.mode})  ✦  ${this.elTickerText.textContent}`;
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
  }

  renderSidebar() {
    if (!this.elSidebarContent) return;
    this.elSidebarContent.innerHTML = "";

    if (this.activeTab === "projects") {
      this.renderProjectsTab();
    } else if (this.activeTab === "quests") {
      this.renderQuestsTab();
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
    if (objectives.length === 0) {
      this.elSidebarContent.innerHTML = `
        <div style="text-align: center; padding: 24px; color: #94a3b8; font-size: 0.75rem;">
          <div style="font-size: 1.8rem; margin-bottom: 8px;">🎯</div>
          <div>No business objectives active.</div>
        </div>
      `;
      return;
    }

    objectives.forEach(obj => {
      const item = document.createElement("div");
      item.className = "real-project-item";
      item.innerHTML = `
        <div class="real-project-title-row">
          <span class="real-project-name">${obj.title}</span>
          <span class="real-project-status completed">${obj.status}</span>
        </div>
        <div class="real-project-meta">
          <span>Grade: <strong>${obj.quality_info ? obj.quality_info.grade : "A"}</strong></span>
          <span>Milestones: ${obj.milestones.length}</span>
        </div>
      `;
      this.elSidebarContent.appendChild(item);
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
        const workstation = document.createElement("div");
        workstation.className = "workstation";
        const avatarSvg = generatePixelAvatarSVG(emp.name, emp.role_id, emp.department_id);

        workstation.innerHTML = `
          <div class="status-bubble"><span>☕</span><span>${emp.live_state || "Standby"}</span></div>
          <div class="avatar-container">${avatarSvg}</div>
          <div class="emp-name">${emp.name}</div>
          <div class="emp-role">${emp.rpg_class}</div>
        `;
        workstation.addEventListener("click", () => this.openDossier(emp));
        interior.appendChild(workstation);
      });

      roomCard.appendChild(interior);
      this.elFloorGrid.appendChild(roomCard);
    });
  }
}

// Instantiate on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.aetherDashboard = new AetherGameDashboard();
});
