-- СФЕРА module: training professions (сферы) the student can be certified in.
-- Certificate/protocol counters live in `settings` (svera.*), not here.

CREATE TABLE IF NOT EXISTS professions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    note        TEXT,
    grade       INTEGER NOT NULL DEFAULT 5,
    status      TEXT NOT NULL DEFAULT 'active',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_professions_status ON professions (status);
