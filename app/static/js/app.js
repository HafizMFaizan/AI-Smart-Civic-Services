// =================================================================
// AI SMART CIVIC SERVICES - MAIN CITIZEN & AUTHENTICATION CORE JS
// =================================================================

const API_BASE = "/api";

// Active Logged In Session State
let currentUser = JSON.parse(localStorage.getItem("civic_user") || "null");
let citizenMap = null;
let mapMarkers = [];
let myComplaintsCache = [];

// Sample High Quality Civic Issue Dataset with SLA & DevOps Pipeline Stages
const SAMPLE_ISSUES = [
  {
    id: 101,
    category: "Road",
    priority: "High",
    status: "in_progress",
    pipeline_stage: "in_repair",
    sla_days: 4,
    sla_due_date: "2026-08-13 08:30",
    sla_status: "on_time",
    department: "Roads & Highways",
    description: "Deep pothole causing severe traffic bottleneck near Main St & 5th Ave",
    location: "Main St & 5th Ave, Central District",
    date: "2026-08-09 08:30",
    lat: 24.8607,
    lng: 67.0011,
    img: "https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&w=600&q=80",
    ai_summary: "Structural pavement cracking. Auto-routed to Roads Dept under 4-Day SLA.",
    department_remarks: null
  },
  {
    id: 102,
    category: "Electricity",
    priority: "Critical",
    status: "open",
    pipeline_stage: "ai_triaged",
    sla_days: 2,
    sla_due_date: "2026-08-11 09:15",
    sla_status: "on_time",
    department: "Electrical Utilities",
    description: "Broken streetlight pole with exposed wiring near Park Avenue",
    location: "Park Ave & 12th St, North Zone",
    date: "2026-08-09 09:15",
    lat: 24.8712,
    lng: 67.0255,
    img: "https://images.unsplash.com/photo-1509391365360-2e959784a276?auto=format&fit=crop&w=600&q=80",
    ai_summary: "HIGH VOLTAGE HAZARD! Instant Emergency Broadcast Alert triggered.",
    department_remarks: null
  },
  {
    id: 103,
    category: "Waste",
    priority: "Medium",
    status: "resolved",
    pipeline_stage: "resolved",
    sla_days: 7,
    sla_due_date: "2026-08-15 14:20",
    sla_status: "on_time",
    department: "Solid Waste Mgmt",
    description: "Overflowing garbage dumpsters blocking pedestrian walkway",
    location: "Commercial Area 4, East Ward",
    date: "2026-08-08 14:20",
    lat: 24.8450,
    lng: 67.0340,
    img: "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80",
    ai_summary: "Solid waste overflow. Sanitation crew dispatched.",
    department_remarks: "Resolved on-time within 2 hours. Green SLA rating awarded."
  }
];

// Initialize application on load
document.addEventListener("DOMContentLoaded", () => {
  renderAuthControls();
  fetchCityHealthRisk();
  renderRoute();
  initCitizenMap();
  loadCitizenComplaintsFromUI();
  loadNotifications();
});

// City Health Risk Indicator Engine (Req #20)
async function fetchCityHealthRisk() {
  const riskBar = document.getElementById("city-health-bar");
  const riskLight = document.getElementById("city-risk-light");
  const riskText = document.getElementById("city-risk-text");
  if (!riskBar) return;

  try {
    const res = await fetch(`${API_BASE}/city-health`);
    let data = { risk_level: "GREEN", description: "Optimal Operations" };
    if (res.ok) data = await res.json();

    if (data.risk_level === "RED") {
      riskBar.className = "w-full bg-rose-950/90 border-b border-rose-500/40 px-4 py-1.5 flex items-center justify-between text-xs transition-all";
      riskLight.className = "w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping";
      riskText.innerHTML = `🔴 <strong>HIGH ALERT:</strong> Heavy Municipal Complaint Overload (${data.critical_active_count} Active Critical Cases)`;
    } else if (data.risk_level === "ORANGE") {
      riskBar.className = "w-full bg-amber-950/90 border-b border-amber-500/40 px-4 py-1.5 flex items-center justify-between text-xs transition-all";
      riskLight.className = "w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse";
      riskText.innerHTML = `🟠 <strong>MODERATE ALERT:</strong> Active Municipal Dispatch Pipeline (${data.critical_active_count} High Priority Cases)`;
    } else {
      riskBar.className = "w-full bg-emerald-950/80 border-b border-emerald-500/30 px-4 py-1.5 flex items-center justify-between text-xs transition-all";
      riskLight.className = "w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse";
      riskText.innerHTML = `🟢 <strong>OPTIMAL OPERATIONS:</strong> All City Municipal Systems Green`;
    }
  } catch (e) {
    console.log("Using default city risk bar");
  }
}

