# OFIS — Technical Architecture & Design

**HR Document Automation System Pro**
Design document — version 1.0 (produced before any code, per `DEVELOPMENT_ROADMAP.md`)

This document is the single source of truth for *how* the system is built. It
takes the 16 specification files and the real МВД form (Приложение № 7) and
turns them into concrete, buildable engineering decisions: module boundaries,
the database schema, the OCR/AI contracts, and — most importantly — the
**field-mapping and coordinate system** that lets one code base fill unlimited
company templates without touching source code.

Nothing here contradicts the specs; where a spec listed a *what*, this document
commits to a *how*.

---

## 1. Design pillars (non-negotiable)

| Pillar | Concrete rule in this project |
|---|---|
| Clean Architecture | 4 layers, one-way dependencies. UI never imports `services`, `pdf`, `ocr`, or `database`. |
| Provider independence | OCR/AI/PDF/Storage are **interfaces**. Swapping Gemini→OpenAI→Claude is a config change, never a code change. |
| No hardcoded layout | Every PDF field position lives in a JSON mapping file, never in `.py`. |
| Deterministic output | Same validated data + same template version → byte-identical PDF. |
| Fail safe | No bare `except`. Every error is typed, logged, and recoverable. The app never crashes to desktop. |
| Async UI | OCR / AI / PDF run on worker threads. The window never freezes. |
| Testable | Every service has an interface + a fake, so it is unit-testable without a GPU, a network, or a display. |

---

## 2. Layered architecture

```
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION  (src/ui)                                        │
│  PySide6 widgets, windows, dialogs, view-models, themes, i18n  │
│  Knows: controllers. Knows NOTHING about services/db/pdf.      │
└───────────────┬──────────────────────────────────────────────┘
                │ signals / slots (Qt), plain DTOs
┌───────────────▼──────────────────────────────────────────────┐
│  APPLICATION  (src/controllers)                                │
│  Orchestrates use-cases. One controller per screen/workflow.   │
│  Coordinates services; contains NO business logic itself.      │
└───────────────┬──────────────────────────────────────────────┘
                │ calls service interfaces (DI-injected)
┌───────────────▼──────────────────────────────────────────────┐
│  DOMAIN + SERVICES  (src/services, src/domain)                 │
│  Business rules. OCRService, PdfService, CompanyService, …      │
│  Pydantic domain models. Pure Python, no Qt, no SQL.           │
└───────────────┬──────────────────────────────────────────────┘
                │ repository + provider interfaces
┌───────────────▼──────────────────────────────────────────────┐
│  INFRASTRUCTURE  (src/database, src/ocr, src/ai, src/pdf, …)   │
│  SQLite repositories, Gemini/OpenAI clients, PyMuPDF engine,    │
│  filesystem archive, config, logging.                          │
└──────────────────────────────────────────────────────────────┘
```

**Dependency rule (enforced by an import-lint test):**
`ui → controllers → services → {repositories, providers} → {sqlite, filesystem, http}`.
An arrow never points backwards. `domain` (models) is imported by everyone and
imports nothing from the project.

---

## 3. Project structure (concrete)

