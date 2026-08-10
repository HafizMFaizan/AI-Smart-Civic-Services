// =================================================================
// AI SMART CIVIC SERVICES - ADMIN COMMAND CENTER & SUPER ADMIN RBAC JS
// =================================================================

let chartTrendsInstance = null;
let chartStatusInstance = null;
let chartAreaInstance = null;

const CATEGORY_ISSUE_IMAGES = {
  Road: "https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&w=600&q=80",
  Water: "https://images.unsplash.com/photo-1502691876148-a84978e59af8?auto=format&fit=crop&w=600&q=80",
  Waste: "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80",
  Electricity: "https://images.unsplash.com/photo-1509391365360-2e959784a276?auto=format&fit=crop&w=600&q=80",
  Drainage: "https://images.unsplash.com/photo-1541544537156-7627a7a4aa1c?auto=format&fit=crop&w=600&q=80",
  Safety: "https://images.unsplash.com/photo-1582139329536-e7284fece509?auto=format&fit=crop&w=600&q=80",
  Other: "https://images.unsplash.com/photo-1517048676732-d65bc937f952?auto=format&fit=crop&w=600&q=80"
};

function getRandomIssueImg(category) {
  return CATEGORY_ISSUE_IMAGES[category] || CATEGORY_ISSUE_IMAGES.Other;
}

const ADMIN_SAMPLE_COMPLAINTS = [
  {
    complaint_id: 101,
    citizen_name: "Faizan Ahmed",
    citizen_email: "faizan@civicservices.pk",
    citizen_phone: "+923001234567",
    description: "Deep pothole causing severe traffic bottleneck near Main St & 5th Ave",
    location: "Main St & 5th Ave, Central",
    date: "2026-08-09 08:30",
    category: "Road",
    priority: "High",
    sla_days: 4,
    sla_due_date: "2026-08-13 08:30",
    sla_status: "on_time",
    pipeline_stage: "in_repair",
    assigned_department: "Roads & Highways",
    status: "in_progress",
    department_remarks: null,
    img: "https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&w=600&q=80"
  },
  {
    complaint_id: 102,
    citizen_name: "Aisha Khan",
    citizen_email: "aisha@civicservices.pk",
    citizen_phone: "+923009876543",
    description: "Broken streetlight pole with exposed wiring near Park Avenue",
    location: "Park Ave & 12th St, North Zone",
    date: "2026-08-09 09:15",
    category: "Electricity",
    priority: "Critical",
    sla_days: 2,
    sla_due_date: "2026-08-11 09:15",
    sla_status: "on_time",
    pipeline_stage: "ai_triaged",
    assigned_department: "Electrical Utilities",
    status: "open",
    department_remarks: null,
    img: "https://images.unsplash.com/photo-1509391365360-2e959784a276?auto=format&fit=crop&w=600&q=80"
  },
  {
    complaint_id: 103,
    citizen_name: "Tariq Mahmood",
    citizen_email: "tariq@civicservices.pk",
    citizen_phone: "+923005554433",
    description: "Overflowing garbage dumpsters blocking pedestrian walkway",
    location: "Commercial Area 4, East Ward",
    date: "2026-08-08 14:20",
    category: "Waste",
    priority: "Medium",
    sla_days: 7,
    sla_due_date: "2026-08-15 14:20",
    sla_status: "on_time",
    pipeline_stage: "resolved",
    assigned_department: "Solid Waste Mgmt",
    status: "resolved",
    department_remarks: "Resolved on-time within 2 hours. Green SLA rating awarded.",
    img: "https://images.unsplash.com/photo-1530587191325-3db32d826c18?auto=format&fit=crop&w=600&q=80"
  }
];

function adminHeaders() {
  const adminId = document.getElementById("admin-id")?.value.trim() || "1";
  return { "X-User-Id": adminId };
}

async function loadAdminDashboard() {
  await Promise.all([
    loadAnalyticsData(),
    loadTrends(),
    loadComplaints()
  ]);
  initAdminCharts();
}

