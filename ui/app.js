/**
 * AETHER OFFICE - RETRO TYCOON GAME DASHBOARD ENGINE
 * Interactive virtual office simulation, procedural pixel sprites, Web Audio SFX, and real-time SSE.
 */

// =============================================================================
// 1. 8-BIT SOUND SYNTHESIZER (Pure Web Audio API, Zero Dependencies)
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
    // 8-bit coin pickup arpeggio (B5 -> E6)
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
    // Victory fanfare (C5 -> G5 -> C6)
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
// 2. PROCEDURAL PIXEL ART AVATAR GENERATOR (SVG)
// =============================================================================
function generatePixelAvatarSVG(name, role, department) {
  // Simple deterministic hash
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
  const hasGlasses = (hash % 3 === 0);

  return `
    <svg viewBox="0 0 16 16" width="100%" height="100%" shape-rendering="crispEdges">
      <!-- Background -->
      <rect width="16" height="16" fill="#0f172a" />
      
      <!-- Hair Top -->
      <rect x="4" y="2" width="8" height="3" fill="${hair}" />
      <rect x="3" y="3" width="10" height="2" fill="${hair}" />
      
      <!-- Head / Face -->
      <rect x="4" y="4" width="8" height="6" fill="${skin}" />
      
      <!-- Eyes -->
      <rect x="5" y="6" width="2" height="1" fill="#0f172a" />
      <rect x="9" y="6" width="2" height="1" fill="#0f172a" />
      
      <!-- Glasses (optional) -->
      ${hasGlasses ? `
        <rect x="4" y="5" width="4" height="3" fill="none" stroke="#38bdf8" stroke-width="0.75" />
        <rect x="8" y="5" width="4" height="3" fill="none" stroke="#38bdf8" stroke-width="0.75" />
        <line x1="7" y1="6" x2="9" y2="6" stroke="#38bdf8" stroke-width="0.75" />
      ` : ''}
      
      <!-- Mouth -->
      <rect x="7" y="8" width="2" height="1" fill="#9f1239" />
      
      <!-- Shoulders / Shirt -->
      <rect x="2" y="10" width="12" height="6" fill="${shirt}" />
      
      <!-- Collar / Tie -->
      <polygon points="8,10 6,13 10,13" fill="#f8fafc" />
      <rect x="7.5" y="11" width="1" height="4" fill="#0f172a" />
    </svg>
  `;
}


// =============================================================================
// 3. GAME STATE & APPLICATION CONTROLLER
// =============================================================================
class AetherGameDashboard {
  constructor() {
    this.state = null;
    this.autoTickTimer = null;
    this.autoTickInterval = 4000;
    this.selectedEmployee = null;
    this.activeTab = "quests";

    this.initElements();
    this.attachEventListeners();
    this.initSSE();
    this.fetchState();
  }

  initElements() {
    // Top HUD
    this.elCycleCounter = document.getElementById("hud-cycle");
    this.elTreasuryVal = document.getElementById("hud-treasury");
    this.elStaffVal = document.getElementById("hud-staff");
    this.elQuestsVal = document.getElementById("hud-quests");
    this.elHealthVal = document.getElementById("hud-health");

    // Controls
    this.btnTick = document.getElementById("btn-step-tick");
    this.btnAutoTick = document.getElementById("btn-auto-tick");
    this.btnNewQuest = document.getElementById("btn-new-quest");
    this.btnSfxToggle = document.getElementById("btn-sfx-toggle");
    this.btnCrtToggle = document.getElementById("btn-crt-toggle");
    this.crtOverlay = document.querySelector(".crt-overlay");

    // Floor & Sidebar
    this.elFloorGrid = document.getElementById("floor-grid");
    this.elSidebarContent = document.getElementById("sidebar-content");
    this.tabQuests = document.getElementById("tab-quests");
    this.tabLogs = document.getElementById("tab-logs");
    this.tabCron = document.getElementById("tab-cron");
    this.elCronsVal = document.getElementById("hud-crons");

    // Ticker
    this.elTickerText = document.getElementById("ticker-text");

    // Modals
    this.modalDossier = document.getElementById("modal-dossier");
    this.modalNewQuest = document.getElementById("modal-new-quest");
  }