```
OFIS/
├─ pyproject.toml            # deps, ruff, mypy, pytest config
├─ README.md
├─ CLAUDE.md                 # (from spec) engineering rules
├─ ARCHITECTURE.md           # this file
├─ .env.example              # AI keys placeholders (never committed real)
├─ .gitignore
├─ requirements.txt
├─ build/
│  └─ ofis.spec              # PyInstaller spec (single EXE)
├─ resources/
│  ├─ icons/                 # app + toolbar icons
│  ├─ fonts/                 # Arial/Roboto/Noto (Cyrillic-capable, embedded)
│  ├─ qss/                   # light.qss, dark.qss (Qt stylesheets)
│  └─ i18n/                  # ru.json, uz.json, en.json
├─ templates/                # company PDF templates + their field maps
│  └─ mvd_prilozhenie_7/
│     ├─ template.pdf        # the 5-page МВД form (blank)
│     ├─ mapping.v1.json     # field coordinates (see §8)
│     └─ meta.json           # version, page count, checksum
├─ src/
│  ├─ app.py                 # composition root: builds DI container, shows MainWindow
│  ├─ config/
│  │  ├─ settings_service.py # reads/writes settings (DB-backed)
│  │  ├─ paths.py            # AppData/AppFolder resolution (Windows)
│  │  └─ constants.py
│  ├─ domain/                # Pydantic models — the shared language (§5)
│  │  ├─ employee.py  passport.py  patent.py  registration.py
│  │  ├─ migration_card.py  company.py  generated_document.py
│  │  ├─ ocr_result.py  history.py  settings.py  enums.py
│  ├─ ui/
│  │  ├─ main_window.py
│  │  ├─ views/              # dashboard, process, companies, archive, search, settings
│  │  ├─ widgets/            # DropZone, DocPreview, ConfidenceField, ProgressToast
│  │  ├─ viewmodels/         # plain state objects bound to views
│  │  ├─ theme.py            # applies qss, light/dark switch at runtime
│  │  └─ i18n.py             # translator, no-restart language switch
│  ├─ controllers/
│  │  ├─ process_controller.py   # the core upload→OCR→validate→PDF→archive flow
│  │  ├─ company_controller.py   archive_controller.py
│  │  ├─ search_controller.py    settings_controller.py  dashboard_controller.py
│  ├─ services/
│  │  ├─ interfaces.py       # ABCs: IOcrService, IAiProvider, IPdfService, …
│  │  ├─ ocr_service.py      ai_service.py  validation_service.py
│  │  ├─ pdf_service.py      company_service.py  archive_service.py
│  │  ├─ history_service.py  search_service.py  backup_service.py
│  │  └─ notification_service.py
│  ├─ ocr/
│  │  ├─ pipeline.py         # preprocess → detect → extract → normalize → score
│  │  ├─ preprocess.py       # OpenCV: rotate, deskew, denoise, contrast, crop
│  │  ├─ detector.py         # document-type detection
│  │  └─ normalizers.py      # dates, names, numbers, unicode
│  ├─ ai/
│  │  ├─ base.py             # IAiProvider ABC (vision + json contract)
│  │  ├─ gemini_provider.py  openai_provider.py
│  │  ├─ prompts.py          # per-document extraction prompts (versioned)
│  │  └─ manager.py          # primary→fallback chain, retry, cache
│  ├─ pdf/
│  │  ├─ engine.py           # fill(template, mapping, values) -> path
│  │  ├─ mapping.py          # load/validate FieldMapping (Pydantic)
│  │  ├─ renderers.py        # grid / text / mark / image renderers (§8)
│  │  ├─ formatters.py       # uppercase, date, boolean, number
│  │  ├─ verifier.py         # post-generation output verification
│  │  └─ calibrate.py        # dev tool: build/adjust a mapping visually (§8.4)
│  ├─ database/
│  │  ├─ connection.py       # SQLite, WAL mode, foreign_keys ON
│  │  ├─ migrations/         # 0001_init.sql, 0002_*.sql …
│  │  └─ repositories/       # company_repo, employee_repo, history_repo, …
│  ├─ common/
│  │  ├─ di.py               # tiny dependency-injection container
│  │  ├─ errors.py           # typed exception hierarchy (§9)
│  │  ├─ logging.py          # structured logger → file + DB
│  │  ├─ result.py           # Result/Either type for recoverable ops
│  │  └─ threading.py        # QThread worker wrapper for async use-cases
│  └─ utils/
│     ├─ dates.py  images.py  files.py  strings.py  hashing.py  paths.py
└─ tests/
   ├─ unit/  integration/  fixtures/  samples/   # synthetic docs only, no PII
```

---

## 4. Runtime data flow (the core use-case)

```
Operator picks company + drops 4 images
        │  (UI, main thread)
        ▼
ProcessController.start_ocr()             ── spawns a Worker (QThread)
        │
        ▼   [worker thread]
OcrService.process(files, company)
   ├─ preprocess.py   (OpenCV per image)
   ├─ detector.py     (which doc is which)
   ├─ AiManager.extract(image, doc_type)  → Gemini → (fallback) OpenAI
   │        returns strict JSON per prompt contract
   ├─ normalizers     (ISO dates, trimmed Cyrillic names, clean numbers)
   └─ ValidationService.validate()        → Employee model + confidence + warnings
        │
        ▼   (signal back to main thread)
UI shows editable review form
   • low-confidence fields highlighted
   • operator corrects, confirms
        │
        ▼
ProcessController.generate()              ── Worker (QThread)
        │
        ▼   [worker thread]
PdfService.generate(employee, company)
   ├─ mapping.load(template.mapping.v1)
   ├─ engine.fill()  (grid/text/mark/image renderers)
   ├─ verifier.verify()  (page count, required fields, opens cleanly)
   ├─ save → output/<Company>/<SURNAME_NAME>.pdf   (dedupe _001,_002)
   ├─ ArchiveService.archive()  (copy images+pdf+ocr.json+metadata.json)
   └─ HistoryService.record()   + StatisticsService.bump()
        │
        ▼
UI toast: "PDF generated" + [Open folder] [Open PDF]
```

