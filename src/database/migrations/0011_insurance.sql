-- СТРАХОВКА МАШИНАГА: each insurer's ОСАГО policy template, registered once
-- and filled per car. The four the office already works with are seeded from
-- templates/strahovka/ on first run.
CREATE TABLE IF NOT EXISTS insurance_templates (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    internal_code TEXT NOT NULL UNIQUE,
    insurer       TEXT,
    firm          TEXT,
    template_path TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insurance_templates_status
    ON insurance_templates (status);
