// API_BASE is declared once in app.js -- both scripts share the same
// top-level scope now that the SPA loads them into a single document.

const adminIdInput = document.getElementById("admin-id");
const loadButton = document.getElementById("load-dashboard");
const adminStatus = document.getElementById("admin-status");
const analyticsStats = document.getElementById("analytics-stats");
const analyticsBreakdowns = document.getElementById("analytics-breakdowns");
const complaintsTableBody = document.querySelector("#complaints-table tbody");

const resolutionTimeStats = document.getElementById("resolution-time-stats");
const trendGroupBySelect = document.getElementById("trend-group-by");
const loadTrendsButton = document.getElementById("load-trends-button");
const trendsList = document.getElementById("trends-list");

const filterSearch = document.getElementById("filter-search");
const filterCategory = document.getElementById("filter-category");
const filterPriority = document.getElementById("filter-priority");
const filterStatus = document.getElementById("filter-status");
const filterDepartmentId = document.getElementById("filter-department-id");
const filterLocation = document.getElementById("filter-location");
const filterDateFrom = document.getElementById("filter-date-from");
const filterDateTo = document.getElementById("filter-date-to");
const applyFiltersButton = document.getElementById("apply-filters-button");
const clearFiltersButton = document.getElementById("clear-filters-button");

const STATUS_OPTIONS = ["open", "assigned", "in_progress", "resolved", "closed"];

const STAT_TILE = "bg-surfacealt border border-border rounded-lg p-3";

function setAdminStatus(message, kind) {
  adminStatus.textContent = message;
  const color = kind === "error" ? "text-red-400" : kind === "success" ? "text-green-400" : "text-slate-400";
  adminStatus.className = `text-sm mt-2 ${color}`;
}

function adminHeaders() {
  const adminId = adminIdInput.value.trim();
  return adminId ? { "X-User-Id": adminId } : {};
}

async function loadDashboard() {
  setAdminStatus("Loading...", "");
  await Promise.all([loadAnalytics(), loadComplaints(), loadResolutionTime(), loadTrends()]);
}

function buildComplaintsQuery() {
  const params = new URLSearchParams();
  if (filterSearch.value.trim()) params.set("search", filterSearch.value.trim());
  if (filterCategory.value) params.set("category", filterCategory.value);
  if (filterPriority.value) params.set("priority", filterPriority.value);
  if (filterStatus.value) params.set("status", filterStatus.value);
  if (filterDepartmentId.value) params.set("department_id", filterDepartmentId.value);
  if (filterLocation.value.trim()) params.set("location", filterLocation.value.trim());
  if (filterDateFrom.value) params.set("date_from", filterDateFrom.value);
  if (filterDateTo.value) params.set("date_to", filterDateTo.value);
  return params.toString();
}

function clearFilters() {
  filterSearch.value = "";
  filterCategory.value = "";
  filterPriority.value = "";
  filterStatus.value = "";
  filterDepartmentId.value = "";
  filterLocation.value = "";
  filterDateFrom.value = "";
  filterDateTo.value = "";
  loadComplaints();
}

async function loadResolutionTime() {
  try {
    const response = await fetch(`${API_BASE}/analytics/resolution-time`, {
      headers: adminHeaders(),
    });
    if (!response.ok) throw new Error("Failed to load resolution time.");
    const data = await response.json();
    resolutionTimeStats.innerHTML = `
      <div class="${STAT_TILE}">
        <div class="text-2xl font-bold">${data.average_hours !== null ? data.average_hours + "h" : "-"}</div>
        <div class="text-xs text-slate-400">Average</div>
      </div>
      <div class="${STAT_TILE}">
        <div class="text-2xl font-bold">${data.minimum_hours !== null ? data.minimum_hours + "h" : "-"}</div>
        <div class="text-xs text-slate-400">Minimum</div>
      </div>
      <div class="${STAT_TILE}">
        <div class="text-2xl font-bold">${data.maximum_hours !== null ? data.maximum_hours + "h" : "-"}</div>
        <div class="text-xs text-slate-400">Maximum</div>
      </div>
      <div class="${STAT_TILE}">
        <div class="text-2xl font-bold">${data.resolved_count}</div>
        <div class="text-xs text-slate-400">Resolved</div>
      </div>
    `;
  } catch (err) {
    resolutionTimeStats.innerHTML = `<p class="text-sm text-red-400">${err.message}</p>`;
  }
}

async function loadTrends() {
  trendsList.innerHTML = '<li class="text-slate-400">Loading...</li>';
  try {
    const groupBy = trendGroupBySelect.value;
    const response = await fetch(
      `${API_BASE}/analytics/trends?group_by=${encodeURIComponent(groupBy)}`,
      { headers: adminHeaders() }
    );
    if (!response.ok) throw new Error("Failed to load trends.");
    const data = await response.json();

    if (data.series.length === 0) {
      trendsList.innerHTML = '<li class="text-slate-400">No data yet.</li>';
      return;
    }

    trendsList.innerHTML = data.series
      .map(
        (point) =>
          `<li class="flex justify-between py-1 border-b border-border"><span>${escapeHtml(point.period)}</span><span>${point.count}</span></li>`
      )
      .join("");
  } catch (err) {
    trendsList.innerHTML = `<li class="text-red-400">${err.message}</li>`;
  }
}