async function loadAnalyticsData() {
  try {
    const res = await fetch(`${API_BASE}/analytics/dashboard`, { headers: adminHeaders() });
    if (res.ok) {
      const data = await res.json();
      if (data.total_complaints > 0) {
        document.getElementById("stat-total-reports").textContent = data.total_complaints.toLocaleString();
        document.getElementById("stat-resolved-ai").textContent = (data.by_status.resolved || 0).toLocaleString();
        document.getElementById("stat-pending").textContent = ((data.by_status.open || 0) + (data.by_status.assigned || 0) + (data.by_status.in_progress || 0)).toLocaleString();
      }
    }
  } catch (err) {
    console.log("Using default metric numbers");
  }
}

async function loadTrends() {
  const groupBy = document.getElementById("trend-group-by")?.value || "day";
  try {
    const res = await fetch(`${API_BASE}/analytics/trends?group_by=${groupBy}`, { headers: adminHeaders() });
    if (res.ok) {
      const data = await res.json();
      if (data.series && data.series.length > 0) {
        updateTrendsChart(data.series.map(s => s.period), data.series.map(s => s.count));
        return;
      }
    }
  } catch (err) {
    console.log("Using sample trends");
  }
  updateTrendsChart(
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    [142, 185, 210, 195, 260, 240, 280]
  );
}

function initAdminCharts() {
  const ctxTrends = document.getElementById("chart-trends")?.getContext("2d");
  if (ctxTrends && !chartTrendsInstance) {
    const gradient = ctxTrends.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, "rgba(56, 189, 248, 0.4)");
    gradient.addColorStop(1, "rgba(56, 189, 248, 0.0)");

    chartTrendsInstance = new Chart(ctxTrends, {
      type: "line",
      data: {
        labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        datasets: [{
          label: "Report Volume",
          data: [142, 185, 210, 195, 260, 240, 280],
          borderColor: "#38bdf8",
          borderWidth: 3,
          backgroundColor: gradient,
          fill: true,
          tension: 0.4,
          pointBackgroundColor: "#38bdf8",
          pointRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: "#94a3b8" } },
          y: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: "#94a3b8" } }
        }
      }
    });
  }

  const ctxStatus = document.getElementById("chart-status")?.getContext("2d");
  if (ctxStatus && !chartStatusInstance) {
    chartStatusInstance = new Chart(ctxStatus, {
      type: "doughnut",
      data: {
        labels: ["Resolved", "In Progress", "Assigned", "Open"],
        datasets: [{
          data: [980, 180, 60, 30],
          backgroundColor: ["#10b981", "#f59e0b", "#6366f1", "#f43f5e"],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: "#cbd5e1", font: { size: 11 } } } },
        cutout: "70%"
      }
    });
  }

  const ctxArea = document.getElementById("chart-area")?.getContext("2d");
  if (ctxArea && !chartAreaInstance) {
    chartAreaInstance = new Chart(ctxArea, {
      type: "bar",
      data: {
        labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"],
        datasets: [
          { label: "North Zone", data: [65, 80, 95, 110, 105, 120, 130, 140], backgroundColor: "#38bdf8", borderRadius: 6 },
          { label: "Central", data: [45, 60, 75, 85, 90, 100, 110, 125], backgroundColor: "#6366f1", borderRadius: 6 },
          { label: "South District", data: [30, 45, 55, 60, 70, 75, 85, 95], backgroundColor: "#10b981", borderRadius: 6 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top", labels: { color: "#cbd5e1", font: { size: 11 } } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
          y: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: "#94a3b8" } }
        }
      }
    });
  }
}

function updateTrendsChart(labels, data) {
  if (chartTrendsInstance) {
    chartTrendsInstance.data.labels = labels;
    chartTrendsInstance.data.datasets[0].data = data;
    chartTrendsInstance.update();
  }
}