Every step logs start/end/duration. Any failure is caught, typed, logged, shown
as a friendly message, and leaves uploaded files + partial state intact.

---

## 5. Domain models (Pydantic) — derived from the real form

Field lists come straight from the МВД Приложение № 7 boxes and the OCR spec.
All models are `pydantic.BaseModel` with validators. `Optional` = the box may be
empty on the real form.

```python
# domain/enums.py
class DocType(StrEnum): PASSPORT; PATENT; REGISTRATION; MIGRATION_CARD; UNKNOWN
class Gender(StrEnum):  MALE; FEMALE
class ContractType(StrEnum): LABOR; CIVIL          # трудовой / гражданско-правовой
class EmployerType(StrEnum): LEGAL_ENTITY; IP; LAWYER; INDIVIDUAL; ...  # the §1 checkboxes

# domain/passport.py
class Passport(BaseModel):
    surname: str; name: str; patronymic: str | None
    gender: Gender | None
    birth_date: date | None
    birth_place: str | None
    nationality: str | None            # Гражданство (e.g. ТАДЖИКИСТАН)
    series: str | None
    number: str                        # e.g. 4025112331
    issue_date: date | None
    issued_by: str | None              # e.g. МВД
    # confidence carried separately in OcrFieldScore

# domain/patent.py
class Patent(BaseModel):
    doc_name: str = "ПАТЕНТ"
    series: str | None                 # 77
    number: str                        # 26003 14661
    issue_date: date
    valid_from: date; valid_to: date   # Срок действия … по …
    issued_by: str                     # Отдел внешней трудовой миграции …
    profession: str                    # ПОДСОБНЫЙ РАБОЧИЙ

class Registration(BaseModel):
    address: str; registration_date: date | None; expiration_date: date | None

class MigrationCard(BaseModel):
    number: str | None; entry_date: date | None; purpose: str | None

# domain/company.py  (the §1–1.2 employer block, static per company)
class Company(BaseModel):
    id: UUID; name: str; internal_code: str
    employer_type: EmployerType
    okved: str                         # 46.21.19
    ogrn: str                          # ОГРНИП 315080100000587
    inn: str                           # 080100230802
    address_index: str; address_text: str      # 111677, МОСКВА УЛ. ВЕРТОЛЁТЧИКОВ Д4 К2
    phone: str | None
    director_position: str             # ГЕНЕРАЛЬНЫЙ ДИРЕКТОР
    director_fio: str                  # ГОРДИЕНКО АЛЕКСЕЙ АНАТОЛЬЕВИЧ
    logo_path: Path | None; template_path: Path; status: CompanyStatus

# domain/employee.py — the aggregate the PDF engine consumes
class Employee(BaseModel):
    id: UUID; company_id: UUID
    passport: Passport
    patent: Patent | None
    registration: Registration | None
    migration_card: MigrationCard | None
    profession: str
    contract_type: ContractType
    contract_date: date
    work_address: str | None
```

`OcrResult` keeps the raw AI JSON, the normalized JSON, and a per-field
confidence map so the UI can highlight anything below the threshold. Domain
models never store confidence — that is OCR metadata, kept separate.

---

## 6. Database schema (SQLite, Repository pattern)

- SQLite in **WAL** mode, `PRAGMA foreign_keys = ON`, UUID text PKs.
- Migrations are plain, ordered `.sql` files applied by `connection.py` on start,
  tracked in a `schema_migrations` table. Never destructive.
- Every business table carries `created_at`; audit tables are append-only.

Core tables (from `DATABASE.md`, trimmed to what v1 needs; the rest are added in
their phase):

