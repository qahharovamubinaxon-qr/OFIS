# OFIS — Progress

## ПЕРЕВОД скани · УМУМИЙ бир майдон · премиум дизайн ✅
- **ПЕРЕВОД**: чиқиш энди 2 саҳифа — 1-саҳифа юкланган расм **сканер қилингандек**
  (AI ҳужжат чегарасини қайтаради → фон кесилади, ёруғлик текисланади, тиниқ
  оқ-қора), 2-саҳифа таржима. Таржимон номи ва сана олиб ташланди — офис ўз
  тасдиқ варағини қўшади.
- **УМУМИЙ**: 3 та алоҳида майдон ўрнига 2 та катта drag&drop майдон —
  ҳужжат (PDF) ва ишчи ҳужжатлари (хоҳлаганча расм, паспорт мажбурий эмас —
  патент ёки миграционка ҳам етарли).
- **MultiDropZone** темага уланди (аввал қаттиқ стиль эди), hover/filled
  ҳолатлари, PDF режими.
- **Дизайн**: нав бўлимларга ажратилди (МИГРАЦИЯ · НОТАРИУС · ҲУЖЖАТ · БАЗА),
  Sozlamalar карточкаларга бўлинди (`src/ui/widgets/card.py`) —
  AI · Ko'rinish · Доверенность · Telegram · Zaxira · Papkalar, скролл билан.
- Tests: **64/64**.

## УМУМИЙ + ПЕРЕВОД бўлимлари ✅
- **УМУМИЙ** (`src/services/umumiy_service.py`): офиснинг ҳар қандай матнли
  PDF ҳужжати (шартнома, справка, ариза) + янги ишчи паспорт/патент расми +
  сана → AI ҳужжат ичидаги ЭСКИ ишчи маълумотларини топади, редакция билан
  ўчириб, янги ишчиникини ўша жойга, ўша шрифт/ўлчамда ёзади.
  - Фирма реквизитлари (ИНН, ОГРН, КПП, БИК, р/с, директор) промпт билан
    ҳам, `_PROTECTED` регекс қўриқчиси билан ҳам ҳимояланган.
  - Скан (расм) PDF учун тушунарли хато хабари.
  - Ҳақиқий СЕРВИСБЫТ-НН шартномасида текширилди: ФИО, туғилган сана,
    паспорт рақами алмашди; фирма ИНН тегилмади.
- **ПЕРЕВОД** (`src/services/perevod_service.py`): паспорт · ҳайдовчилик
  гувоҳномаси · туғилганлик/никоҳ гувоҳномаси · диплом · аттестат ·
  миграционная карта расмларини юклаш → AI ҳужжат турини ЎЗИ аниқлайди,
  барча майдонларни ўқиб рус тилига нотариал стандарт бўйича таржима қилади
  → PDF + Word («ПЕРЕВОД С … ЯЗЫКА НА РУССКИЙ ЯЗЫК» сарлавҳа, майдонлар,
  печатлар, таржимон имзоси учун сатр).
  - `templates/perevod/forms.v1.json` — 8 турдаги ҳужжат учун стандарт
    майдонлар тартиби (AI қайси тартибда қайтарса ҳам, чиқиш бир хил).
- Янги умумий AI ёрдамчи: `src/ai/text_client.py` (эркин матн сўровлари,
  429 да кутиб қайта уриниш, JSON режими).
- Нав: 15 бўлим (♻️ УМУМИЙ, 🌐 ПЕРЕВОД қўшилди).
- Tests: **63/63**.

## ХОСТЕЛ бўлими ✅
- Янги 13-бўлим: хостелда яшовчи ишчилар учун «Уведомление о прибытии».
  Регистрация билан бир хил оқим, лекин ўз бланки/координаталари билан
  (`templates/hostel_blank/blank.pdf` + `templates/hostel/{mapping,
  address_mapping}.v1.json`, образецдан калибровка қилинган).
- «+ Yangi xostel»: ном/код · область·район·город·улица·дом·корпус·строение·
  комната · хозяин ФИО · наименование организации · ИНН → программа бўш
  бланкага босиб, ўша хостел шаблонини ясайди (Times New Roman 10). Ёки
  тайёр тўлдирилган шаблон PDF юклаш мумкин.
