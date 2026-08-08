const API_BASE = "/api";

const registerForm = document.getElementById("register-form");
const registerStatus = document.getElementById("register-status");

const complaintForm = document.getElementById("complaint-form");
const submitStatus = document.getElementById("submit-status");
const resultBox = document.getElementById("submit-result");
const refreshButton = document.getElementById("refresh-button");
const userIdInput = document.getElementById("view-user-id");
const complaintsList = document.getElementById("complaints-list");
const notificationsList = document.getElementById("notifications-list");

function priorityBadgeClasses(priority) {
  const colors = {
    Low: "bg-green-500/10 text-green-400",
    Medium: "bg-amber-500/10 text-amber-400",
    High: "bg-red-500/10 text-red-400",
    Critical: "bg-red-500/10 text-red-400",
  };
  const color = colors[priority] || "bg-slate-500/20 text-slate-400";
  return `inline-block px-2 py-0.5 rounded-full text-xs font-semibold mr-1 ${color}`;
}

const CATEGORY_BADGE = "inline-block px-2 py-0.5 rounded-full text-xs font-semibold mr-1 bg-sky-400/10 text-sky-400";
const STATUS_BADGE = "inline-block px-2 py-0.5 rounded-full text-xs font-semibold mr-1 bg-slate-500/20 text-slate-400";

function setStatus(el, message, kind) {
  el.textContent = message;
  const color = kind === "error" ? "text-red-400" : kind === "success" ? "text-green-400" : "text-slate-400";
  el.className = `text-sm mt-2 ${color}`;
}

