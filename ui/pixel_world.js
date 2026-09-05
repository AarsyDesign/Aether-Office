/**
 * AETHER PIXEL OFFICE WORLD (HTML5 2D Canvas Engine)
 * Authentic 2D Retro Pixel Art Virtual Office Simulation
 * Inspired by KalebKE/PixelOffice — Features tilemaps, animated pixel characters,
 * glowing monitors, coffee machine steam particles, server LEDs, and interactive furniture.
 */

class PixelOfficeWorld {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) {
      console.error(`Canvas #${canvasId} not found`);
      return;
    }
    this.ctx = this.canvas.getContext("2d");
    this.ctx.imageSmoothingEnabled = false;

    // Virtual resolution (16:9 pixel art canvas)
    this.width = 1024;
    this.height = 576;
    this.canvas.width = this.width;
    this.canvas.height = this.height;

    this.onSelectEmployee = options.onSelectEmployee || null;
    this.onSelectWhiteboard = options.onSelectWhiteboard || null;
    this.sfx = options.sfx || null;

    // Simulation state & theme lighting
    this.state = null;
    this.time = 0;
    this.animFrame = null;
    this.lightMode = (localStorage.getItem("aether_theme") || "light") === "light";

    // Office layout definitions
    this.rooms = this._initRoomLayout();
    this.characters = [];
    this.particles = [];
    this.pets = this._initPets();

    // Mouse interaction
    this.hoveredObject = null;
    this.mousePos = { x: 0, y: 0 };

    this._initEvents();
    this.fitToContainer();

    if (window.ResizeObserver && this.canvas.parentElement) {
      this.resizeObserver = new ResizeObserver(() => this.fitToContainer());
      this.resizeObserver.observe(this.canvas.parentElement);
    }
    window.addEventListener("resize", () => this.fitToContainer());

    this.startLoop();
  }

  fitToContainer() {
    if (!this.canvas || !this.canvas.parentElement) return;
    const parent = this.canvas.parentElement;
    const pw = Math.max(300, parent.clientWidth - 12);
    const ph = Math.max(160, parent.clientHeight - 12);

    const targetAspect = 16 / 9;
    let w = pw;
    let h = w / targetAspect;
    if (h > ph) {
      h = ph;
      w = h * targetAspect;
    }
    this.canvas.style.width = `${Math.floor(w)}px`;
    this.canvas.style.height = `${Math.floor(h)}px`;
  }

  setLightMode(isLight) {
    this.lightMode = !!isLight;
  }

  // =========================================================================
  // 1. ROOM & FURNITURE LAYOUT
  // =========================================================================
  _initRoomLayout() {
    return [
      {
        id: "executive",
        name: "EXECUTIVE SUITE",
        color: "#f59e0b",
        x: 20, y: 20, w: 280, h: 220,
        floorType: "wood",
        furniture: [
          { type: "exec_desk", x: 60, y: 70, w: 100, h: 50, label: "CEO / PM Desk" },
          { type: "bookshelf", x: 190, y: 35, w: 90, h: 45, label: "Archives" },
          { type: "plant", x: 35, y: 35, w: 20, h: 30 },
          { type: "rug", x: 70, y: 140, w: 110, h: 70, color: "#78350f" },
        ]
      },
      {
        id: "war_room",
        name: "THE WAR ROOM (MEETING & ARCH)",
        color: "#38bdf8",
        x: 320, y: 20, w: 380, h: 220,
        floorType: "carpet_blue",
        furniture: [
          { type: "whiteboard", x: 420, y: 30, w: 180, h: 40, label: "LIVE DAG ARCHITECTURE" },
          { type: "conf_table", x: 410, y: 95, w: 200, h: 80, label: "Sprint Planning Table" },
          { type: "plant", x: 335, y: 35, w: 20, h: 30 },
          { type: "plant", x: 665, y: 35, w: 20, h: 30 },
        ]
      },
      {
        id: "cafe",
        name: "CAFE & BREAKROOM",
        color: "#10b981",
        x: 720, y: 20, w: 284, h: 220,
        floorType: "checkered",
        furniture: [
          { type: "coffee_bar", x: 740, y: 35, w: 90, h: 45, label: "Espresso Bar" },
          { type: "water_cooler", x: 845, y: 35, w: 30, h: 45, label: "Water Cooler" },
          { type: "arcade", x: 930, y: 35, w: 50, h: 60, label: "Retro Arcade" },
          { type: "lounge_sofa", x: 780, y: 130, w: 140, h: 60, label: "Break Lounge" },
          { type: "vending", x: 735, y: 130, w: 35, h: 60, label: "Snacks" },
        ]
      },
      {
        id: "engineering",
        name: "ENGINEERING BAY",
        color: "#3b82f6",
        x: 20, y: 260, w: 460, h: 296,
        floorType: "tech_grid",
        furniture: [
          { type: "dev_desk", x: 50, y: 300, w: 85, h: 55, role: "lead", label: "Lead Eng" },
          { type: "dev_desk", x: 155, y: 300, w: 85, h: 55, role: "backend", label: "Backend" },
          { type: "dev_desk", x: 260, y: 300, w: 85, h: 55, role: "frontend", label: "Frontend" },
          { type: "dev_desk", x: 365, y: 300, w: 85, h: 55, role: "devops", label: "DevOps" },

          { type: "dev_desk", x: 50, y: 430, w: 85, h: 55, role: "security", label: "Security" },
          { type: "dev_desk", x: 155, y: 430, w: 85, h: 55, role: "mobile", label: "Mobile" },
          { type: "dev_desk", x: 260, y: 430, w: 85, h: 55, role: "data", label: "Data Eng" },
          { type: "server_mini", x: 380, y: 430, w: 70, h: 60, label: "Build Farm" },
        ]
      },
      {
        id: "qa_lab",
        name: "QA & SECURITY LAB",
        color: "#ea580c",
        x: 500, y: 260, w: 260, h: 296,
        floorType: "tile_orange",
        furniture: [
          { type: "qa_bench", x: 530, y: 310, w: 100, h: 60, label: "Test Runner" },
          { type: "qa_bench", x: 645, y: 310, w: 95, h: 60, label: "Bug Hunter" },
          { type: "bug_board", x: 530, y: 420, w: 100, h: 50, label: "Bug Triage" },
          { type: "cabinet", x: 670, y: 420, w: 60, h: 60, label: "Reports" },
        ]
      },
      {
        id: "server_room",
        name: "SERVER INFRASTRUCTURE",
        color: "#6366f1",
        x: 780, y: 260, w: 224, h: 296,
        floorType: "metal_vent",
        furniture: [
          { type: "server_rack", x: 805, y: 300, w: 75, h: 100, label: "RACK-01" },
          { type: "server_rack", x: 905, y: 300, w: 75, h: 100, label: "RACK-02" },
          { type: "terminal_desk", x: 840, y: 440, w: 110, h: 60, label: "SysAdmin Console" },
        ]
      }
    ];
  }

  _initPets() {
    return [
      {
        type: "cat",
        name: "Mimi",
        x: 120, y: 170,
        targetX: 120, targetY: 170,
        color: "#f97316",
        state: "sleeping",
        speech: "Zzz... 🐱",
        speechTimer: 0
      },
      {
        type: "dog",
        name: "Boni",
        x: 820, y: 180,
        targetX: 820, targetY: 180,
        color: "#a16207",
        state: "walking",
        speech: "Woof! 🐾",
        speechTimer: 0
      }
    ];
  }

  // =========================================================================
  // 2. STATE SYNCHRONIZATION
  // =========================================================================
  updateState(state) {
    this.state = state;
    this._syncCharacters();
  }

  _syncCharacters() {
    if (!this.state || !this.state.rooms) return;

    // Map department employees to desk coordinates
    const deskSlots = [
      // Exec
      { dept: "executive", x: 100, y: 90, chairX: 100, chairY: 125 },
      // Engineering Bay
      { dept: "engineering", x: 85, y: 320, chairX: 85, chairY: 360 },
      { dept: "engineering", x: 190, y: 320, chairX: 190, chairY: 360 },
      { dept: "engineering", x: 295, y: 320, chairX: 295, chairY: 360 },
      { dept: "engineering", x: 400, y: 320, chairX: 400, chairY: 360 },
      { dept: "engineering", x: 85, y: 450, chairX: 85, chairY: 490 },
      { dept: "engineering", x: 190, y: 450, chairX: 190, chairY: 490 },
      { dept: "engineering", x: 295, y: 450, chairX: 295, chairY: 490 },
      // QA Lab
      { dept: "qa", x: 570, y: 330, chairX: 570, chairY: 375 },
      { dept: "qa", x: 680, y: 330, chairX: 680, chairY: 375 },
      // Product & War room
      { dept: "product", x: 450, y: 125, chairX: 450, chairY: 175 },
      { dept: "product", x: 560, y: 125, chairX: 560, chairY: 175 },
      // Design
      { dept: "design", x: 570, y: 440, chairX: 570, chairY: 480 },
      // SysAdmin
      { dept: "operations", x: 885, y: 460, chairX: 885, chairY: 505 },
    ];

    let slotIdx = 0;
    const newChars = [];

    this.state.rooms.forEach((room) => {
      room.employees.forEach((emp, i) => {
        // Find assigned or default slot
        const slot = deskSlots[slotIdx % deskSlots.length];
        slotIdx++;

        // Check if existing character exists to keep smooth position
        const existing = this.characters.find(c => c.id === emp.id);

        const charObj = existing || {
          id: emp.id,
          name: emp.name,
          role: emp.rpg_class || emp.role_id,
          dept: room.id,
          x: slot.chairX,
          y: slot.chairY,
          homeX: slot.chairX,
          homeY: slot.chairY,
          targetX: slot.chairX,
          targetY: slot.chairY,
          typingTimer: 0,
          hairColor: this._getHairColor(emp.name),
          shirtColor: room.theme || "#3b82f6",
        };

        // Update live attributes
        charObj.live_state = (emp.live_state || "IDLE").toUpperCase();
        charObj.current_task = emp.current_task;
        charObj.status = emp.status;
        charObj.availability = emp.availability;
        charObj.raw = emp;

        // Determine speech/emote bubble
        charObj.speech = this._getSpeechBubble(charObj);

        // State actions: if PLANNING, walk near whiteboard
        if (charObj.live_state === "PLANNING" && (room.id === "engineering" || room.id === "product" || room.id === "executive")) {
          charObj.targetX = 450 + (i * 30);
          charObj.targetY = 75;
        } else if (charObj.live_state === "WORKING" || charObj.live_state === "CODING") {
          charObj.targetX = charObj.homeX;
          charObj.targetY = charObj.homeY;
        }

        newChars.push(charObj);
      });
    });

    this.characters = newChars;
  }

  _getSpeechBubble(char) {
    const s = char.live_state;
    if (s === "PLANNING") return "📋 Planning DAG...";
    if (s === "THINKING") return "💡 Thinking...";
    if (s === "TESTING") return "🧪 Running tests...";
    if (s === "WORKING" || s === "CODING") {
      if (char.current_task && char.current_task.title) {
        return `💻 ${char.current_task.title.slice(0, 16)}...`;
      }
      return "💻 Coding core.py";
    }
    if (s === "COMPLETED") return "🎉 Done!";
    if (s === "FAILED") return "❌ Fixing bug";
    if (s === "WAITING" || s === "BLOCKED") return "⏳ Waiting";
    return "☕ Standby";
  }

  _getHairColor(name) {
    const colors = ["#1e293b", "#7c2d12", "#b45309", "#475569", "#0f172a", "#854d0e"];
    let hash = 0;
    for (let i = 0; i < (name || "").length; i++) {
      hash = (hash << 5) - hash + name.charCodeAt(i);
    }
    return colors[Math.abs(hash) % colors.length];
  }

  // Handle high priority event from SSE
  handleEvent(evt) {
    const agentId = evt.agent_id;
    if (agentId) {
      const char = this.characters.find(c => c.id === agentId);
      if (char) {
        if (evt.event_type.includes("STARTED")) {
          char.speech = "🚀 Starting task!";
          char.typingTimer = 60;
        } else if (evt.event_type.includes("COMPLETED")) {
          char.speech = "✨ Finished unit!";
        }
      }
    }
    // Spawn server burst particles if pipeline active
    if (evt.event_type.includes("DEV") || evt.event_type.includes("QA")) {
      this._spawnServerParticles();
    }
  }

  // =========================================================================
  // 3. MAIN GAME RENDER LOOP
  // =========================================================================
  startLoop() {
    const loop = () => {
      this.time += 0.05;
      this.updatePhysics();
      this.render();
      this.animFrame = requestAnimationFrame(loop);
    };
    this.animFrame = requestAnimationFrame(loop);
  }

  stopLoop() {
    if (this.animFrame) cancelAnimationFrame(this.animFrame);
  }

  updatePhysics() {
    // Character interpolation
    this.characters.forEach(char => {
      const dx = char.targetX - char.x;
      const dy = char.targetY - char.y;
      if (Math.abs(dx) > 0.5) char.x += dx * 0.08;
      if (Math.abs(dy) > 0.5) char.y += dy * 0.08;
    });

    // Pet wandering
    this.pets.forEach(pet => {
      if (Math.random() < 0.005) {
        if (pet.type === "cat") {
          // Nap or stretch
          pet.state = Math.random() < 0.7 ? "sleeping" : "walking";
          if (pet.state === "walking") {
            pet.targetX = 50 + Math.random() * 200;
            pet.targetY = 140 + Math.random() * 60;
          }
        } else {
          // Dog walks around breakroom or engineering
          pet.targetX = 750 + Math.random() * 180;
          pet.targetY = 130 + Math.random() * 80;
        }
      }
      const dx = pet.targetX - pet.x;
      const dy = pet.targetY - pet.y;
      if (Math.abs(dx) > 0.5) pet.x += dx * 0.05;
      if (Math.abs(dy) > 0.5) pet.y += dy * 0.05;
    });

    // Coffee Steam Particles
    if (Math.random() < 0.3) {
      this.particles.push({
        x: 775 + (Math.random() * 6 - 3),
        y: 40,
        vx: (Math.random() - 0.5) * 0.4,
        vy: -0.8 - Math.random() * 0.5,
        alpha: 0.8,
        size: 3 + Math.random() * 3,
        type: "steam"
      });
    }

    // Update particles
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.alpha -= 0.015;
      if (p.alpha <= 0) this.particles.splice(i, 1);
    }
  }

  _spawnServerParticles() {
    for (let i = 0; i < 4; i++) {
      this.particles.push({
        x: 840 + Math.random() * 120,
        y: 320 + Math.random() * 60,
        vx: (Math.random() - 0.5) * 1.5,
        vy: -0.5 - Math.random(),
        alpha: 1.0,
        size: 2,
        color: Math.random() < 0.5 ? "#22c55e" : "#38bdf8",
        type: "spark"
      });
    }
  }

  // =========================================================================
  // 4. RENDERING ROUTINES (PIXEL ART CANVAS)
  // =========================================================================
  render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    // 1. Draw outer walls & floor background (Daylight office or Dark retro)
    ctx.fillStyle = this.lightMode ? "#cbd5e1" : "#090d16";
    ctx.fillRect(0, 0, this.width, this.height);

    // 2. Draw Rooms & Tiles
    this.rooms.forEach(room => this._drawRoomFloor(room));

    // 3. Draw Room Dividers & Walls
    this.rooms.forEach(room => this._drawRoomWalls(room));

    // 4. Draw Furniture
    this.rooms.forEach(room => {
      (room.furniture || []).forEach(furn => this._drawFurniture(furn, room));
    });

    // 5. Draw Particles (Coffee steam, server sparks)
    this._drawParticles();

    // 6. Draw Pets
    this.pets.forEach(pet => this._drawPet(pet));

    // 7. Draw Characters
    // Sort by Y position for proper 2.5D retro depth sorting
    const sortedChars = [...this.characters].sort((a, b) => a.y - b.y);
    sortedChars.forEach(char => this._drawCharacter(char));

    // 8. Draw Speech Bubbles
    sortedChars.forEach(char => this._drawSpeechBubble(char));

    // 9. Draw Room Labels (Retro Pixel Headers)
    this.rooms.forEach(room => this._drawRoomHeader(room));

    // 10. Draw Hover Cursor / Tooltip
    if (this.hoveredObject) {
      this._drawHoverHighlight(this.hoveredObject);
    }
  }

  _drawRoomFloor(room) {
    const ctx = this.ctx;
    ctx.save();

    // Base floor
    if (room.floorType === "wood") {
      ctx.fillStyle = this.lightMode ? "#fde68a" : "#1e1b18";
      ctx.fillRect(room.x, room.y, room.w, room.h);
      // Wood planks
      ctx.strokeStyle = this.lightMode ? "#d97706" : "#292524";
      ctx.lineWidth = 1;
      for (let py = room.y; py < room.y + room.h; py += 16) {
        ctx.beginPath();
        ctx.moveTo(room.x, py);
        ctx.lineTo(room.x + room.w, py);
        ctx.stroke();
      }
    } else if (room.floorType === "carpet_blue") {
      ctx.fillStyle = this.lightMode ? "#bfdbfe" : "#0f172a";
      ctx.fillRect(room.x, room.y, room.w, room.h);
      // Subtle weave
      ctx.fillStyle = this.lightMode ? "#93c5fd" : "#1e293b";
      for (let px = room.x; px < room.x + room.w; px += 24) {
        for (let py = room.y; py < room.y + room.h; py += 24) {
          ctx.fillRect(px + 4, py + 4, 2, 2);
        }
      }
    } else if (room.floorType === "checkered") {
      const tileSize = 20;
      for (let px = room.x; px < room.x + room.w; px += tileSize) {
        for (let py = room.y; py < room.y + room.h; py += tileSize) {
          const isWhite = ((px - room.x) / tileSize + (py - room.y) / tileSize) % 2 === 0;
          if (this.lightMode) {
            ctx.fillStyle = isWhite ? "#ffffff" : "#f1f5f9";
          } else {
            ctx.fillStyle = isWhite ? "#334155" : "#1e293b";
          }
          ctx.fillRect(px, py, tileSize, tileSize);
        }
      }
    } else if (room.floorType === "metal_vent") {
      ctx.fillStyle = this.lightMode ? "#f8fafc" : "#0b0f19";
      ctx.fillRect(room.x, room.y, room.w, room.h);
      ctx.strokeStyle = this.lightMode ? "#cbd5e1" : "#1e293b";
      ctx.lineWidth = 1;
      for (let px = room.x; px < room.x + room.w; px += 32) {
        ctx.strokeRect(px, room.y, 32, room.h);
      }
    } else {
      // Standard tech floor
      ctx.fillStyle = this.lightMode ? "#f8fafc" : "#0f172a";
      ctx.fillRect(room.x, room.y, room.w, room.h);
      ctx.strokeStyle = this.lightMode ? "#e2e8f0" : "#1e293b";
      ctx.lineWidth = 1;
      for (let px = room.x; px < room.x + room.w; px += 32) {
        for (let py = room.y; py < room.y + room.h; py += 32) {
          ctx.strokeRect(px, py, 32, 32);
        }
      }
    }
    ctx.restore();
  }

  _drawRoomWalls(room) {
    const ctx = this.ctx;
    ctx.save();
    // Outer wall border
    ctx.strokeStyle = this.lightMode ? "#64748b" : "#334155";
    ctx.lineWidth = 4;
    ctx.strokeRect(room.x, room.y, room.w, room.h);

    // Accent line at bottom of top wall
    ctx.strokeStyle = room.color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(room.x, room.y + 24);
    ctx.lineTo(room.x + room.w, room.y + 24);
    ctx.stroke();

    ctx.restore();
  }

  _drawRoomHeader(room) {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = this.lightMode ? "#ffffff" : "#0b1329";
    ctx.fillRect(room.x + 8, room.y + 4, room.w - 16, 18);
    if (this.lightMode) {
      ctx.strokeStyle = "#cbd5e1";
      ctx.lineWidth = 1;
      ctx.strokeRect(room.x + 8, room.y + 4, room.w - 16, 18);
    }

    ctx.fillStyle = room.color;
    ctx.font = "bold 10px 'Press Start 2P', monospace";
    ctx.fillText(room.name, room.x + 14, room.y + 17);
    ctx.restore();
  }

  // =========================================================================
  // 5. DRAW FURNITURE (PIXEL ART STYLE)
  // =========================================================================
  _drawFurniture(furn, room) {
    const ctx = this.ctx;
    ctx.save();

    if (furn.type === "dev_desk" || furn.type === "exec_desk") {
      // Wood Desk Tabletop
      ctx.fillStyle = furn.type === "exec_desk" ? "#78350f" : "#475569";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      ctx.fillStyle = furn.type === "exec_desk" ? "#92400e" : "#64748b";
      ctx.fillRect(furn.x + 2, furn.y + 2, furn.w - 4, 8); // Desk highlight

      // Dual Computer Monitors
      const monW = 26;
      const monH = 18;

      // Monitor 1
      this._drawMonitor(furn.x + 10, furn.y + 12, monW, monH, room);
      // Monitor 2
      this._drawMonitor(furn.x + 46, furn.y + 12, monW, monH, room);

      // Keyboard & Mousepad
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(furn.x + 24, furn.y + 36, 32, 8);
      ctx.fillStyle = "#94a3b8";
      ctx.fillRect(furn.x + 60, furn.y + 36, 12, 10); // Mouse

    } else if (furn.type === "whiteboard") {
      // Whiteboard Frame
      ctx.fillStyle = "#cbd5e1";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(furn.x + 4, furn.y + 4, furn.w - 8, furn.h - 8);

      // Interactive Architecture Diagram
      ctx.fillStyle = "#38bdf8";
      ctx.font = "8px 'Press Start 2P', monospace";
      ctx.fillText("ARCHITECTURE [DAG]", furn.x + 12, furn.y + 16);

      // Animated diagram nodes & connections
      const pulse = Math.sin(this.time * 3) > 0;
      ctx.fillStyle = pulse ? "#4ade80" : "#22c55e";
      ctx.fillRect(furn.x + 15, furn.y + 22, 20, 8);
      ctx.fillStyle = "#f59e0b";
      ctx.fillRect(furn.x + 60, furn.y + 22, 35, 8);
      ctx.fillStyle = "#38bdf8";
      ctx.fillRect(furn.x + 120, furn.y + 22, 40, 8);

      // Arrows
      ctx.strokeStyle = "#94a3b8";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(furn.x + 35, furn.y + 26);
      ctx.lineTo(furn.x + 60, furn.y + 26);
      ctx.moveTo(furn.x + 95, furn.y + 26);
      ctx.lineTo(furn.x + 120, furn.y + 26);
      ctx.stroke();

    } else if (furn.type === "coffee_bar") {
      // Counter
      ctx.fillStyle = "#475569";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      ctx.fillStyle = "#64748b";
      ctx.fillRect(furn.x + 2, furn.y + 2, furn.w - 4, 6);

      // Espresso Machine
      ctx.fillStyle = "#991b1b"; // Red retro body
      ctx.fillRect(furn.x + 15, furn.y + 10, 35, 28);
      ctx.fillStyle = "#e2e8f0"; // Chrome portafilter
      ctx.fillRect(furn.x + 22, furn.y + 26, 8, 4);

      // Coffee cups
      ctx.fillStyle = "#f8fafc";
      ctx.fillRect(furn.x + 60, furn.y + 18, 10, 10);
      ctx.fillRect(furn.x + 72, furn.y + 18, 10, 10);

    } else if (furn.type === "water_cooler") {
      // Stand
      ctx.fillStyle = "#e2e8f0";
      ctx.fillRect(furn.x + 5, furn.y + 20, 20, 25);
      // Blue Water Bottle
      ctx.fillStyle = "#38bdf8";
      ctx.fillRect(furn.x + 7, furn.y + 5, 16, 18);
      // Bubbling water animation
      if (Math.sin(this.time * 5) > 0.4) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(furn.x + 12, furn.y + 12, 3, 3);
      }

    } else if (furn.type === "arcade") {
      // Retro Arcade Cabinet
      ctx.fillStyle = "#7c3aed";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      // Screen
      ctx.fillStyle = (Math.floor(this.time * 2) % 2 === 0) ? "#facc15" : "#ec4899";
      ctx.fillRect(furn.x + 8, furn.y + 12, furn.w - 16, 22);
      // Marquee
      ctx.fillStyle = "#f43f5e";
      ctx.fillRect(furn.x + 6, furn.y + 3, furn.w - 12, 6);

    } else if (furn.type === "server_rack") {
      // Server Rack Chassis
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 2;
      ctx.strokeRect(furn.x, furn.y, furn.w, furn.h);

      // Server Units & Blinking LEDs
      for (let sy = furn.y + 8; sy < furn.y + furn.h - 10; sy += 14) {
        ctx.fillStyle = "#1e293b";
        ctx.fillRect(furn.x + 4, sy, furn.w - 8, 10);

        // Blinking LEDs
        const isBlinking = Math.sin(this.time * 8 + sy) > 0;
        ctx.fillStyle = isBlinking ? "#22c55e" : "#14532d";
        ctx.fillRect(furn.x + 8, sy + 3, 4, 4);

        ctx.fillStyle = (sy % 2 === 0) ? "#38bdf8" : (isBlinking ? "#f59e0b" : "#78350f");
        ctx.fillRect(furn.x + 16, sy + 3, 4, 4);
      }

    } else if (furn.type === "conf_table") {
      // Big Conference Table
      ctx.fillStyle = "#7c2d12";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      ctx.fillStyle = "#9a3412";
      ctx.fillRect(furn.x + 6, furn.y + 6, furn.w - 12, furn.h - 12);

      // Laptops on table
      const laptopPositions = [
        { x: furn.x + 20, y: furn.y + 15 },
        { x: furn.x + 80, y: furn.y + 15 },
        { x: furn.x + 140, y: furn.y + 15 },
        { x: furn.x + 50, y: furn.y + 50 },
        { x: furn.x + 110, y: furn.y + 50 },
      ];
      laptopPositions.forEach(pos => {
        ctx.fillStyle = "#cbd5e1";
        ctx.fillRect(pos.x, pos.y, 22, 14);
        ctx.fillStyle = "#38bdf8";
        ctx.fillRect(pos.x + 2, pos.y + 2, 18, 9);
      });

    } else if (furn.type === "plant") {
      // Clay Pot
      ctx.fillStyle = "#c2410c";
      ctx.fillRect(furn.x + 4, furn.y + 16, 12, 12);
      // Leaves
      ctx.fillStyle = "#22c55e";
      ctx.fillRect(furn.x, furn.y + 6, 20, 10);
      ctx.fillStyle = "#15803d";
      ctx.fillRect(furn.x + 3, furn.y, 14, 8);

    } else if (furn.type === "lounge_sofa") {
      // Leather sofa
      ctx.fillStyle = "#1e3a8a";
      ctx.fillRect(furn.x, furn.y, furn.w, furn.h);
      ctx.fillStyle = "#1d4ed8";
      ctx.fillRect(furn.x + 6, furn.y + 6, furn.w - 12, furn.h - 14);
    }

    ctx.restore();
  }

  _drawMonitor(x, y, w, h, room) {
    const ctx = this.ctx;
    // Monitor Case
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);

    // Screen Glow Animation (Green code for eng, Cyan for QA, Gold for PM)
    let screenColor = "#22c55e";
    if (room.id === "qa_lab") screenColor = "#38bdf8";
    if (room.id === "executive") screenColor = "#f59e0b";

    ctx.fillStyle = screenColor;
    const scanlineOffset = Math.floor(this.time * 10) % 4;
    for (let ly = y + 4 + scanlineOffset; ly < y + h - 4; ly += 4) {
      ctx.fillRect(x + 4, ly, w - 8, 2);
    }
  }

  _drawParticles() {
    const ctx = this.ctx;
    ctx.save();
    this.particles.forEach(p => {
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = p.type === "steam" ? "#f1f5f9" : (p.color || "#38bdf8");
      ctx.fillRect(p.x, p.y, p.size, p.size);
    });
    ctx.restore();
  }

  _drawPet(pet) {
    const ctx = this.ctx;
    ctx.save();

    if (pet.type === "cat") {
      // Orange tabby cat
      ctx.fillStyle = pet.color;
      if (pet.state === "sleeping") {
        // Curled up oval
        ctx.beginPath();
        ctx.ellipse(pet.x, pet.y, 10, 6, 0, 0, Math.PI * 2);
        ctx.fill();
        // Ears
        ctx.fillStyle = "#ea580c";
        ctx.fillRect(pet.x - 7, pet.y - 6, 3, 3);
        ctx.fillRect(pet.x - 3, pet.y - 6, 3, 3);
      } else {
        // Walking
        ctx.fillRect(pet.x - 8, pet.y - 5, 16, 10);
        ctx.fillRect(pet.x + 6, pet.y - 8, 6, 6); // Head
        // Tail waving
        const tailY = pet.y - 3 + Math.sin(this.time * 6) * 3;
        ctx.fillRect(pet.x - 12, tailY, 5, 3);
      }
    } else {
      // Dog
      ctx.fillStyle = pet.color;
      ctx.fillRect(pet.x - 10, pet.y - 6, 20, 12);
      ctx.fillRect(pet.x + 8, pet.y - 10, 8, 8); // Head
      ctx.fillStyle = "#451a03";
      ctx.fillRect(pet.x + 10, pet.y - 7, 4, 6); // Floppy ear
      // Tail wagging
      const tailOffset = Math.sin(this.time * 8) * 4;
      ctx.fillStyle = "#78350f";
      ctx.fillRect(pet.x - 13, pet.y - 8 + tailOffset, 4, 4);
    }

    ctx.restore();
  }

  // =========================================================================
  // 6. DRAW CHARACTERS (16x24 PIXEL HUMAN SPRITE)
  // =========================================================================
  _drawCharacter(char) {
    const ctx = this.ctx;
    const x = Math.round(char.x);
    const y = Math.round(char.y);

    ctx.save();

    // Idle breathing offset
    const breathe = Math.sin(this.time * 3 + (char.x * 0.1)) * 1;
    const isTyping = char.live_state === "WORKING" || char.live_state === "CODING" || char.typingTimer > 0;

    // 1. Shadow under feet
    ctx.fillStyle = "rgba(0, 0, 0, 0.4)";
    ctx.beginPath();
    ctx.ellipse(x, y + 12, 10, 4, 0, 0, Math.PI * 2);
    ctx.fill();

    // 2. Legs / Pants
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(x - 5, y + 4, 4, 8);
    ctx.fillRect(x + 1, y + 4, 4, 8);

    // Shoes
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(x - 6, y + 10, 5, 3);
    ctx.fillRect(x + 1, y + 10, 5, 3);

    // 3. Torso / Shirt (Color coded by department)
    ctx.fillStyle = char.shirtColor || "#3b82f6";
    ctx.fillRect(x - 6, y - 6 + breathe, 12, 10);

    // 4. Arms & Typing Hands
    if (isTyping) {
      // Rapid keyboard typing animation
      const handY = y - 1 + ((Math.floor(this.time * 12) % 2 === 0) ? 2 : 0);
      ctx.fillStyle = char.shirtColor || "#3b82f6";
      ctx.fillRect(x - 8, y - 4 + breathe, 3, 5);
      ctx.fillRect(x + 5, y - 4 + breathe, 3, 5);
      // Skin tone hands
      ctx.fillStyle = "#fed7aa";
      ctx.fillRect(x - 7, handY, 3, 3);
      ctx.fillRect(x + 4, handY, 3, 3);
    } else {
      ctx.fillStyle = char.shirtColor || "#3b82f6";
      ctx.fillRect(x - 8, y - 4 + breathe, 2, 8);
      ctx.fillRect(x + 6, y - 4 + breathe, 2, 8);
    }

    // 5. Head / Face
    ctx.fillStyle = "#fed7aa"; // Skin tone
    ctx.fillRect(x - 5, y - 15 + breathe, 10, 9);

    // Eyes
    const blink = Math.sin(this.time * 0.8 + char.y) > 0.96;
    ctx.fillStyle = "#0f172a";
    if (blink) {
      ctx.fillRect(x - 3, y - 10 + breathe, 2, 1);
      ctx.fillRect(x + 1, y - 10 + breathe, 2, 1);
    } else {
      ctx.fillRect(x - 3, y - 11 + breathe, 2, 2);
      ctx.fillRect(x + 1, y - 11 + breathe, 2, 2);
    }

    // 6. Hair
    ctx.fillStyle = char.hairColor || "#1e293b";
    ctx.fillRect(x - 6, y - 18 + breathe, 12, 4); // Top
    ctx.fillRect(x - 6, y - 15 + breathe, 2, 4);  // Left side
    ctx.fillRect(x + 4, y - 15 + breathe, 2, 4);  // Right side

    ctx.restore();
  }

  // =========================================================================
  // 7. SPEECH / EMOTE BUBBLE
  // =========================================================================
  _drawSpeechBubble(char) {
    if (!char.speech) return;

    const ctx = this.ctx;
    const x = Math.round(char.x);
    const y = Math.round(char.y - 28);

    ctx.save();
    ctx.font = "8px 'Space Mono', monospace";
    const textWidth = ctx.measureText(char.speech).width;
    const pad = 6;
    const bx = x - (textWidth / 2) - pad;
    const by = y - 12;
    const bw = textWidth + pad * 2;
    const bh = 16;

    // Bubble background
    ctx.fillStyle = this.lightMode ? "#ffffff" : "#0f172a";
    ctx.fillRect(bx, by, bw, bh);
    ctx.strokeStyle = this.lightMode ? "#0284c7" : "#38bdf8";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(bx, by, bw, bh);

    // Bubble pointer down
    ctx.fillStyle = this.lightMode ? "#ffffff" : "#0f172a";
    ctx.beginPath();
    ctx.moveTo(x - 3, by + bh);
    ctx.lineTo(x + 3, by + bh);
    ctx.lineTo(x, by + bh + 4);
    ctx.fill();

    // Bubble text
    ctx.fillStyle = this.lightMode ? "#0f172a" : "#f8fafc";
    ctx.font = "bold 9px 'Space Mono', monospace";
    ctx.fillText(char.speech, bx + pad, by + 11);

    ctx.restore();
  }

  // =========================================================================
  // 8. INTERACTION & CLICKS
  // =========================================================================
  _initEvents() {
    this.canvas.addEventListener("mousemove", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const scaleX = this.width / rect.width;
      const scaleY = this.height / rect.height;
      this.mousePos.x = (e.clientX - rect.left) * scaleX;
      this.mousePos.y = (e.clientY - rect.top) * scaleY;

      this._checkHover();
    });

    this.canvas.addEventListener("click", () => {
      if (this.hoveredObject) {
        if (this.hoveredObject.type === "character" && this.onSelectEmployee) {
          if (this.sfx) this.sfx.playClick();
          this.onSelectEmployee(this.hoveredObject.data.raw);
        } else if (this.hoveredObject.type === "whiteboard" && this.onSelectWhiteboard) {
          if (this.sfx) this.sfx.playFanfare();
          this.onSelectWhiteboard();
        } else if (this.hoveredObject.type === "coffee") {
          if (this.sfx) this.sfx.playChime();
          this._triggerCoffeeBreak();
        }
      }
    });
  }

  _checkHover() {
    const mx = this.mousePos.x;
    const my = this.mousePos.y;

    // Check characters first
    for (const char of this.characters) {
      if (Math.hypot(char.x - mx, char.y - my) < 20) {
        this.hoveredObject = { type: "character", data: char, x: char.x, y: char.y };
        this.canvas.style.cursor = "pointer";
        return;
      }
    }

    // Check Whiteboard
    if (mx >= 420 && mx <= 600 && my >= 30 && my <= 70) {
      this.hoveredObject = { type: "whiteboard", label: "Inspect DAG Whiteboard" };
      this.canvas.style.cursor = "pointer";
      return;
    }

    // Check Coffee machine
    if (mx >= 740 && mx <= 830 && my >= 35 && my <= 80) {
      this.hoveredObject = { type: "coffee", label: "Dispense Espresso" };
      this.canvas.style.cursor = "pointer";
      return;
    }

    this.hoveredObject = null;
    this.canvas.style.cursor = "default";
  }

  _drawHoverHighlight(hovered) {
    const ctx = this.ctx;
    ctx.save();
    if (hovered.type === "character") {
      ctx.strokeStyle = "#facc15";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.strokeRect(hovered.x - 12, hovered.y - 20, 24, 32);
    }
    ctx.restore();
  }

  _triggerCoffeeBreak() {
    // Send random idle character to coffee machine
    const idleChar = this.characters.find(c => c.live_state === "IDLE");
    if (idleChar) {
      idleChar.targetX = 760;
      idleChar.targetY = 90;
      idleChar.speech = "☕ Coffee break!";
      setTimeout(() => {
        idleChar.targetX = idleChar.homeX;
        idleChar.targetY = idleChar.homeY;
        idleChar.speech = "Refreshed! ⚡";
      }, 5000);
    }
  }
}

window.PixelOfficeWorld = PixelOfficeWorld;