async function loadAnalytics() {
  try {
    const response = await fetch(`${API_BASE}/analytics/dashboard`, { headers: adminHeaders() });
    if (!response.ok) throw new Error("Failed to load analytics.");
    const data = await response.json();
    renderAnalytics(data);
  } catch (err) {
    analyticsStats.innerHTML = `<p class="text-sm text-red-400">${err.message}</p>`;
  }
}

function renderAnalytics(data) {
  analyticsStats.innerHTML = `
    <div class="${STAT_TILE}">
      <div class="text-2xl font-bold">${data.total_complaints}</div>
      <div class="text-xs text-slate-400">Total complaints</div>
    </div>
  `;

  analyticsBreakdowns.innerHTML = [
    ["By Category", data.by_category],
    ["By Priority", data.by_priority],
    ["By Status", data.by_status],
    ["By Department", data.by_department],
  ]
    .map(
      ([title, breakdown]) => `
      <div>
        <h3 class="text-sm font-semibold text-slate-400 mb-1">${title}</h3>
        <ul class="text-sm">
          ${Object.entries(breakdown)
            .map(
              ([key, count]) =>
                `<li class="flex justify-between py-1 border-b border-border"><span>${escapeHtml(key)}</span><span>${count}</span></li>`
            )
            .join("")}
        </ul>
      </div>`
    )
    .join("");
}

async function loadComplaints() {
  complaintsTableBody.innerHTML = '<tr><td colspan="7" class="px-2 py-2">Loading...</td></tr>';
  try {
    const query = buildComplaintsQuery();
    const url = query ? `${API_BASE}/admin/complaints?${query}` : `${API_BASE}/admin/complaints`;
    const response = await fetch(url, { headers: adminHeaders() });

    if (response.status === 401) {
      complaintsTableBody.innerHTML = '<tr><td colspan="7" class="px-2 py-2">Enter an Admin User ID above.</td></tr>';
      setAdminStatus("Missing admin user ID.", "error");
      return;
    }
    if (response.status === 403) {
      complaintsTableBody.innerHTML = '<tr><td colspan="7" class="px-2 py-2">That user is not an admin.</td></tr>';
      setAdminStatus("Not authorized as admin.", "error");
      return;
    }
    if (!response.ok) throw new Error("Failed to load complaints.");

    const complaints = await response.json();
    setAdminStatus(`Loaded ${complaints.length} complaint(s).`, "success");

    if (complaints.length === 0) {
      complaintsTableBody.innerHTML = '<tr><td colspan="7" class="px-2 py-2">No complaints yet.</td></tr>';
      return;
    }

    complaintsTableBody.innerHTML = complaints
      .map(
        (c) => `
        <tr data-complaint-id="${c.complaint_id}" class="border-b border-border">
          <td class="px-2 py-2">${c.complaint_id}</td>
          <td class="px-2 py-2">${escapeHtml(c.citizen_name)}<br><span class="text-xs text-slate-400">${escapeHtml(c.citizen_email)}</span></td>
          <td class="px-2 py-2">${escapeHtml(c.description)}${c.location ? `<br><span class="text-xs text-slate-400">${escapeHtml(c.location)}</span>` : ""}<br><span class="text-xs text-slate-500">${c.date || ""}</span></td>
          <td class="px-2 py-2">${c.category || "-"} / ${c.priority || "-"}<br><span class="text-xs text-slate-400">AI: ${c.ai_status || "-"}</span></td>
          <td class="px-2 py-2">${c.assigned_department ? escapeHtml(c.assigned_department) : "Unassigned"}</td>
          <td class="px-2 py-2">${c.status}</td>
          <td class="px-2 py-2">
            <div class="flex gap-1 items-center">
              <select class="status-select px-2 py-1 bg-surfacealt border border-border rounded text-slate-200 text-sm">
                ${STATUS_OPTIONS.map(
                  (s) => `<option value="${s}" ${s === c.status ? "selected" : ""}>${s}</option>`
                ).join("")}
              </select>
              <button type="button" class="update-status-btn text-xs bg-surfacealt border border-border rounded px-2 py-1 hover:bg-slate-600">Update</button>
            </div>
          </td>
        </tr>`
      )
      .join("");

    document.querySelectorAll(".update-status-btn").forEach((button) => {
      button.addEventListener("click", onUpdateStatus);
    });
  } catch (err) {
    complaintsTableBody.innerHTML = `<tr><td colspan="7" class="px-2 py-2">${err.message}</td></tr>`;
  }
}

async function onUpdateStatus(event) {
  const row = event.target.closest("tr");
  const complaintId = row.dataset.complaintId;
  const newStatus = row.querySelector(".status-select").value;

  setAdminStatus("Updating status...", "");
  try {
    const response = await fetch(`${API_BASE}/admin/complaints/${complaintId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify({ status: newStatus }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Failed to update status.");
    }

    const result = await response.json();
    setAdminStatus(
      `Complaint #${result.complaint_id} updated to '${result.status}'. Citizen notified: ${
        result.notified_user_id !== null ? "yes" : "no"
      }.`,
      "success"
    );
    await loadComplaints();
  } catch (err) {
    setAdminStatus(err.message || "Failed to update status.", "error");
  }
}

// escapeHtml is declared once in app.js -- both scripts share the same
// top-level scope now that the SPA loads them into a single document.

loadButton.addEventListener("click", loadDashboard);
loadTrendsButton.addEventListener("click", loadTrends);
applyFiltersButton.addEventListener("click", loadComplaints);
clearFiltersButton.addEventListener("click", clearFilters);
