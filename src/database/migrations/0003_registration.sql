-- Registration addresses: pre-filled «Уведомление о прибытии» templates.
-- Mirrors `companies` — each row is one address whose block + host ФИО are
-- printed on its template; the program fills only the worker/date boxes.

CREATE TABLE IF NOT EXISTS registration_addresses (
    id               TEXT PRIMARY KEY,
    label            TEXT NOT NULL,
    internal_code    TEXT NOT NULL UNIQUE,
    address_text     TEXT NOT NULL,
    host_fio         TEXT NOT NULL,
    template_path    TEXT NOT NULL,
    template_version TEXT NOT NULL DEFAULT '1',
    status           TEXT NOT NULL DEFAULT 'active',
    notes            TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    archived_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_reg_addr_status ON registration_addresses (status);
CREATE INDEX IF NOT EXISTS idx_reg_addr_label ON registration_addresses (label);
