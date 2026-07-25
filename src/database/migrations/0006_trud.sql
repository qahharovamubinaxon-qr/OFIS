-- Трудовой-Уведомления module: firms, each holding two template paths.

CREATE TABLE IF NOT EXISTS trud_firms (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    internal_code      TEXT NOT NULL UNIQUE,
    trud_template_path TEXT NOT NULL,
    uved_template_path TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'active',
    notes              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trud_firms_status ON trud_firms (status);