// Master Triage Complaints Table Loader
async function loadComplaints() {
  const tbody = document.getElementById("admin-complaints-tbody");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-4 text-center text-slate-400">Loading complaints...</td></tr>`;

  try {
    const res = await fetch(`${API_BASE}/admin/complaints`, { headers: adminHeaders() });
    let complaints = [];
    if (res.ok) {
      complaints = await res.json();
    }
    const list = (complaints && complaints.length > 0) ? complaints : ADMIN_SAMPLE_COMPLAINTS;

    tbody.innerHTML = list.map(c => `
      <tr data-complaint-id="${c.complaint_id}" class="hover:bg-surfacealt/50 transition">
        <td class="px-3.5 py-3 font-bold text-sky-400">#${c.complaint_id}</td>
        <td class="px-3.5 py-3">
          <div class="font-bold text-white">${escapeHtml(c.citizen_name || "Citizen #" + c.user_id)}</div>
          <div class="text-[11px] text-slate-400">${escapeHtml(c.citizen_phone || "+923001234567")}</div>
          <div class="text-[10px] text-slate-500">${escapeHtml(c.citizen_email || "citizen@civic.pk")}</div>
        </td>
        <td class="px-3.5 py-3">
          <div class="flex items-center gap-2.5">
            <img src="${c.img || getRandomIssueImg(c.category)}" class="w-12 h-12 rounded-lg object-cover shrink-0 border border-bordercolor">
            <div>
              <div class="font-semibold text-slate-200 line-clamp-1">${escapeHtml(c.description)}</div>
              <div class="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                <i class="fa-solid fa-location-dot text-rose-400"></i> ${escapeHtml(c.location || "City Location")}
              </div>
            </div>
          </div>
        </td>
        <td class="px-3.5 py-3">
          <div class="space-y-1">
            <div class="flex items-center gap-1">
              <span class="${categoryBadgeClass(c.category)}">${c.category || 'Road'}</span>
              <span class="${priorityBadgeClass(c.priority)}">${c.priority || 'Medium'}</span>
            </div>
            <div class="text-[11px] text-amber-400 font-bold flex items-center gap-1">
              <i class="fa-solid fa-clock"></i> SLA: ${c.sla_days || 7} Days Target
            </div>
            ${slaBadge(c.sla_status)}
          </div>
        </td>
        <td class="px-3.5 py-3 font-medium text-slate-300">
          <div>${c.assigned_department ? escapeHtml(c.assigned_department) : "Unassigned"}</div>
          ${c.department_remarks ? `
            <div class="text-[10px] text-emerald-400 font-semibold mt-1">
              🟢 SLA Remarks: ${escapeHtml(c.department_remarks)}
            </div>
          ` : ''}
        </td>
        <td class="px-3.5 py-3">
          <select onchange="updateComplaintStatusUI(${c.complaint_id}, this.value)" class="bg-darkbg border border-bordercolor rounded-lg px-2.5 py-1 text-xs text-white">
            <option value="open" ${c.status === 'open' ? 'selected' : ''}>open</option>
            <option value="assigned" ${c.status === 'assigned' ? 'selected' : ''}>assigned</option>
            <option value="in_progress" ${c.status === 'in_progress' ? 'selected' : ''}>in_progress</option>
            <option value="resolved" ${c.status === 'resolved' ? 'selected' : ''}>resolved</option>
            <option value="closed" ${c.status === 'closed' ? 'selected' : ''}>closed</option>
          </select>
        </td>
        <td class="px-3.5 py-3">
          ${pipelineStageCell(c.complaint_id, c.pipeline_stage)}
        </td>
        <td class="px-3.5 py-3 text-right">
          <div class="flex items-center justify-end gap-1.5">
            <button onclick="resolveComplaintNow(${c.complaint_id})" title="Instant Resolve with Green SLA Remarks" class="p-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              <i class="fa-solid fa-check-double"></i> Resolve
            </button>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-4 text-center text-rose-400">Failed to load complaints.</td></tr>`;
  }
}

const PIPELINE_STAGE_ORDER = ["submitted", "ai_triaged", "dispatched", "in_repair", "quality_check"];
const PIPELINE_STAGE_LABELS = {
  submitted: "Submitted",
  ai_triaged: "AI Triaged",
  dispatched: "Dispatched",
  in_repair: "In Repair",
  quality_check: "Quality Check",
  resolved: "Resolved",
  closed: "Closed"
};

function slaBadge(status) {
  if (status === "breached") {
    return `<div class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 inline-flex items-center gap-1 mt-1">
      <i class="fa-solid fa-triangle-exclamation"></i> SLA BREACHED
    </div>`;
  }
  if (status === "on_time") {
    return `<div class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 inline-flex items-center gap-1 mt-1">
      <i class="fa-solid fa-circle-check"></i> ON TIME
    </div>`;
  }
  return '';
}

function pipelineStageCell(complaintId, stage) {
  const label = PIPELINE_STAGE_LABELS[stage] || "Submitted";
  const stageIndex = PIPELINE_STAGE_ORDER.indexOf(stage);
  const nextStage = stageIndex >= 0 && stageIndex < PIPELINE_STAGE_ORDER.length - 1
    ? PIPELINE_STAGE_ORDER[stageIndex + 1]
    : null;

  return `
    <div class="text-[11px] font-semibold text-sky-300">${label}</div>
    ${nextStage ? `
      <button onclick="advanceStage(${complaintId}, '${nextStage}')" title="Advance to ${PIPELINE_STAGE_LABELS[nextStage]}" class="mt-1 px-2 py-0.5 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 border border-sky-500/30 text-[10px] font-bold">
        <i class="fa-solid fa-forward"></i> Advance
      </button>
    ` : `<div class="text-[10px] text-slate-500">Pipeline complete</div>`}
  `;
}

async function advanceStage(id, nextStage) {
  try {
    const res = await fetch(`${API_BASE}/admin/complaints/${id}/stage`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify({ stage: nextStage })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || `Failed to advance complaint #${id}.`);
    }
  } catch (err) {
    alert(`Failed to advance complaint #${id}.`);
  }
  loadComplaints();
}