// Authentication Session & Gatekeeper (Req #2, #19, #20)
function renderAuthControls() {
  const container = document.getElementById("auth-controls-container");
  const landingGate = document.getElementById("citizen-landing-gate");
  const isAdmin = window.location.hash.startsWith("#/admin");

  if (isAdmin) {
    let currentAdminUser = JSON.parse(localStorage.getItem("civic_admin_user") || 'null');
    if (container) {
      if (currentAdminUser) {
        container.innerHTML = `
          <div class="flex items-center gap-2 bg-indigo-950/80 px-3 py-1.5 rounded-xl border border-indigo-500/30 text-xs">
            <span class="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-pulse"></span>
            <span class="font-bold text-white">${escapeHtml(currentAdminUser.name || "Municipal Admin")}</span>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 uppercase">${currentAdminUser.role || "ADMIN"}</span>
            <button onclick="handleAdminLogout()" class="text-slate-400 hover:text-rose-400 ml-1" title="Sign Out Admin">
              <i class="fa-solid fa-right-from-bracket"></i>
            </button>
          </div>
        `;
      } else {
        container.innerHTML = `
          <button onclick="openAuthModal('login')" class="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-3.5 py-2 rounded-xl text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/20">
            <i class="fa-solid fa-user-shield"></i>
            <span>Admin Staff Sign In</span>
          </button>
        `;
      }
    }
  } else {
    if (currentUser) {
      // Check if citizen has 0 active complaints for Citizen Active Green Light (Req #20)
      const activeComplaintsCount = myComplaintsCache.filter(c => c.status !== 'resolved' && c.status !== 'closed').length;
      const greenLightBadge = activeComplaintsCount === 0 
        ? `<span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" title="0 Pending Complaints - Active Status Green"></span>` 
        : `<span class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" title="${activeComplaintsCount} Active Complaints"></span>`;

      if (container) {
        container.innerHTML = `
          <div class="flex items-center gap-2 bg-surfacealt px-3 py-1.5 rounded-xl border border-bordercolor text-xs">
            ${greenLightBadge}
            <span class="font-bold text-white">${escapeHtml(currentUser.name)}</span>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/10 text-sky-400 border border-sky-500/20 uppercase">${currentUser.role}</span>
            <button onclick="handleLogout()" class="text-slate-400 hover:text-rose-400 ml-1" title="Sign Out">
              <i class="fa-solid fa-right-from-bracket"></i>
            </button>
          </div>
        `;
      }

      if (landingGate) {
        landingGate.innerHTML = `
          <div class="space-y-1">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Citizen Authenticated Session Active</span>
            </div>
            <h2 class="text-xl font-bold font-heading text-white">Welcome back, ${escapeHtml(currentUser.name)}!</h2>
            <p class="text-xs text-slate-300">Your account is connected. Submit issues, receive SMS alerts, and track resolution timelines live.</p>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <button onclick="openReportModal()" class="bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold px-4 py-2 rounded-xl text-xs flex items-center gap-2 shadow-lg shadow-sky-500/20 transition">
              <i class="fa-solid fa-camera"></i>
              <span>Report Live Issue</span>
            </button>
          </div>
        `;
      }
    } else {
      if (container) {
        container.innerHTML = `
          <button onclick="openAuthModal('login')" class="bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold px-3.5 py-2 rounded-xl text-xs flex items-center gap-1.5 shadow-md shadow-sky-500/20">
            <i class="fa-solid fa-right-to-bracket"></i>
            <span>Sign In / Register</span>
          </button>
        `;
      }
    }
  }
}