  attachEventListeners() {
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

    // New Quest
    this.btnNewQuest.addEventListener("click", () => {
      sfx.playClick();
      this.openNewQuestModal();
    });

    // SFX Mute Toggle
    this.btnSfxToggle.addEventListener("click", () => {
      const active = sfx.toggleMute();
      this.btnSfxToggle.textContent = active ? "🔊 SFX: ON" : "🔇 SFX: OFF";
      this.btnSfxToggle.classList.toggle("toggled-off", !active);
      if (active) sfx.playClick();
    });
    // Set initial button label
    this.btnSfxToggle.textContent = !sfx.muted ? "🔊 SFX: ON" : "🔇 SFX: OFF";
    this.btnSfxToggle.classList.toggle("toggled-off", sfx.muted);

    // CRT Toggle
    this.btnCrtToggle.addEventListener("click", () => {
      sfx.playClick();
      this.crtOverlay.classList.toggle("disabled");
      const isEnabled = !this.crtOverlay.classList.contains("disabled");
      this.btnCrtToggle.textContent = isEnabled ? "📺 CRT: ON" : "📺 CRT: OFF";
      this.btnCrtToggle.classList.toggle("toggled-off", !isEnabled);
    });

    // Sidebar Tabs
    this.tabQuests.addEventListener("click", () => {
      sfx.playClick();
      this.activeTab = "quests";
      this.tabQuests.classList.add("active");
      this.tabLogs.classList.remove("active");
      if (this.tabCron) this.tabCron.classList.remove("active");
      this.renderSidebar();
    });

    this.tabLogs.addEventListener("click", () => {
      sfx.playClick();
      this.activeTab = "logs";
      this.tabLogs.classList.add("active");
      this.tabQuests.classList.remove("active");
      if (this.tabCron) this.tabCron.classList.remove("active");
      this.renderSidebar();
    });

    if (this.tabCron) {
      this.tabCron.addEventListener("click", () => {
        sfx.playClick();
        this.activeTab = "cron";
        this.tabCron.classList.add("active");
        this.tabQuests.classList.remove("active");
        this.tabLogs.classList.remove("active");
        this.renderSidebar();
      });
    }

    // Close Modals
    document.querySelectorAll(".modal-close, .modal-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        sfx.playClick();
        this.closeModals();
      });
    });

    // New Quest Form Submit
    const formQuest = document.getElementById("form-new-quest");
    if (formQuest) {
      formQuest.addEventListener("submit", (e) => {
        e.preventDefault();
        this.submitNewQuest();
      });
    }
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
        console.warn("SSE connection interrupted, retrying...", err);
      };
    } catch (e) {
      console.error("Failed to initialize SSE:", e);
    }
  }

  handleLiveEvent(evt) {
    // Add to ticker
    const timeStr = new Date().toLocaleTimeString();
    const eventName = evt.event_type.replace(/_/g, " ");
    const role = evt.agent_role ? `[${evt.agent_role}]` : "";
    const msg = `${timeStr} ⚡ ${eventName} ${role}`;

    // Append to live marquee
    if (this.elTickerText) {
      this.elTickerText.textContent = `${msg}  ✦  ${this.elTickerText.textContent.slice(0, 300)}`;
    }

    // Sound feedback based on event type
    if (evt.event_type.includes("COMPLETED")) {
      sfx.playChime();
    } else if (evt.event_type.includes("TICK")) {
      sfx.playTick();
    }

    // Refresh state
    this.fetchState();
  }

  // ===========================================================================
  // API CALLS
  // ===========================================================================
  async fetchState() {
    try {
      const res = await fetch("/api/state");
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      this.state = data;
      this.render();
    } catch (err) {
      console.error("Failed to fetch office state:", err);
    }
  }

  async triggerTick() {
    try {
      this.btnTick.disabled = true;
      this.btnTick.textContent = "⏳ TICKING...";
      const res = await fetch("/api/scheduler/tick", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execute: true }),
      });
      const data = await res.json();
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

  async submitNewQuest() {
    const titleInput = document.getElementById("quest-title");
    const descInput = document.getElementById("quest-desc");
    const budgetInput = document.getElementById("quest-budget");
    const prioritySelect = document.getElementById("quest-priority");

    const payload = {
      title: titleInput.value.trim(),
      description: descInput.value.trim(),
      budget: parseFloat(budgetInput.value) || 0.0,
      priority: prioritySelect.value,
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
    this.renderFloor();
    this.renderSidebar();
  }

  renderHUD() {
    const { hud } = this.state;
    if (!hud) return;

    this.elCycleCounter.textContent = `CYCLE #${String(hud.ticks || 0).padStart(4, "0")}`;
    this.elTreasuryVal.textContent = `$${hud.treasury_funds.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    this.elStaffVal.textContent = `${hud.total_workforce} (${hud.available_workforce} Avail / ${hud.busy_workforce} Busy)`;
    this.elQuestsVal.textContent = `${hud.active_quests} Active / ${hud.completed_quests} Done`;
    this.elHealthVal.textContent = `${hud.system_health}%`;
    if (this.elCronsVal) {
      this.elCronsVal.textContent = `${hud.active_crons || 0} Active`;
    }
  }

  renderFloor() {
    if (!this.state.rooms || !this.elFloorGrid) return;
    this.elFloorGrid.innerHTML = "";

    this.state.rooms.forEach((room) => {
      const roomCard = document.createElement("div");
      roomCard.className = "office-room";
      roomCard.style.borderColor = room.theme || "#38bdf8";

      // Room Header
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

      // Room Interior Grid
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

        // Custom avatar path or fallback to procedural SVG
        const customAvatarSrc = `/static/assets/custom/avatars/${emp.id}.png`;
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

        // Check if custom avatar image exists, and replace if loaded
        const imgTest = new Image();
        imgTest.src = customAvatarSrc;
        imgTest.onload = () => {
          const container = workstation.querySelector(`#avatar-${emp.id}`);
          if (container) {
            container.innerHTML = `<img src="${customAvatarSrc}" alt="${emp.name}" />`;
          }
        };

        workstation.addEventListener("click", () => {
          sfx.playClick();
          this.openEmployeeDossier(emp);
        });

        interior.appendChild(workstation);
      });

      roomCard.appendChild(interior);
      this.elFloorGrid.appendChild(roomCard);
    });
  }

  renderSidebar() {
    if (!this.elSidebarContent) return;
    this.elSidebarContent.innerHTML = "";

    if (this.activeTab === "quests") {
      this.renderQuestsList();
    } else if (this.activeTab === "cron") {
      this.renderCronList();
    } else {
      this.renderLogsList();
    }
  }

  renderCronList() {
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

  renderQuestsList() {
    const objectives = this.state.objectives || [];
    if (objectives.length === 0) {
      this.elSidebarContent.innerHTML = `
        <div style="text-align: center; color: var(--hud-muted); padding: 30px 10px;">
          <p style="font-family: var(--font-retro); font-size: 0.7rem; margin-bottom: 8px;">NO ACTIVE QUESTS</p>
          <p style="font-size: 0.8rem;">Click <strong>+ NEW QUEST</strong> above to launch your first corporate objective!</p>
        </div>
      `;
      return;
    }

    objectives.forEach((obj) => {
      const card = document.createElement("div");
      card.className = "quest-card";

      const statusClass = `status-${obj.status.toLowerCase().replace(/_/g, "-")}`;
      const qualityGrade = obj.quality ? `${obj.quality.grade} (${obj.quality.score}/100)` : "Planning";

      // Milestone progress bars
      let milestoneHtml = "";
      if (obj.milestones && obj.milestones.length > 0) {
        milestoneHtml = `
          <div class="milestones-pipeline" title="Milestones: ${obj.completed_milestones}/${obj.total_milestones} Done">
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
          <span class="tag-badge">Strategy: ${obj.strategy}</span>
          <span class="tag-badge">Grade: ${qualityGrade}</span>
          <span class="tag-badge">Budget: $${obj.spent.toFixed(2)} / $${obj.budget.toFixed(2)}</span>
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

  renderLogsList() {
    const events = this.state.recent_events || [];
    if (events.length === 0) {
      this.elSidebarContent.innerHTML = `<div style="color: var(--hud-muted); padding: 20px;">No logs recorded yet.</div>`;
      return;
    }

    events.forEach((ev) => {
      const item = document.createElement("div");
      item.style.cssText = "background: #0b1120; border: 1px solid var(--border-color); border-radius: 4px; padding: 8px; font-size: 0.75rem; font-family: var(--font-mono);";
      const time = ev.created_at ? ev.created_at.split("T")[1]?.slice(0, 8) : "--:--:--";
      item.innerHTML = `
        <div style="color: #38bdf8; font-weight: bold; margin-bottom: 2px;">[${time}] ${ev.event_type}</div>
        <div style="color: #94a3b8; font-size: 0.7rem;">Agent: ${ev.agent_role || 'System'} | Project: ${ev.project_id || '-'}</div>
      `;
      this.elSidebarContent.appendChild(item);
    });
  }

  // ===========================================================================
  // MODALS
  // ===========================================================================
  openEmployeeDossier(emp) {
    this.selectedEmployee = emp;
    const avatarContainer = document.getElementById("dossier-avatar");
    const customAvatarSrc = `/static/assets/custom/avatars/${emp.id}.png`;

    avatarContainer.innerHTML = generatePixelAvatarSVG(emp.name, emp.role_id, emp.department_id);
    const imgTest = new Image();
    imgTest.src = customAvatarSrc;
    imgTest.onload = () => {
      avatarContainer.innerHTML = `<img src="${customAvatarSrc}" alt="${emp.name}" />`;
    };

    document.getElementById("dossier-name").textContent = emp.name;
    document.getElementById("dossier-title").textContent = `${emp.rpg_class} • Level ${emp.level}`;
    document.getElementById("dossier-dept").textContent = emp.department_id.toUpperCase();

    // Stats
    document.getElementById("stat-level").textContent = `Lv. ${emp.level}`;
    document.getElementById("stat-status").textContent = emp.availability.toUpperCase();
    document.getElementById("stat-caps").textContent = emp.capabilities.join(", ") || "General Tasks";
    document.getElementById("stat-task").textContent = emp.current_task ? emp.current_task.title : "Standby / Available";

    this.modalDossier.classList.remove("hidden");
  }

  openNewQuestModal() {
    this.modalNewQuest.classList.remove("hidden");
    const titleInput = document.getElementById("quest-title");
    if (titleInput) titleInput.focus();
  }

  closeModals() {
    this.modalDossier.classList.add("hidden");
    this.modalNewQuest.classList.add("hidden");
  }
}

// Initialize on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.aetherGame = new AetherGameDashboard();
});
