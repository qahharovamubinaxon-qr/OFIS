# АЛЬЯНСКОТ 2400 — new OFIS section (design)

Date: 2026-09-09 · Status: approved by the office, ready to plan.

## Purpose

A new section, **АЛЬЯНСКОТ 2400**, that prints one worker's **удостоверение**
(a badge-style ID card, front + back) and **two справки** onto the firm's own
blank PDFs. The operator uploads the blanks once, arranges where every value
sits, and from then on each worker is: drop passport + photo, sign, type a few
fields, RUN → three named PDFs.

It is the АЛЬПИНИСТ screen (photo 3×4 + background removal + drawn signature +
per-blank arrange) generalised to **three blanks that each print and save as a
separate PDF**, the way ТРУД-8 already produces more than one document.

## Section identity

- Nav label: **АЛЬЯНСКОТ 2400**. Registered in `main_window.py` beside the
  other worker-document sections.
- New, self-contained modules (existing working modules are NOT touched):
  - `src/ui/views/alliance_view.py` — the screen.
  - `src/controllers/alliance_controller.py` — reads documents, drives service.
  - `src/services/alliance_service.py` — blank storage, arrange layout, fill.

## Blanks (uploaded once, kept)

Three blank PDFs, uploaded via three buttons and stored for the firm:

1. **Удостоверение** — a single **2-page** PDF (page 1 = front, page 2 = back).
2. **СПРАВКА-1** — single page.
3. **СПРАВКА-2** — single page.

Re-uploading replaces a blank. Blanks live under the section's own data dir
(mirrors how ТРУД-8 / hostel keep their blanks); they are never swept.

## Inputs per worker

- **🛂 Passport** — dropped; the moment it lands the AI reads it (the shared
  read-then-check flow). ФИО, gender and birth date appear in the editable
  `PassportReview` panel for the operator to check/correct before printing.
- **📷 Worker photo** — dropped; processed to 3×4 with the background removed
  (reuse `bg_segment` + the alpinist photo pipeline).
- **✍ Signature** — the worker draws it in-app with the mouse (reuse the
  alpinist signature pad), kept for this worker's run.
- **Typed fields:** удостоверение № · должность · start date.
- **End date** = start date **+ exactly 3 years**, computed automatically and
  shown read-only (07.09.2026 → 07.09.2029).

## Placeable values (arrange)

A **📐 Жойлаш** tool (reuse `arrange_mapping` / the ТРУД-8 multi-page arranger)
opens each blank and lets the operator drag, size, colour and set the font of
every value, saved per blank. The удостоверение arrange spans **both pages**.

Placeable items (the operator decides which appear on which blank/page):

- Text: surname, name, patronymic, удостоверение №, должность, gender,
  start date, end date.
- Images: **photo** (the 3×4 background-removed portrait, placed to fill its
  frame — the alliance равивалент of alpinist's photo-into-frame) and
  **signature**.

Only what the operator actually moves is written to the layout; anything left
where the program put it keeps following the program (same rule as the other
sections' arrange).

## Generation (RUN)

Guarded like every other section: passport must be read (panel shown, surname
present) and all three blanks uploaded. Then:

1. Build the worker's values from the review boxes + typed fields + computed
   end date.
2. Fill each blank from its saved layout, drawing the photo and signature
   where arranged.
3. Ask the operator where to save (`ask_save_dir`).
4. Write **three separate PDFs**, each named `SURNAME_NAME.pdf`:
   - удостоверение (2 pages), справка1, справка2.

## Reused building blocks

- `passport_review.PassportReview` + `ready_or_start` gate (read → check → print).
- `ocr.OcrService.read_passport` / `read_documents` (via a controller with
  `read_image`, `read_documents`, `generate`).
- `bg_segment` + alpinist photo cropping (3×4, background clean).
- Alpinist signature pad.
- `arrange_mapping` / ТРУД-8 arranger (multi-page, text + image placement),
  `blank_layout` for per-blank persistence.
- `pdf` fill engine; `save_to.ask_save_dir`.

## Testing

- Unit: end date = start + 3 years (leap-day edge picked explicitly).
- Unit (real controller): `read_image`, `read_documents`, `generate` exist and
  a dropped passport reads → panel fills (the class of bug that hit ТРУД).
- Unit (view, fake controller): drop passport → panel fills; RUN refused until
  passport read + all three blanks present; RUN produces three results named
  after the worker; the corrected name in the boxes is what prints.
- Photo pipeline: a portrait is cropped to a 3×4 aspect and returned.

## Out of scope

- No changes to existing sections or their controllers/services.
- No cloud/bot path for this section initially (desktop only; a one-shot
  `generate_from_images` may be added later if the bot needs it).
- Blank content/templates are the office's own uploads — nothing is bundled.
