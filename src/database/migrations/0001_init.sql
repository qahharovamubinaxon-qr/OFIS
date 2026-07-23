-- OFIS initial schema (Phase 1 subset).
-- Later phases add employees/passport_data/patent_data/... via their own
-- numbered migration files. Never edit an applied migration; add a new one.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL,
    module      TEXT NOT NULL,
    message     TEXT NOT NULL,
    stack_trace TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs (created_at);

CREATE TABLE IF NOT EXISTS companies (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    internal_code     TEXT NOT NULL UNIQUE,
    employer_type     TEXT NOT NULL,
    okved             TEXT NOT NULL,
    ogrn              TEXT NOT NULL,
    inn               TEXT NOT NULL,
    address_index     TEXT NOT NULL,
    address_text      TEXT NOT NULL,
    phone             TEXT,
    director_position TEXT NOT NULL,
    director_fio      TEXT NOT NULL,
    logo_path         TEXT,
    template_path     TEXT NOT NULL,
    template_version  TEXT NOT NULL DEFAULT '1',
    status            TEXT NOT NULL DEFAULT 'active',
    notes             TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    archived_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies (status);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies (name);
