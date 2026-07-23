# OFIS — Operator workflow & field spec (from the owner)

The authoritative description of how the app must behave, captured from the
owner's own words. Everything here drives the МВД Приложение № 7 template; other
forms (регистрация, трудовой договор) follow the same model later.

## The 16 fill-in fields (everything else on the form is fixed company data)

| # | Field | Page | Source | Notes |
|---|-------|------|--------|-------|
| 1 | Фамилия | 2 | passport (OCR) | uppercase |
| 2 | Имя | 2 | passport | |
| 3 | Отчество | 2 | passport | may be empty |
| 4 | Гражданство | 2 | passport | |
| 5 | Дата рождения (д/м/г) | 2 | passport | three box groups |
| 6 | Паспорт серия + номер | 2 | passport | two groups |
| 7 | Дата выдачи паспорта (д/м/г) | 2 | passport | |
| 8 | Кем выдан паспорт | 2 | passport | long text, wraps rows |
| 9 | Патент серия + номер | 3 | patent | two groups |
| 10 | Дата выдачи патента (д/м/г) | 3 | patent | also written in "Срок действия с" |
| 11 | Срок окончания патента (д/м/г) | 3 | **computed** | = field 10 + **1 year** (10.05.2026 → 10.05.2027) |
| 12 | Патент кем выдан | 3 | patent (back side) | organization name |
| 13 | Дата формы (д/м/г) | 3 | **operator** | program ASKS before generating |
| 14 | Рег. номер уведомления | 5 | **auto** | 3-digit, auto-increments: 345 → 346 → 347 … |
| 15 | ФИО + гражданство | 5 | passport | e.g. "РАСУЛОВ МУСТАФО АЗИЗЖОН УГЛИ, УЗБЕКИСТАН" |
| 16 | Должность (профессия) | 3 | **operator** | program ASKS; default **ПОДСОБНЫЙ РАБОЧИЙ** if left blank |

Notes on the pre-printed template:
- "ПАТЕНТ" (наименование документа, p3) is pre-printed and constant — never touched.
- "ПОДСОБНЫЙ РАБОЧИЙ" is pre-printed in §3.2. So field 16 logic:
  - должность = ПОДСОБНЫЙ РАБОЧИЙ (default) → leave the pre-printed text, write nothing.
  - должность = anything else (ВОДИТЕЛЬ, …) → whiteout the pre-printed row, then write the new value.

Fill-in pages: **2, 3, 5**. Font: **Calibri** on Windows (Carlito on the dev box).

## AI mode (default runtime flow)

1. Companies are stored (1 now, ~5–6 later); operator picks one.
2. Operator uploads the worker's **passport + patent photos**.
3. Operator selects: **company**, **date (13)**, **должность (16)** (default kept if skipped).
4. Operator presses **RUN**.
5. Program OCR-reads passport + patent, fills the selected company's template,
   computes field 11 (+1 year) and field 14 (next number), generates the PDF and
   **saves it to the computer named by the worker's SURNAME** (e.g. `РАХИМОВ.pdf`,
   dedupe `_001` …).

## Manual mode (offline / no-AI fallback)

- A **"Qo'lda to'ldirish" (Manual fill)** button.
- Opens a table of the **16 fields**, each row labeled with what goes there
  (1 = Фамилия, 2 = Имя, 3 = Отчество, 4 = Гражданство, …).
- Operator types the values by hand; program fills the PDF from the table.
- Used when internet or AI is unavailable. **AI is the default; manual is fallback.**

Both modes converge on the same engine: they produce the same
`{field_id: value}` dict that `src/pdf/engine.py` fills. AI mode fills the dict
from OCR; manual mode fills it from the table.

## Status
- Fields 1–10, 12 (pages 2–3) + 11 (computed +1yr): **calibrated & filling correctly**
  on the blank template.
- Field 16 (профессия): calibrated; needs the whiteout-on-custom rule above.
- Fields 13, 14, 15: pending (13/14 are values; 15 is a page-5 line field to place).
- Next: page-5 line calibration (14, 15), the values flattener (Employee+Company
  → dict incl. computed 11/14/15), then the UI (company picker, upload, RUN,
  manual-fill table) and the OCR/AI reader.
