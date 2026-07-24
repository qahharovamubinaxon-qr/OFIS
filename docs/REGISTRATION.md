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

## Status — DONE
- ✅ Passport model/prompt/OCR read **gender** and **expiry_date**.
- ✅ Engine supports two fonts (OfisSans = Calibri, **OfisSerif = Times**),
  chosen per field via the mapping's `font` key.
- ✅ Template + meta installed at `templates/registration/`.
- ✅ Calibration: the faint boxes are found by the new contour-based
  `detect_cell_runs` (fixed threshold, not OTSU). `mapping.v1.json` has all 23
  serif fields; `scripts/calibrate_registration.py` regenerates it. Verified
  aligned on both pages against a rendered fill.
- ✅ `registration_values.py` builder — names/citizenship from patent, dates &
  gender from passport, registration expiry → «Заявленный срок» (p1) +
  «Поставлен на учет до» (p2), gender → checkbox mark.
- ✅ `RegistrationAddress` entity + repo + migration `0003` + service (copies a
  blank template per address, like a company).
- ✅ `Регистрация` nav screen: address picker + **add new address**, upload
  passport/patent (drag&drop), registration-expiry date, RUN → PDF named by
  surname under `output/registration/<address>/`.
- ✅ Seeded first address (Г МОСКВА 5-Я ПАРКОВАЯ 55, host ПОПОВ) from the
  shipped template. Tests in `tests/unit/test_registration.py`.

## How a new address is added (operator)
Регистрация → «+ Yangi manzil» → fill label/code/address/host ФИО → pick that
address's filled-blank PDF (address + host already printed) → Save. One shared
mapping fills any address; no code change.