```sql
companies(id, name, internal_code UNIQUE, employer_type, okved, ogrn, inn,
          address_index, address_text, phone, director_position, director_fio,
          logo_path, template_path, status, notes, created_at, updated_at, archived_at)

employees(id, company_id FK, surname, name, patronymic, gender, birth_date,
          nationality, created_at, updated_at)
passport_data(id, employee_id FK, series, number, issue_date, issued_by,
              birth_place, scan_path, ocr_json, confidence, created_at)
patent_data(id, employee_id FK, series, number, profession, issue_date,
            valid_from, valid_to, issued_by, scan_path, ocr_json, confidence, created_at)
registration_data(...)   migration_cards(...)

document_templates(id, company_id FK, template_name, template_path, version,
                   is_default, created_at)
generated_documents(id, employee_id FK, company_id FK, template_id FK, pdf_path,
                    file_size, generation_ms, status, created_at)
ocr_results(id, employee_id FK, provider, raw_json, normalized_json,
            confidence, processing_ms, created_at)
history(id, employee_id, company_id, action, description, created_at)
logs(id, level, module, message, stack_trace, created_at)
settings(id, key, value, updated_at)            -- key/value, typed on read
api_providers(id, provider, api_key_enc, base_url, enabled, priority, created_at)
statistics(id, total_documents, total_employees, total_companies,
           ocr_ms_avg, pdf_ms_avg, last_generated)
```

**Indexes** (from `DATABASE.md` perf target — search < 100 ms on 100k rows):
`employees(surname)`, `passport_data(number)`, `patent_data(number)`,
`employees(company_id)`, `*_data(employee_id)`, `*(created_at)`.

**Rules enforced in repos, not UI:** never hard-delete employees or generated
docs; soft-delete + archive; every mutation writes a `history` row.

API keys in `api_providers.api_key_enc` are encrypted at rest (Windows DPAPI via
`win32crypt` when available, AES-GCM with a machine-derived key as fallback).

---

## 7. OCR + AI contract

**The engine is provider-agnostic.** `IAiProvider` is the only thing the OCR
pipeline knows about:

```python
class IAiProvider(ABC):
    name: str
    @abstractmethod
    def extract(self, image: bytes, doc_type: DocType, prompt: Prompt) -> AiRawResult: ...
    @abstractmethod
    def health(self) -> ProviderHealth: ...
```

- **Preprocess (OpenCV):** auto-rotate (EXIF + text-orientation), deskew,
  perspective-correct, denoise, CLAHE contrast, border-crop, resolution-normalize.
  Output is a clean bytes image handed to the provider. Pure function, unit-tested
  on fixture images with known transforms.
- **Detect type:** cheap heuristics first (aspect ratio, keyword hits from a fast
  pass); the AI call is asked to confirm `document_type`. Operator is never asked.
- **Extraction prompt contract:** every provider MUST return strict JSON matching
  a JSON Schema per document type — never prose. Example (passport):
  ```json
  {"document_type":"passport","confidence":0.0-1.0,
   "fields":{"surname":{"value":"","confidence":0.0-1.0}, ...}}
  ```
  `ai/manager.py` validates against the schema; a parse failure is a typed
  `AiInvalidJsonError` that triggers a retry, then provider fallback.
- **Fallback chain:** `primary (Gemini) → retry×N (backoff 1s,2s,4s) → secondary
  (OpenAI) → retry → AiUnavailableError`. Uploaded files are never lost on failure.
- **Normalize:** dates → ISO internally; names → trimmed, Cyrillic-preserving,
  Uzbek-safe; numbers → cleaned. All normalizers are pure + unit-tested.
- **Confidence:** any field below `settings.ocr.confidence_threshold` (default
  0.90) is flagged for the review form.
- **Adding Claude / Azure / local later** = new file implementing `IAiProvider`
  + a registry entry. Zero changes to `ocr/`, `services/`, or the UI.

---

## 8. PDF engine & field-mapping — the heart of the system

The whole product hinges on this: **one code base fills unlimited company
templates**, and templates are static scanned/graphical PDFs (the real МВД form
is 5 pages of pure raster — no AcroForm fields, no text layer). So we place text
by coordinate, driven entirely by an external JSON mapping.

### 8.1 The template reality
- A4 pages: **595.3 × 842.4 pt**. Origin **top-left**, coordinates in points.
- Most of the form is **character grids**: a row of equal boxes, one glyph each
  (surname `А З И М О В`, ИНН `0 8 0 1 0 0 2 3 0 8 0 2`, dates `2 3 | 0 1 | 1 9 8 1`).
- A few **checkbox marks**: put `V` / `X` at a point (employer type §1, contract
  type §3.3).