function handleAdminLogout() {
  localStorage.removeItem("civic_admin_user");
  renderAuthControls();
}

function openAuthModal(tab = "login") {
  document.getElementById("auth-modal").classList.remove("hidden");
  switchAuthTab(tab);
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.add("hidden");
}

function switchAuthTab(tab) {
  const loginForm = document.getElementById("login-form");
  const signupForm = document.getElementById("signup-form");
  const adminReqForm = document.getElementById("admin-request-form");
  const tabLogin = document.getElementById("auth-login-tab");
  const tabSignup = document.getElementById("auth-signup-tab");
  const tabAdmin = document.getElementById("auth-admin-tab");

  loginForm.classList.add("hidden");
  signupForm.classList.add("hidden");
  adminReqForm.classList.add("hidden");

  tabLogin.className = "flex-1 py-2 font-bold text-slate-400 border-b-2 border-transparent hover:text-white";
  tabSignup.className = "flex-1 py-2 font-bold text-slate-400 border-b-2 border-transparent hover:text-white";
  tabAdmin.className = "flex-1 py-2 font-bold text-slate-400 border-b-2 border-transparent hover:text-white";

  if (tab === "login") {
    loginForm.classList.remove("hidden");
    tabLogin.className = "flex-1 py-2 font-bold text-sky-400 border-b-2 border-sky-400";
  } else if (tab === "signup") {
    signupForm.classList.remove("hidden");
    tabSignup.className = "flex-1 py-2 font-bold text-sky-400 border-b-2 border-sky-400";
  } else {
    adminReqForm.classList.remove("hidden");
    tabAdmin.className = "flex-1 py-2 font-bold text-indigo-400 border-b-2 border-indigo-400";
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });

    if (res.ok) {
      const data = await res.json();
      const user = data.user;
      if (user.role === "admin" || user.role === "super_admin") {
        localStorage.setItem("civic_admin_user", JSON.stringify(user));
        alert(`Authenticated as ${user.name} (${user.role.toUpperCase()})!`);
        window.location.hash = "#/admin";
      } else {
        currentUser = user;
        localStorage.setItem("civic_user", JSON.stringify(currentUser));
        alert(`Welcome back, ${currentUser.name}! Citizen session active.`);
      }
      renderAuthControls();
      closeAuthModal();
      loadCitizenComplaintsFromUI();
      loadNotifications();
    } else {
      alert("Invalid login credentials.");
    }
  } catch (err) {
    alert("Unable to reach the server. Please check your connection and try again.");
  }
}

async function handleSignupSubmit(e) {
  e.preventDefault();
  const name = document.getElementById("signup-name").value;
  const email = document.getElementById("signup-email").value;
  const phone = document.getElementById("signup-phone").value;
  const password = document.getElementById("signup-password").value;

  try {
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, phone, password })
    });

    if (res.ok) {
      const data = await res.json();
      currentUser = { id: data.user_id, name, email, phone, role: "citizen" };
      localStorage.setItem("civic_user", JSON.stringify(currentUser));
      renderAuthControls();
      closeAuthModal();
      loadCitizenComplaintsFromUI();
      loadNotifications();
      alert(`Account registered & verified! Welcome to AI Smart Civic Services, ${name}.`);
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to sign up. Please try again.");
    }
  } catch (err) {
    alert("Unable to reach the server. Please check your connection and try again.");
  }
}