async function registerUser(event) {
  event.preventDefault();
  setStatus(registerStatus, "Registering...", "");

  const payload = {
    name: document.getElementById("register-name").value,
    email: document.getElementById("register-email").value,
    phone: document.getElementById("register-phone").value || null,
  };

  try {
    const response = await fetch(`${API_BASE}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Failed to register.");
    }

    const result = await response.json();
    setStatus(registerStatus, `Registered! Your user ID is ${result.user_id}.`, "success");
    document.getElementById("user-id").value = result.user_id;
    userIdInput.value = result.user_id;
    registerForm.reset();
  } catch (err) {
    setStatus(registerStatus, err.message || "Registration failed.", "error");
  }
}

async function submitComplaint(event) {
  event.preventDefault();
  resultBox.classList.add("hidden");
  setStatus(submitStatus, "Submitting...", "");

  const payload = {
    user_id: Number(document.getElementById("user-id").value),
    description: document.getElementById("description").value,
    location: document.getElementById("location").value || null,
  };

  try {
    const response = await fetch(`${API_BASE}/complaints`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Failed to submit complaint.");
    }

    const result = await response.json();
    setStatus(submitStatus, "Complaint submitted successfully.", "success");
    renderResult(result);
    complaintForm.reset();

    if (userIdInput.value === "") {
      userIdInput.value = String(payload.user_id);
    }
  } catch (err) {
    setStatus(submitStatus, err.message || "Something went wrong.", "error");
  }
}

function renderResult(result) {
  resultBox.innerHTML = `
    <p><strong>Complaint #${result.complaint_id}</strong></p>
    <p class="mt-1">
      <span class="${CATEGORY_BADGE}">${result.category}</span>
      <span class="${priorityBadgeClasses(result.priority)}">${result.priority}</span>
      <span class="${STATUS_BADGE}">AI: ${result.ai_status}</span>
    </p>
    <p class="text-xs text-slate-400 mt-1">Department ID: ${result.department_id !== null ? result.department_id : "not yet assigned"}</p>
  `;
  resultBox.classList.remove("hidden");
}

async function loadCitizenData() {
  const userId = userIdInput.value.trim();
  if (!userId) {
    complaintsList.innerHTML = '<p class="text-slate-400 text-sm">Enter a user ID to view complaints.</p>';
    notificationsList.innerHTML = '<p class="text-slate-400 text-sm">Enter a user ID to view notifications.</p>';
    return;
  }

  await Promise.all([loadCitizenComplaints(userId), loadNotifications(userId)]);
}

async function loadCitizenComplaints(userId) {
  complaintsList.innerHTML = '<p class="text-slate-400 text-sm">Loading...</p>';
  try {
    const response = await fetch(`${API_BASE}/citizens/${encodeURIComponent(userId)}/complaints`);
    if (!response.ok) throw new Error("Failed to load complaints.");
    const complaints = await response.json();

    if (complaints.length === 0) {
      complaintsList.innerHTML = '<p class="text-slate-400 text-sm">No complaints yet.</p>';
      return;
    }

    complaintsList.innerHTML = complaints
      .map(
        (c) => `
        <div class="p-3 rounded-lg bg-surfacealt border border-border">
          <div>${escapeHtml(c.description)}</div>
          ${c.ai_summary ? `<div class="text-xs text-slate-400 mt-1">${escapeHtml(c.ai_summary)}</div>` : ""}
          <div class="text-xs text-slate-400 mt-2">
            <span class="${STATUS_BADGE}">${c.status}</span>
            ${c.category ? `<span class="${CATEGORY_BADGE}">${c.category}</span>` : ""}
            ${c.priority ? `<span class="${priorityBadgeClasses(c.priority)}">${c.priority}</span>` : ""}
            ${c.assigned_department ? `Dept: ${escapeHtml(c.assigned_department)}` : "Dept: unassigned"}
            ${c.location ? ` &middot; ${escapeHtml(c.location)}` : ""}
            ${c.date ? ` &middot; ${escapeHtml(c.date)}` : ""}
          </div>
        </div>`
      )
      .join("");
  } catch (err) {
    complaintsList.innerHTML = `<p class="text-sm text-red-400">${err.message}</p>`;
  }
}

async function loadNotifications(userId) {
  notificationsList.innerHTML = '<p class="text-slate-400 text-sm">Loading...</p>';
  try {
    const response = await fetch(`${API_BASE}/citizens/${encodeURIComponent(userId)}/notifications`);
    if (!response.ok) throw new Error("Failed to load notifications.");
    const notifications = await response.json();

    if (notifications.length === 0) {
      notificationsList.innerHTML = '<p class="text-slate-400 text-sm">No notifications yet.</p>';
      return;
    }

    notificationsList.innerHTML = notifications
      .map(
        (n) => `
        <div class="p-3 rounded-lg bg-surfacealt border border-border" data-notification-id="${n.id}">
          <div class="flex items-start justify-between gap-2">
            <div>${escapeHtml(n.message)}</div>
            ${
              n.is_read
                ? '<span class="text-xs text-slate-500 shrink-0">Read</span>'
                : '<button type="button" class="mark-read-btn shrink-0 text-xs bg-surface border border-border rounded px-2 py-1 hover:bg-slate-600">Mark read</button>'
            }
          </div>
          <div class="text-xs text-slate-400 mt-1">${n.created_at || ""}${n.complaint_id ? ` &middot; Complaint #${n.complaint_id}` : ""}</div>
        </div>`
      )
      .join("");

    document.querySelectorAll(".mark-read-btn").forEach((button) => {
      button.addEventListener("click", onMarkNotificationRead);
    });
  } catch (err) {
    notificationsList.innerHTML = `<p class="text-sm text-red-400">${err.message}</p>`;
  }
}

async function onMarkNotificationRead(event) {
  const container = event.target.closest("[data-notification-id]");
  const notificationId = container.dataset.notificationId;

  try {
    const response = await fetch(`${API_BASE}/notifications/${notificationId}/read`, {
      method: "PATCH",
    });
    if (!response.ok) throw new Error("Failed to mark notification as read.");
    await loadNotifications(userIdInput.value.trim());
  } catch (err) {
    setStatus(submitStatus, err.message || "Failed to mark notification as read.", "error");
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

registerForm.addEventListener("submit", registerUser);
complaintForm.addEventListener("submit", submitComplaint);
refreshButton.addEventListener("click", loadCitizenData);