- A few **free-text** areas (the director line on page 5).

### 8.2 Field types (renderers.py)
```
grid  → renders each character of `value` into its own cell.
        Needs: page, x0 (center of first cell), y (baseline), pitch (cell-to-cell
        spacing in pt), max_cells, font, size, align="center", transform.
        Overflow strategy per FIELD_MAPPING.md: trim | shrink | error.
text  → free text at (x,y), with wrap width, max lines, overflow strategy.
mark  → a single glyph (V/X/☑) at (x,y). Used for checkboxes.
image → logo/stamp/signature drawn in a box (x,y,w,h), aspect-preserved.
```
A grid is fully described by `x0`, `pitch`, `max_cells` — so calibrating a
20-box row is **two clicks** (first + last cell), pitch is computed.

### 8.3 Mapping schema (JSON, versioned per template)
```json
{
  "template": "mvd_prilozhenie_7",
  "template_version": "1",
  "mapping_version": "1",
  "page_size": [595.3, 842.4],
  "fields": [
    { "id": "employee.passport.surname", "type": "grid",
      "page": 1, "x0": 175.0, "y": 561.0, "pitch": 21.4, "max_cells": 20,
      "font": "Arial", "size": 12, "transform": "uppercase",
      "required": true, "validator": "russian_name", "overflow": "shrink" },

    { "id": "employee.passport.birth_date.day",   "type": "grid",
      "page": 2, "x0": 220.0, "y": 470.0, "pitch": 21.4, "max_cells": 2,
      "formatter": "date_dd", "required": true },
    { "id": "employee.passport.birth_date.month", "type": "grid", "page": 2,
      "x0": 285.0, "y": 470.0, "pitch": 21.4, "max_cells": 2, "formatter": "date_mm" },
    { "id": "employee.passport.birth_date.year",  "type": "grid", "page": 2,
      "x0": 360.0, "y": 470.0, "pitch": 21.4, "max_cells": 4, "formatter": "date_yyyy" },

    { "id": "company.employer_type.legal_entity", "type": "mark",
      "page": 1, "x": 70.0, "y": 505.0, "glyph": "V",
      "visible_if": "company.employer_type == LEGAL_ENTITY" },

    { "id": "company.inn", "type": "grid", "page": 2, "x0": 120.0, "y": 210.0,
      "pitch": 21.4, "max_cells": 12, "validator": "inn" }
  ]
}
```
Coordinates above are **illustrative** — the exact numbers come from calibration
(§8.4). The schema, the renderers, and the formatters are what we build; the
numbers are data.

### 8.4 Calibration tool (`pdf/calibrate.py`, dev-time)
Because eyeballing 100+ coordinates is error-prone, the PDF work ships with a
small calibrator:
1. Render `template.pdf` page to an image at a known DPI (scale = pt↔px is exact).
2. Operator clicks the **first** and **last** cell of a grid row → the tool
   computes `x0`, `pitch`, `max_cells` and writes the field to `mapping.json`.
3. For marks/text: one click = the point.
4. A **preview** overlays sample data onto the real template so drift is caught
   visually before shipping a template.
This is the v1 answer to `FIELD_MAPPING.md`'s "Visual Mapping Editor (future)".

### 8.5 Generation guarantees
- Template is **never modified** — we open it, draw on a copy, save new.
- **Deterministic:** fonts embedded (Arial/Noto, Cyrillic + Uzbek glyphs), no
  timestamps in content stream → identical bytes for identical inputs.
- **Verified** before archiving: page count matches, all `required` fields were
  filled, every font/image loaded, output re-opens as a valid PDF. Fail → no
  archive, error logged, friendly message.
- **Never overwrites** output: `SURNAME_NAME.pdf` → `_001`, `_002`, …

### 8.6 Engine independence
`PdfService` receives only a validated `Employee` + `Company` + a `FieldMapping`.
It never imports `ocr`, `ai`, `ui`, or `database`. It can be lifted into any other
app unchanged — which is exactly the `PDF_ENGINE.md` rule.

---

## 9. Cross-cutting concerns

