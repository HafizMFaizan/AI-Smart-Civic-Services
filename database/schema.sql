-- Enterprise AI Smart Civic Services Database Schema (Phase 1 Upgrade)

PRAGMA foreign_keys = ON;

-- 1. Users Table (Citizens, Admins, Super Admin)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    password_hash TEXT NOT NULL DEFAULT 'pbkdf2:sha256$seeded_hash_no_access',
    role TEXT NOT NULL DEFAULT 'citizen' CHECK (role IN ('citizen', 'admin', 'super_admin')),
    is_verified INTEGER NOT NULL DEFAULT 1 CHECK (is_verified IN (0, 1)),
    phone_verified INTEGER NOT NULL DEFAULT 1 CHECK (phone_verified IN (0, 1)),
    permissions TEXT DEFAULT '[]', -- JSON array of granted RBAC permissions for Admins
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Admin Applications / Onboarding Queue (Super Admin Gatekeeping)
CREATE TABLE IF NOT EXISTS admin_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    requested_role TEXT NOT NULL DEFAULT 'admin',
    department_name TEXT NOT NULL DEFAULT 'General Triage',
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (approved_by) REFERENCES users (id)
);

-- 3. Departments Table
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (
        category IN ('Road', 'Water', 'Waste', 'Electricity', 'Drainage', 'Safety', 'Other')
    ),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Complaints Master Table (DevOps Pipeline & SLA Extensions)
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    department_id INTEGER,
    description TEXT NOT NULL,
    location TEXT,
    category TEXT DEFAULT 'Other',
    priority TEXT DEFAULT 'Medium',
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'assigned', 'in_progress', 'resolved', 'closed')
    ),
    pipeline_stage TEXT NOT NULL DEFAULT 'submitted' CHECK (
        pipeline_stage IN ('submitted', 'ai_triaged', 'dispatched', 'in_repair', 'quality_check', 'resolved', 'closed')
    ),
    sla_days INTEGER NOT NULL DEFAULT 7,
    sla_due_date TIMESTAMP,
    sla_status TEXT DEFAULT 'on_time' CHECK (sla_status IN ('on_time', 'breached')),
    department_remarks TEXT,
    rating_score INTEGER CHECK (rating_score BETWEEN 1 AND 5),
    review_comment TEXT,
    image_url TEXT,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (department_id) REFERENCES departments (id)
);

-- 5. AI Analysis Audit & Triage Table
CREATE TABLE IF NOT EXISTS ai_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (
        category IN ('Road', 'Water', 'Waste', 'Electricity', 'Drainage', 'Safety', 'Other')
    ),
    priority TEXT NOT NULL CHECK (
        priority IN ('Low', 'Medium', 'High', 'Critical')
    ),
    summary TEXT NOT NULL,
    model_name TEXT NOT NULL,
    confidence REAL,
    ai_status TEXT NOT NULL CHECK (ai_status IN ('success', 'failed')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints (id)
);

-- 6. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    complaint_id INTEGER,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (complaint_id) REFERENCES complaints (id)
);

-- 7. SMS Dispatches & Mobile Logs Table
CREATE TABLE IF NOT EXISTS sms_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    complaint_id INTEGER,
    phone TEXT NOT NULL,
    message TEXT NOT NULL,
    sms_type TEXT NOT NULL DEFAULT 'status_update',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (complaint_id) REFERENCES complaints (id)
);

-- 8. Audit Logs Table (AI & System Actions)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    target_id INTEGER,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
