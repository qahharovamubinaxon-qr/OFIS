-- Log of every generated document — powers Dashboard, Archive and Search.

CREATE TABLE IF NOT EXISTS generated_documents (
    id            TEXT PRIMARY KEY,
    company_id    TEXT,
    company_name  TEXT NOT NULL,
    surname       TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    citizenship   TEXT,
    reg_number    INTEGER NOT NULL,
    pdf_path      TEXT NOT NULL,
    form_date     TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gen_surname ON generated_documents (surname);
CREATE INDEX IF NOT EXISTS idx_gen_created ON generated_documents (created_at);
CREATE INDEX IF NOT EXISTS idx_gen_company ON generated_documents (company_id);