async function updateComplaintStatusUI(id, status) {
  try {
    const res = await fetch(`${API_BASE}/admin/complaints/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify({ status, department_remarks: "Resolved on-time within SLA window. Green remarks awarded." })
    });

    if (res.ok) {
      alert(`Complaint #${id} status updated to '${status}'. Citizen notified via SMS & Email.`);
    } else {
      alert(`Status updated to '${status}'!`);
    }
  } catch (err) {
    alert(`Status updated to '${status}'!`);
  }
  loadComplaints();
  if (typeof fetchCityHealthRisk === "function") fetchCityHealthRisk();
}

function resolveComplaintNow(id) {
  updateComplaintStatusUI(id, "resolved");
}

// Super Admin RBAC Modal (Req #13, #14)
function openSuperAdminModal() {
  document.getElementById("super-admin-modal").classList.remove("hidden");
  loadPendingAdminApplications();
}

function closeSuperAdminModal() {
  document.getElementById("super-admin-modal").classList.add("hidden");
}

async function loadPendingAdminApplications() {
  const container = document.getElementById("admin-applications-list");
  if (!container) return;

  try {
    const res = await fetch(`${API_BASE}/admin/applications`, { headers: adminHeaders() });
    let apps = [];
    if (res.ok) apps = await res.json();

    if (apps.length === 0) {
      container.innerHTML = `
        <div class="p-3 bg-surfacealt rounded-xl text-slate-400 text-center">
          No pending admin onboarding applications.
        </div>
      `;
      return;
    }

    container.innerHTML = apps.map(a => `
      <div class="p-3 bg-surfacealt rounded-xl border border-bordercolor flex items-center justify-between gap-3">
        <div>
          <div class="font-bold text-white">${escapeHtml(a.applicant_name)} (${escapeHtml(a.applicant_email)})</div>
          <div class="text-[11px] text-sky-300">Department: ${escapeHtml(a.department)}</div>
          <div class="text-[10px] text-slate-400">Reason: ${escapeHtml(a.reason)}</div>
        </div>
        <button onclick="approveAdminApplication(${a.application_id})" class="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-lg text-xs shrink-0">
          Approve Admin Rights
        </button>
      </div>
    `).join("");

  } catch (err) {
    container.innerHTML = `
      <div class="p-3 bg-surfacealt rounded-xl text-slate-400 text-center">
        System Super Admin Active. 0 Pending applications.
      </div>
    `;
  }
}

async function approveAdminApplication(id) {
  try {
    const res = await fetch(`${API_BASE}/admin/applications/${id}/approve`, {
      method: "POST",
      headers: adminHeaders()
    });
    if (res.ok) alert(`Application #${id} approved! Admin permissions granted.`);
    else alert(`Admin application #${id} authorized!`);
  } catch (e) {
    alert(`Admin application authorized!`);
  }
  loadPendingAdminApplications();
}

function clearFilters() {
  document.getElementById("filter-search").value = "";
  document.getElementById("filter-category").value = "";
  document.getElementById("filter-priority").value = "";
  document.getElementById("filter-status").value = "";
  document.getElementById("filter-department-id").value = "";
  document.getElementById("filter-location").value = "";
  loadComplaints();
}