- RUN: паспорт+патент расмлари + бошланиш/тугаш саналари → PDF, қаерга
  сақлашни сўрайди (`ask_save_dir`).
- Маълумот базаси: `registration_addresses` жадвалига `kind` ('regular' |
  'hostel'), `organization_name`, `inn`, `komnata` устунлари қўшилди
  (migration 0008). Хостеллар оддий адреслардан ажратилган.
- ИП ДЯГИЛЕВА (ЛУЖСКАЯ 10) хостели биринчи ишга туширишда сидланади.
- **Ҳуқуқий чегара**: чиқадиган PDF — Госуслугига топшириладиган бўш ариза
  бланкаси. МВД электрон имзо блоки ва рўйхат рақами ҳеч қачон қайта
  чиқарилмайди (тест билан қўриқланади) — уларни реал топширувдан кейин
  МВД/Госуслуги ўзи қўяди.
- Tests: **58/58**.

## Telegram бот — телефондан бошқариш ✅
- `src/controllers/telegram_bot.py`: long-polling бот (зависимостсиз, urllib).
  Телефондан: /start ПАРОЛ → менюдан Патент PDF / Регистрация / Трудовой /
  Расм 3×4 → фирма/манзил inline-кнопкада → расмларни тартибда юбориш
  (1 паспорт, 2 патент олд, 3 орқа) → «✅ Тайёрла» → тайёр PDF(лар) чатга
  қайтади. Регистрацияда тугаш санаси сўралади (КК.ОО.ЙЙЙЙ).
- Хавфсизлик: парол (Sozlamalar'да), рухсатли чатлар DB'да сақланади.
- Sozlamalar → Telegram: токен (@BotFather) + парол; дастур қайта очилганда
  бот ишга тушади. Компютер ва OFIS очиқ туриши шарт (иш шу ерда бажарилади).
- WhatsApp: расмий API фақат пуллик Business-провайдер орқали — уланмади;
  WhatsApp'дан келган расмни ботга forward қилиш тавсия этилади.
- Tests: **53/53**.

## Доверенность на нотариальном бланке + premium UI ✅
- **Blank rendering**: every Доверенность/Согласие/Заявление PDF is now laid
  onto the office's scanned notarial blank (`templates/dover_blank/page1.jpg`
  — series pre-cleaned — + continuation `page2.jpg`). The series number
  («77 АВ 2463964») is drawn per document in the blank's own red serif and
  auto-increments; реестр № does too (12855, 12856, …). Word copy stays
  blank-free. `src/pdf/dover_renderer.py` + tests.
- **Layout per the approved образец**: title (СОГЛАСИЕ/…), «Город Москва.» and
  the date-in-words centered; body justified; «Подпись:» line; удостоверительная
  надпись; fixed block «Зарегистрировано в реестре: № N / Уплачено по тарифу:
  1500 руб. / Нотариус: … Друганова М.В.» (AI's own реестр/тариф lines are
  stripped and replaced — applies to ALL dover doc types).
- **Settings → Доверенность**: серия prefix, next бланк number, next реестр №,
  тариф — all editable; counters persist in the DB.
- **Premium UI**: both themes rebuilt (gradient sidebar, accent-bar nav
  selection, gradient RUN button, focus glow inputs, styled combos/tables/
  scrollbars/dialogs/tooltips).
- Tests: **49/49**.

## v1.0.0 — release polish ✅
- **Backup/Restore (Phase 11)**: Settings → «Zaxira yaratish» zips the whole DB
  (firms, addresses, counters, archive) + user templates; «Zaxiradan tiklash»
  stages the ZIP and applies it on next start (pre-restore DB kept in backups/).
  `src/services/backup_service.py`, tests in test_backup.py.
- **User templates now live in AppData** (`%LOCALAPPDATA%\OFIS\templates`), not
  inside the program folder — an EXE rebuild/update no longer deletes firms,
  addresses or company templates added by the user.
- **Packaging (Phase 14)**: real app icon (`resources/icons/ofis.ico`, generator
  in scripts/make_icon.py), Windows version resource (build/version_info.txt),
  Inno Setup installer script (build/installer.iss), portable ZIP step in
  build_exe.bat. APP_VERSION → 1.0.0; window/taskbar icon set at startup.