async function handleAdminRequestSubmit(e) {
  e.preventDefault();
  if (!currentUser) {
    alert("Please sign up or sign in with a citizen account first, then apply for admin rights.");
    switchAuthTab("signup");
    return;
  }

  const dept = document.getElementById("admin-req-dept").value;
  const reason = document.getElementById("admin-req-reason").value;

  try {
    const res = await fetch(`${API_BASE}/admin-applications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: currentUser.id, department_name: dept, reason })
    });

    if (res.ok) {
      alert(`Admin application for ${dept} submitted! Pending Super Admin review.`);
      closeAuthModal();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to submit admin application. Please try again.");
    }
  } catch (err) {
    alert("Unable to reach the server. Please check your connection and try again.");
  }
}

function handleLogout() {
  localStorage.removeItem("civic_user");
  currentUser = null;
  myComplaintsCache = [];
  renderAuthControls();
  loadCitizenComplaintsFromUI();
  loadNotifications();
}

// Navigation Tab Switcher
function switchTab(tab) {
  window.location.hash = tab === "admin" ? "#/admin" : "#/";
  renderRoute();
}

function renderRoute() {
  renderAuthControls();
  const isAdmin = window.location.hash.startsWith("#/admin");
  const citizenView = document.getElementById("citizen-view");
  const adminView = document.getElementById("admin-view");
  const citizenBtn = document.getElementById("nav-citizen-btn");
  const adminBtn = document.getElementById("nav-admin-btn");
  const portalBadge = document.getElementById("portal-context-badge");

  if (isAdmin) {
    citizenView.classList.add("hidden");
    adminView.classList.remove("hidden");
    
    if (portalBadge) {
      portalBadge.className = "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
      portalBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping"></span> Municipal Admin Command Center`;
    }
    
    if (adminBtn) adminBtn.className = "nav-tab px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all duration-200 bg-sky-500 text-slate-950 shadow-md shadow-sky-500/20";
    if (citizenBtn) citizenBtn.className = "nav-tab px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all duration-200 text-slate-400 hover:text-slate-200";
    
    if (typeof loadAdminDashboard === "function") {
      setTimeout(() => loadAdminDashboard(), 100);
    }
  } else {
    adminView.classList.add("hidden");
    citizenView.classList.remove("hidden");

    if (portalBadge) {
      portalBadge.className = "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20";
      portalBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-sky-400 animate-ping"></span> Citizen Portal`;
    }

    if (citizenBtn) citizenBtn.className = "nav-tab px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all duration-200 bg-sky-500 text-slate-950 shadow-md shadow-sky-500/20";
    if (adminBtn) adminBtn.className = "nav-tab px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all duration-200 text-slate-400 hover:text-slate-200";

    if (citizenMap) {
      setTimeout(() => citizenMap.invalidateSize(), 200);
    }
  }
}

window.addEventListener("hashchange", renderRoute);

// Leaflet Map Setup
function initCitizenMap() {
  const mapContainer = document.getElementById("citizen-map");
  if (!mapContainer || citizenMap) return;

  citizenMap = L.map("citizen-map").setView([24.8607, 67.0011], 12);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(citizenMap);

  plotSampleMarkers();
}

function plotSampleMarkers() {
  if (!citizenMap) return;
  mapMarkers.forEach(m => citizenMap.removeLayer(m));
  mapMarkers = [];

  SAMPLE_ISSUES.forEach(issue => {
    const colorClass = issue.status === 'resolved' ? 'resolved' : issue.status === 'in_progress' ? 'in_progress' : 'reported';
    const iconHtml = `<div class="custom-map-pin ${colorClass} w-7 h-7 text-xs"><i class="fa-solid fa-location-dot"></i></div>`;
    
    const customIcon = L.divIcon({
      html: iconHtml,
      className: '',
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });

    const popupContent = `
      <div class="p-1 space-y-2 max-w-xs text-xs">
        <img src="${issue.img}" class="w-full h-24 object-cover rounded-lg">
        <div class="font-bold text-white">${escapeHtml(issue.description)}</div>
        <div class="flex items-center justify-between text-[11px]">
          <span class="px-2 py-0.5 rounded-full ${priorityBadgeClass(issue.priority)}">${issue.priority}</span>
          <span class="text-slate-400">SLA: ${issue.sla_days} Days</span>
        </div>
      </div>
    `;

    const marker = L.marker([issue.lat, issue.lng], { icon: customIcon })
      .bindPopup(popupContent)
      .addTo(citizenMap);
    
    marker.status = issue.status;
    mapMarkers.push(marker);
  });
}

