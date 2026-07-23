# OFIS — Progress

## Current phase
**Phase 1 — Project Foundation** ✅ complete (see DEVELOPMENT_ROADMAP.md).

## Done
- **Phase 0 — Design**: `ARCHITECTURE.md` — full technical design binding the 16
  spec files + the real МВД Приложение № 7 form into a buildable plan (layers,
  folder map, domain models, DB schema, OCR/AI contract, PDF field-mapping &
  calibration system, phase-1 deliverable).
- **Phase 1 — Foundation**:
  - Package skeleton (`src/{config,common,domain,ui,controllers,services,ocr,ai,pdf,database,utils}`).
  - `common/`: typed error hierarchy, `Result` type, DI container, structured
    logging (rotating file in AppData), Qt worker (`run_async`).
  - `config/`: Windows-aware paths (AppData for data, read-only app dir),
    constants, `SettingsService` (typed, DB-backed, defaults + validation).
  - `domain/`: Pydantic models from the real form — `Passport`, `Patent`,
    `Registration`, `MigrationCard`, `Company`, `Employee`, `OcrResult` + enums.
  - `database/`: SQLite (WAL + FK), forward-only migration runner, `0001_init.sql`
    (settings/logs/companies/schema_migrations), `SettingsRepository`.
  - `ui/`: themed `MainWindow` shell (sidebar nav + stacked placeholder views +
    status bar), runtime light/dark `.qss`, no-restart i18n (ru/uz/en).
  - `app.py`: composition root — builds DI graph, runs migrations, shows window.
  - `templates/mvd_prilozhenie_7/`: blank 5-page template + `meta.json` (sha256)
    + `mapping.v1.json` schema skeleton (coordinates pending Phase 8 calibration).
  - `tests/`: domain validation, DB migration idempotency + settings round-trip,
    **architecture import-lint** enforcing the dependency rule. **9/9 green.**
  - Tooling: `pyproject.toml` (ruff + mypy strict + pytest), `requirements.txt`,
    `.gitignore`, `.env.example`.

## Verified
- `pytest tests/unit/test_domain.py test_settings_and_db.py test_architecture.py` → 9 passed.
- `build_container()` boots headless (migrations apply, settings resolve).
- Note: GUI (`app.py` → window) verified by construction; run on Windows/desktop
  with a display (`python -m src.app`) — this dev box is headless Linux.

## Phase 8 (partial) — PDF Engine + auto-calibration ✅
- `src/pdf/`: `mapping.py` (versioned FieldMapping, Pydantic), `formatters.py`
  (transforms + date parts), `renderers.py` (grid/text/mark, Cyrillic-accurate
  widths), `engine.py` (fill a template from `{field_id: value}`, embeds a
  Cyrillic font, never mutates the template, deterministic), `calibrate.py`
  (**OpenCV auto-detection** of character-grid rows → x0/pitch/max_cells in points).
- `resources/fonts/OfisSans` = Liberation Sans (OFL, Arial-metric, Cyrillic).
- `scripts/calibrate_mvd.py` builds `mapping.v1.json` from detection (11 fields).
- Proven end-to-end: engine fills the real МВД form, inserted Cyrillic is real
  page text; tests 11/11.
- FINDING: auto-detection is corrupted on the *filled* sample (printed glyphs
  add false vertical strokes) — clean rows (passport №, dates) align pixel-exact,
  text rows drift. **Needs the BLANK бланк** to calibrate all rows cleanly.

## Phases 2–7 — Working app (manual mode end-to-end) ✅
- **Companies**: CompanyRepository + CompanyService (store/list, per-company
  template import); default ИП ГОРДИЕНКО seeded on first run.
- **Generation**: GenerationService — data → build_values → fill company template
  → save output/<company>/<SURNAME>.pdf (deduped) → advance 3-digit reg counter.
- **Business rules** (field_extractor): patent expiry = issue+1yr, ФИО+гражданство,
  должность only when custom (else pre-printed default kept via engine whiteout).
- **AI/OCR**: IAiProvider + Gemini adapter (keyed from Settings, lazy import) +
  FakeProvider + AiManager (fallback → "use manual fill"); OcrService maps
  passport/patent images → validated models.
- **Manual mode**: 16-field labeled table (manual_entry) → build_employee → same
  engine. Offline fallback, needs no key.
- **UI (PySide6)**: MainWindow shell + real ProcessView (company/date/должность,
  AI upload + RUN, «Qo'lda to'ldirish»), CompaniesView (list + add w/ template),
  SettingsView (Gemini key, theme live, language, output folder). Wired via
  ProcessController on worker threads (responsive).
- **Verified**: full app constructs offscreen (6 views); manual generation
  end-to-end produces ЮЛДАШЕВ_БЕКЗОД.pdf; all 16 fields correct. Tests 24/24.
- **AI**: plug a Gemini key in Settings → RUN reads passport+patent automatically.

## Next (Core Infrastructure + Database)
- Flesh out repositories (company, employee, documents, history, generated).
- `CompanyService` + the Companies screen (Phase 5) so a real company/template
  can be registered.
- Then Phase 6 OCR pipeline scaffolding behind `IAiProvider` with a fake provider.

## Notes
- Dev machine is headless Linux; EXE build (PyInstaller, Phase 14) and live GUI
  runs happen on Windows.
- One template today (МВД Приложение № 7). Planned next forms: уведомление по
  месту пребывания (регистрация), трудовой договор — each is just a new
  `templates/<name>/{template.pdf, mapping.vN.json, meta.json}`, no code change.
