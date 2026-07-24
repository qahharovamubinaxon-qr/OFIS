# Registration form (Уведомление о прибытии) — spec & plan

A second form type, added alongside the МВД trudovoy form. Font: **Times New
Roman** (OfisSerif). Template: `templates/registration/template.pdf` (2 pages).

## What the program fills (from passport + patent + one runtime input)

### Page 1 (worker)
| Field | Source |
|---|---|
| Фамилия, Имя, Отчество | **patent** (Russian) |
| Гражданство/подданство | **patent** (Russian) |
| Дата рождения (число/месяц/год) | passport |
| Пол (мужской / женский — mark) | passport (gender) |
| Паспорт серия, № | passport |
| Дата выдачи (число/месяц/год) | passport |
| Срок действия до (число/месяц/год) | passport (**expiry_date** — new) |
| Заявленный срок пребывания до (число/месяц/год) | **operator input** (registration expiry, asked at upload) |

### Page 2
| Field | Source |
|---|---|
| Поставлен на учет до (число/месяц/год) | = registration expiry (same runtime value) |

### Pre-printed per address (in each address's template — like a company)
- Page 1: the arrival address (субъект «Г МОСКВА», street «5-Я ПАРКОВАЯ», дом,
  корпус, квартира) and «вид ИНОСТРАННЫЙ».
- Page 2: the host (принимающая сторона) ФИО, e.g. ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ.

## Registration "addresses" = like companies
A `Регистрация` section lets the operator add addresses (each = a blank template
with the address + host pre-filled), exactly like adding a company. One shared
field mapping fills any address's template.

## Status
- ✅ Passport model/prompt/OCR now read **gender** and **expiry_date**.
- ✅ Engine supports two fonts (OfisSans = Calibri, **OfisSerif = Times**),
  chosen per field via the mapping's `font` key.
- ✅ Template + meta installed at `templates/registration/`.
- ⏳ Field calibration: this form's boxes are faint/small; auto-detection needs a
  fixed-threshold pass + per-row measurement (in progress — will be tuned against
  a filled sample like the МВД form was).
- ⏳ `RegistrationAddress` entity + `Регистрация` nav screen (add/list) + fill
  flow (asks the registration-expiry date), reusing the engine and OCR.

## Next steps
1. Calibrate `templates/registration/mapping.v1.json` (grid + mark fields, serif).
2. `registration_values.py` builder (names from patent, dates from passport,
   gender→mark, registration expiry → both pages).
3. `RegistrationAddress` repo/service/migration + `Регистрация` view + process
   flow, then iterate on alignment from the operator's screenshots.