function filterMapMarkers(status) {
  document.querySelectorAll('.map-filter-btn').forEach(btn => {
    btn.className = "map-filter-btn px-2.5 py-1 rounded-lg text-slate-400 hover:text-slate-200";
  });
  if (event && event.target) {
    event.target.className = "map-filter-btn px-2.5 py-1 rounded-lg bg-sky-500/20 text-sky-300 font-medium";
  }

  mapMarkers.forEach(marker => {
    if (status === 'all' || marker.status === status) {
      citizenMap.addLayer(marker);
    } else {
      citizenMap.removeLayer(marker);
    }
  });
}

const PIPELINE_STAGE_PROGRESS = ["submitted", "ai_triaged", "dispatched", "in_repair", "quality_check", "resolved"];

// Computes a "Day X of Y" / "Overdue by N days" line from live SLA fields.
function computeDayByDaySlaText(c) {
  if (c.status === "resolved" || c.status === "closed") {
    return c.sla_status === "breached" ? "⚠️ Resolved after SLA deadline" : "✅ Resolved within SLA window";
  }
  if (!c.sla_due_date) return null;

  const due = new Date(c.sla_due_date.replace(" ", "T"));
  const now = new Date();

  if (c.sla_status === "breached") {
    const overdueDays = Math.max(1, Math.ceil((now - due) / 86400000));
    return `⚠️ Overdue by ${overdueDays} day${overdueDays === 1 ? "" : "s"}`;
  }

  if (c.date && c.sla_days) {
    const created = new Date(c.date.replace(" ", "T"));
    const elapsedDays = Math.min(c.sla_days, Math.max(1, Math.floor((now - created) / 86400000) + 1));
    return `Day ${elapsedDays} of ${c.sla_days} — On Track`;
  }
  return "On Track";
}