**Errors (`common/errors.py`).** One typed hierarchy so every layer speaks the
same failure language and the UI can map type→friendly message:
```
OfisError
 ├ UserError (MissingDocument, InvalidFileType, EmptyFile)
 ├ ValidationError (InvalidDate, InvalidPassport, RequiredFieldMissing)
 ├ OcrError (UnreadableImage, LowConfidence, OcrTimeout)
 ├ AiError (AuthFailed, QuotaExceeded, RateLimited, InvalidJson, Unavailable)
 ├ PdfError (TemplateMissing, TemplateCorrupted, FontMissing, MappingInvalid, WriteFailed)
 ├ DatabaseError (Locked, Corrupted, ConstraintViolation, MigrationFailed)
 └ InfraError (DiskFull, PermissionDenied, NetworkError, ConfigError)
```
Rule: no bare `except`, no silent pass. Recoverable errors return a `Result`;
fatal ones are caught at the controller boundary, logged with full context, and
shown without a stack trace. A global `sys.excepthook` writes a crash report to
AppData and offers recovery on next start.

**Logging (`common/logging.py`).** Structured records (timestamp, level, module,
operation, duration, request_id) to a rotating file in AppData **and** the `logs`
table. INFO/WARNING/ERROR/CRITICAL. Secrets are never logged; raw provider
responses never reach the UI.

**Config & paths (`config/`).** Program files vs. user data separated the Windows
way: binaries under Install dir, mutable data under
`%LOCALAPPDATA%\OFIS\` (settings, logs, cache, backups, output, archive). Nothing
hardcoded — all through `SettingsService`.

**DI (`common/di.py`).** A tiny container wired once in `app.py` (the composition
root). Everything else receives its dependencies via constructor injection, so
every unit gets a fake in tests. No service locators, no globals.

**Threading (`common/threading.py`).** A `Worker(QRunnable/QThread)` wrapper runs
any use-case off the UI thread and marshals results back via signals. OCR, AI,
PDF, backup, and archive always run through it → the window stays at 60 fps and
`UI_UX.md`'s "responsive during OCR/PDF" holds.

**i18n & theme.** `resources/i18n/{ru,uz,en}.json` + a translator that re-renders
on switch (no restart). `resources/qss/{light,dark}.qss` applied at runtime.

---

## 10. Packaging (Phase 14)

- **PyInstaller** one-file build via `build/ofis.spec`: bundles fonts, icons, qss,
  i18n, and the blank templates. No console window (`--windowed`).
- Data (settings/logs/archive) lives in AppData, so the EXE stays read-only and
  updatable.
- Output: portable ZIP + (later) an MSI/EXE installer that makes shortcuts and the
  AppData folders. App runs without admin after install.

---

## 11. Testing strategy (maps to `TESTING.md`)

- **Unit** (≥90% on services/normalizers/formatters/repos) — pure, deterministic,
  no network/GPU/display via the fakes.
- **PDF golden tests:** fill the МВД template with a fixed synthetic employee →
  assert the output PDF byte-matches a checked-in golden (proves determinism) and
  that a text-probe finds each value at its expected page/'box'.
- **OCR tests** run against the provider **fakes** returning canned JSON (real API
  calls are opt-in, key-gated, and never in CI). Preprocess tested on fixture images.
- **Integration:** OCR→Validation→PDF→Archive→DB on synthetic data.
- **No real personal data** in the repo — synthetic fixtures only.

---

## 12. Phase 1 deliverable (what the first commit builds)

Per `DEVELOPMENT_ROADMAP.md` Phase 1 + this design, the first working milestone:

1. Repo skeleton exactly as §3 (empty but importable packages).
2. `pyproject.toml` (ruff + mypy + pytest), `requirements.txt`, `.gitignore`,
   `.env.example`.
3. `common/`: logging, errors, Result, DI container, paths — working.
4. `config/SettingsService` backed by a SQLite `settings` table + migration `0001`.
5. `domain/` Pydantic models from §5 (compile + validate, with unit tests).
6. `app.py` boots a DI container and shows an **empty themed `MainWindow`** with the
   sidebar (Dashboard/Process/Companies/Archive/Search/Settings) and a status bar.
7. `tests/` green; app launches in < 3 s; import-lint test enforcing §2 passes.

**Success criteria (roadmap M1):** the application starts, logs its startup,
reads settings, and shows a professional empty shell — nothing faked, everything
on the real architecture.

Subsequent phases (DB repos → UI screens → OCR → AI → PDF engine → archive →
search → settings → perf → tests → packaging) each land as their own reviewed,
independently-runnable milestone.

---

*End of design. No code is written until this is approved. Approve, and Phase 1
lands as the first commit on the new `OFIS` repository.*