- Tests: **46/46**. Remaining (needs owner input): paid image-API key for
  10/10 РАСМ-ФОТО; cleaned трудовой templates for the AI template-analysis
  engine; notary requisites for Доверенность header.

## Current state — WORKING MVP ✅
The app runs end-to-end and produces correct МВД Приложение № 7 PDFs.

- **Manual mode works with no AI key** — the full offline path is complete.
- **AI mode is ready** — enter a Gemini key in Settings and RUN reads the
  passport + patent photos automatically.
- All **16 fill-in fields** land correctly on pages 2/3/5 (incl. patent +1yr,
  reg-number auto-increment, ФИО+гражданство, должность whiteout).
- 8 screens: Dashboard, Process, **Registration**, **СФЕРА**, Companies,
  Archive, Search, Settings.
- **Registration form** (Уведомление о прибытии, Times New Roman, size 11):
  pick an address, upload passport+patent, enter registration-expiry → PDF.
  Names from patent, dates/gender from passport, expiry on both pages. All 23
  fields calibrated via contour detection; see docs/REGISTRATION.md.
- **Professional address builder**: «+ Yangi manzil» opens a 10-field table
  (область/район/город/улица/дом/корпус/строение/квартира/владелец/рег.номер) —
  the program prints it onto the bundled blank (`templates/registration/
  blank.pdf` + `address_mapping.v1.json`) to make that address's template:
  address grids on page 1, владелец ФИО on page 2 (3 grid rows + «Владелец:»
  line in the госуслуги box) and «№ …» under «Уведомления зарегистрированго».
  Uploading a ready-made template PDF still works as before.
- **Live progress**: Process/Registration/СФЕРА/Трудовой show a modern animated
  percent bar (`RunProgress`) while the PDF is generated; green→100% on
  success, red on error.
- **Трудовой-Уведомления module**: firms with TWO templates each (трудовой
  договор text-PDF + уведомление госуслуги blank). RUN with passport + patent
  photos + date + должность → two PDFs: the договор with the old worker's
  block/date/profession replaced in-place (redaction-based, pattern-matched, no
  fixed coordinates) and the уведомление filled under its labels (Title-case,
  patent blank series/number OCR'd, region derived from the patent's issuer).
  Firm add/delete inline; migration 0006; see src/pdf/trud_editor.py.
- **Delete buttons**: Компании list, Регистрация address picker and Трудовой
  firm picker each have a 🗑 remove (soft archive — nothing on disk is lost).
- **РАСМ-ФОТО module**: drop any worker photo → YuNet face detection (bundled
  ONNX, offline), eye-line deskew, document 3:4 crop (head ≈60%), GrabCut
  background → pure white, 600×800 PNG preview with Save / Copy-to-clipboard.
  No face → plain 3:4 centre crop. cv2 now ships in the EXE.
- **СФЕРА module** (training-centre Удостоверение + Протокол, 2-page PDF): pick a
  profession (сфера) + date, upload student photo + passport → PDF named by
  surname under `output/svera/`. Certificate ФИО is auto-declined to the **dative
  case** («Расулову Азизу Анваровичу»; «угли» patronymics left as-is); protocol
  ФИО stays nominative. Three auto-incrementing counters: удостоверение №, a
  4-digit ПО number shared by both pages, and a 13-digit protocol reg number.
  5 professions seeded; add more inline. Photo embedded; long profession names
  wrap. Serif Bold/Italic fonts added to the engine.
- Saves `output/<company>/<SURNAME>.pdf` (+ `output/registration/<address>/`,
  `output/svera/`); every doc logged for Archive/Search.
- Run on Windows: `python -m src.app` (see docs/RUN_WINDOWS.md); EXE via
  build/ofis.spec. Tests: **43/43**.

### Next (needs owner input / Windows)
- Gemini key → verify real OCR accuracy on live passport/patent photos.
- Optional OCR image preprocessing (deskew/contrast) once accuracy is measured.
- Add the remaining company templates (5–6) via Companies → + Yangi firma.
- Add real registration addresses via Регистрация → + Yangi manzil.
- Later forms (трудовой договор): new templates/<name>/ only.

## Roadmap phase
**Phases 1–10 substantially delivered** (foundation → DB → UI → OCR → AI → PDF →
archive → search). Packaging spec ready (Phase 14). See DEVELOPMENT_ROADMAP.md.

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