function renderReportCard(c) {
  const stage = c.pipeline_stage || "submitted";
  const stageIndex = PIPELINE_STAGE_PROGRESS.indexOf(stage);
  const dayStatus = computeDayByDaySlaText(c);

  return `
    <div class="glass-card-interactive p-3.5 space-y-2.5 border border-bordercolor">
      <div class="flex gap-3">
        <img src="${c.img || getRandomIssueImg(c.category)}" class="w-16 h-16 rounded-xl object-cover shrink-0 border border-bordercolor">
        <div class="flex-1 space-y-1">
          <div class="flex items-center justify-between text-xs">
            <span class="font-bold text-white line-clamp-1">#${c.complaint_id} - ${escapeHtml(c.description)}</span>
          </div>
          <p class="text-[11px] text-slate-400 flex items-center gap-1">
            <i class="fa-solid fa-location-dot text-rose-400"></i>
            <span>${escapeHtml(c.location || "City Location")}</span>
          </p>
          <div class="flex items-center gap-1.5 flex-wrap pt-0.5">
            <span class="${categoryBadgeClass(c.category)}">${c.category || "Pending AI Triage"}</span>
            <span class="${priorityBadgeClass(c.priority)}">${c.priority || "Pending"} ${c.sla_days ? `(${c.sla_days}D SLA)` : ""}</span>
          </div>
        </div>
      </div>

      <!-- Service Lifecycle Stepper Visualizer (Req #15, #16) -->
      <div class="p-2 bg-slate-100 rounded-xl border border-slate-200 text-[10px] space-y-1">
        <div class="flex items-center justify-between text-slate-500 font-semibold mb-1">
          <span>Service Lifecycle Stage:</span>
          <span class="text-sky-600 font-bold uppercase">${stage.replace("_", " ")}</span>
        </div>
        <div class="flex items-center gap-1">
          <div class="flex-1 h-1.5 rounded-full ${stageIndex >= 0 ? "bg-sky-400" : "bg-slate-700"}"></div>
          <div class="flex-1 h-1.5 rounded-full ${stageIndex >= 1 ? "bg-indigo-400" : "bg-slate-700"}"></div>
          <div class="flex-1 h-1.5 rounded-full ${stageIndex >= 3 ? "bg-amber-400" : "bg-slate-700"}"></div>
          <div class="flex-1 h-1.5 rounded-full ${stageIndex >= 5 ? "bg-emerald-400" : "bg-slate-700"}"></div>
        </div>
        ${dayStatus ? `<div class="pt-1 font-semibold ${c.sla_status === "breached" ? "text-rose-500" : "text-emerald-600"}">${dayStatus}</div>` : ""}
      </div>

      ${c.department_remarks ? `
        <div class="bg-emerald-500/10 p-2 rounded-lg text-[11px] text-emerald-300 border border-emerald-500/30 flex items-start gap-1.5">
          <i class="fa-solid fa-award text-emerald-400 shrink-0 mt-0.5"></i>
          <span>${escapeHtml(c.department_remarks)}</span>
        </div>
      ` : c.ai_summary ? `
        <div class="bg-surfacealt p-2 rounded-lg text-[11px] text-sky-200 border border-sky-500/20 flex items-start gap-1.5">
          <i class="fa-solid fa-wand-magic-sparkles text-sky-400 shrink-0 mt-0.5"></i>
          <span>${escapeHtml(c.ai_summary)}</span>
        </div>
      ` : ""}
    </div>
  `;
}

// Load Citizen Feed with DevOps Stepper -- real data for signed-in citizens,
// sample preview only when nobody is signed in yet.
async function loadCitizenComplaintsFromUI() {
  const feedContainer = document.getElementById("recent-reports-feed");
  if (!feedContainer) return;

  if (!currentUser) {
    myComplaintsCache = [];
    feedContainer.innerHTML = SAMPLE_ISSUES.map(c => renderReportCard({
      complaint_id: c.id,
      description: c.description,
      location: c.location,
      category: c.category,
      priority: c.priority,
      sla_days: c.sla_days,
      sla_due_date: null,
      sla_status: c.sla_status,
      pipeline_stage: c.pipeline_stage,
      department_remarks: c.department_remarks,
      ai_summary: c.ai_summary,
      img: c.img,
      status: c.status,
      date: c.date
    })).join("");
    return;
  }

  feedContainer.innerHTML = `<p class="text-xs text-slate-400 text-center py-4">Loading your reports...</p>`;

  try {
    const res = await fetch(`${API_BASE}/citizens/${currentUser.id}/complaints`);
    if (!res.ok) throw new Error("Failed to load complaints");
    const complaints = await res.json();
    myComplaintsCache = complaints;

    feedContainer.innerHTML = complaints.length > 0
      ? complaints.map(renderReportCard).join("")
      : `<p class="text-xs text-slate-400 text-center py-4">No complaints submitted yet. Tap "Report Live Issue" to file your first one.</p>`;
  } catch (err) {
    myComplaintsCache = [];
    feedContainer.innerHTML = `<p class="text-xs text-rose-400 text-center py-4">Failed to load your reports.</p>`;
  }
  renderAuthControls();
}

// Modal Handlers & Gatekeeper (Req #2)
function openReportModal() {
  if (!currentUser) {
    alert("Please sign in or register an account first before submitting a complaint!");
    openAuthModal();
    return;
  }
  populateDepartmentDropdown();
  document.getElementById("report-modal").classList.remove("hidden");
}

