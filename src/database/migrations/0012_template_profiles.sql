-- A template the office uploaded and the program studied: the map of where each
-- worker value goes, as the operator confirmed it. Keyed by the file's content
-- hash, so the same document is never studied twice.
CREATE TABLE IF NOT EXISTS template_profiles (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    file_hash     TEXT NOT NULL UNIQUE,
    template_path TEXT NOT NULL,
    kind          TEXT NOT NULL,
    map_json      TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_template_profiles_name ON template_profiles (name);