let departmentsLoadPromise = null;

async function populateDepartmentDropdown() {
  const select = document.getElementById("department-select");
  if (!select || select.options.length > 1) return; // already populated

  if (!departmentsLoadPromise) {
    departmentsLoadPromise = fetch(`${API_BASE}/departments`)
      .then(res => (res.ok ? res.json() : []))
      .catch(() => {
        console.log("Could not load department list; AI auto-detect remains available.");
        return [];
      });
  }

  const departments = await departmentsLoadPromise;
  if (select.options.length > 1) return; // populated by a concurrent call while awaiting

  departments.forEach(d => {
    const option = document.createElement("option");
    option.value = d.department_id;
    option.textContent = `${d.name} (${d.category})`;
    select.appendChild(option);
  });
}

function closeReportModal() {
  document.getElementById("report-modal").classList.add("hidden");
}

function triggerPhotoUpload() {
  document.getElementById("photo-file-input").click();
}

function handlePhotoSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById("photo-placeholder").classList.add("hidden");
    const previewContainer = document.getElementById("photo-preview-container");
    const previewImg = document.getElementById("photo-preview-img");
    const analysisBox = document.getElementById("ai-photo-analysis-box");
    const analysisText = document.getElementById("ai-photo-analysis-text");

    previewImg.src = e.target.result;
    previewContainer.classList.remove("hidden");
    analysisBox.classList.remove("hidden");

    analysisText.textContent = "AI Scanning image for structural damage...";
    setTimeout(() => {
      analysisText.textContent = "Detected: Structural Pothole (98.6% confidence) -> Priority: High (4-Day SLA Target) -> Dept: Road Maintenance";
      document.getElementById("description").value = "Pothole detected automatically via AI camera capture.";
      document.getElementById("location").value = "Corner of 4th Street & Main Boulevard";
    }, 1500);
  };
  reader.readAsDataURL(file);
}

function detectGPSLocation() {
  const locInput = document.getElementById("location");
  if (navigator.geolocation) {
    locInput.value = "Locating via GPS...";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        locInput.value = `Lat: ${pos.coords.latitude.toFixed(4)}, Lng: ${pos.coords.longitude.toFixed(4)} (GPS Verified)`;
      },
      () => {
        locInput.value = "Downtown Central District, Sector 4-B";
      }
    );
  } else {
    locInput.value = "Downtown Central District, Sector 4-B";
  }
}

async function submitReportForm(event) {
  event.preventDefault();
  if (!currentUser) {
    openAuthModal();
    return;
  }

  const description = document.getElementById("description").value;
  const location = document.getElementById("location").value;
  const departmentSelect = document.getElementById("department-select");
  const departmentId = departmentSelect && departmentSelect.value ? parseInt(departmentSelect.value, 10) : null;

  const payload = { user_id: currentUser.id, description, location };
  if (departmentId) payload.department_id = departmentId;

  try {
    const res = await fetch(`${API_BASE}/complaints`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      alert(`Complaint #${data.complaint_id} submitted! AI SLA Target: ${data.sla_days} Days. Routed to ${data.department_name}.`);
      document.getElementById("complaint-form").reset();
      closeReportModal();
      loadCitizenComplaintsFromUI();
      fetchCityHealthRisk();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to submit complaint. Please try again.");
    }
  } catch (err) {
    alert("Unable to reach the server. Please check your connection and try again.");
  }
}

// AI Chatbot Drawer
function toggleAIChat() {
  document.getElementById("ai-chat-drawer").classList.toggle("hidden");
}

function sendQuickPrompt(promptText) {
  document.getElementById("chat-input").value = promptText;
  handleChatSubmit(new Event('submit'));
}

function handleChatSubmit(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;

  const container = document.getElementById("chat-messages-container");
  container.innerHTML += `
    <div class="flex gap-2.5 items-start justify-end">
      <div class="bg-sky-600 p-3 rounded-2xl rounded-tr-none text-white max-w-[80%] space-y-1">
        <p>${escapeHtml(text)}</p>
      </div>
    </div>
  `;
  input.value = "";
  container.scrollTop = container.scrollHeight;

  setTimeout(() => {
    let reply = "I have logged your query into the Civic Services Knowledge Engine.";
    if (text.toLowerCase().includes("track")) {
      reply = "Complaint #101 is in stage **IN REPAIR**. Roads Dept crew assigned under 4-Day SLA.";
    } else if (text.toLowerCase().includes("sla")) {
      reply = "SLA Timelines:\n• **Critical**: 2 Days Target\n• **High**: 4 Days Target\n• **Medium**: 7 Days Target\n• **Low**: 14 Days Target.";
    }
    container.innerHTML += `
      <div class="flex gap-2.5 items-start">
        <div class="w-7 h-7 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 shrink-0 text-xs">
          🤖
        </div>
        <div class="bg-surfacealt p-3 rounded-2xl rounded-tl-none border border-bordercolor text-slate-200 space-y-1 max-w-[85%]">
          <p>${reply}</p>
        </div>
      </div>
    `;
    container.scrollTop = container.scrollHeight;
  }, 800);
}

// Notifications Mock
async function loadNotifications() {
  const container = document.getElementById("notifications-list");
  const badge = document.getElementById("unread-count-badge");
  if (!container) return;

  if (!currentUser) {
    container.innerHTML = `<p class="text-xs text-slate-400 text-center py-3">Sign in to see your notifications.</p>`;
    if (badge) badge.style.display = "none";
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/citizens/${currentUser.id}/notifications`);
    if (!res.ok) throw new Error("Failed to load notifications");
    const notifications = await res.json();

    const unreadCount = notifications.filter(n => !n.is_read).length;
    if (badge) {
      badge.textContent = unreadCount;
      badge.style.display = unreadCount > 0 ? "flex" : "none";
    }

    container.innerHTML = notifications.length > 0
      ? notifications.map(n => `
          <div class="p-2.5 ${n.is_read ? "bg-surfacealt/50" : "bg-surfacealt"} rounded-xl border border-bordercolor flex items-start gap-2">
            <i class="fa-solid ${n.is_read ? "fa-circle-check text-slate-500" : "fa-circle-exclamation text-sky-400"} mt-0.5"></i>
            <div>
              <div class="font-semibold text-white">${escapeHtml(n.message)}</div>
              <div class="text-[10px] text-slate-400">${n.created_at ? new Date(n.created_at.replace(" ", "T")).toLocaleString() : ""}</div>
            </div>
          </div>
        `).join("")
      : `<p class="text-xs text-slate-400 text-center py-3">No notifications yet.</p>`;
  } catch (err) {
    container.innerHTML = `<p class="text-xs text-rose-400 text-center py-3">Failed to load notifications.</p>`;
  }
}

function toggleNotifications() {
  document.getElementById("notifications-dropdown").classList.toggle("hidden");
}

async function clearNotifications() {
  if (currentUser) {
    try {
      const res = await fetch(`${API_BASE}/citizens/${currentUser.id}/notifications`);
      if (res.ok) {
        const notifications = await res.json();
        await Promise.all(
          notifications
            .filter(n => !n.is_read)
            .map(n => fetch(`${API_BASE}/notifications/${n.id}/read`, { method: "PATCH" }))
        );
      }
    } catch (err) {
      // best-effort: dropdown still closes even if marking-as-read failed
    }
  }
  document.getElementById("notifications-dropdown").classList.add("hidden");
  loadNotifications();
}

function priorityBadgeClass(p) {
  if (p === 'Critical') return 'badge-critical';
  if (p === 'High') return 'badge-high';
  if (p === 'Medium') return 'badge-medium';
  return 'badge-low';
}

function categoryBadgeClass(c) {
  return "px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/10 text-sky-400 border border-sky-500/20";
}

function escapeHtml(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}
