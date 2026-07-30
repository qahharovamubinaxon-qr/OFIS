"""Chek (premiya cheki) field spec — measured from the owner's filled sample.

Blank template: templates/chek/premiya_blank.pdf (227.5 x 1583 pt receipt).
Font: Microsoft Sans Serif (C:/Windows/Fonts/micross.ttf), sizes below.
Rects are [x0, y0, x1, y1] from the FILLED sample; insert text at the same
baseline (use y1 - descent) and x0. Do not touch anything outside these 12.

Filename rule: "Документ-YYYY-MM-DD-HH-MM-SS" from the ENTERED date+time
(not current time). Default save dir: Desktop; always ask via save dialog
with that default.

User inputs in the UI: patent image (drag&drop), date, time h:m:s, amount
(rubles, e.g. 15000.50), card last-4. From patent OCR/MRZ: fam, ism, otch, inn.
"""

FONT_PATH = r"C:/Windows/Fonts/micross.ttf"

FIELDS = {
    # 1: entered date+time, month in Russian words, " мск" suffix. size 10
    "datetime":   {"rect": [14.2, 35.8, 118.4, 47.1], "size": 10,
                   "fmt": "{d} {month_ru} {yyyy} {HH}:{MM}:{SS} мск"},
    # 2: full FIO from patent, UPPER, wraps to 2 lines (FAM ISM / OTCH). size 11
    "fio_l1":     {"rect": [14.8, 111.6, 111.0, 124.1], "size": 11},   # ФАМ ИСМ
    "fio_l2":     {"rect": [14.5, 124.7, 111.9, 137.2], "size": 11},   # ОТЧЕСТВО
    # 3: card last 4 — only the digits after "МИР Сберкарта **** ". size 10 (sample x)
    "card4":      {"rect": [123.7, 158.6, 149.4, 171.1], "size": 10},
    # 4: INN from patent. size 10
    "inn":        {"rect": [14.2, 559.0, 91.1, 571.5], "size": 10},
    # 5/6/7: name parts, UPPER. size 11
    "ism":        {"rect": [14.3, 670.4, 56.8, 681.7], "size": 11},
    "otch":       {"rect": [14.2, 708.5, 102.4, 719.7], "size": 11},
    "fam":        {"rect": [14.3, 740.5, 56.4, 751.8], "size": 11},
    # 8: "121000000000" + INN. size 10
    "inn12":      {"rect": [14.2, 779.1, 168.3, 791.6], "size": 10,
                   "fmt": "121000000000{inn}"},
    # 9: "1044525225009006" + ddmmyyyy(entered date) + "11071538", wraps. size 10
    "sana_baza":  {"rect": [14.2, 842.3, 117.0, 854.7], "size": 10,
                   "fmt": "1044525225009006{ddmmyyyy}11071538"},
    # 10: random 6-digit per generated PDF. size 10
    "avtoriz":    {"rect": [14.2, 1269.2, 52.7, 1281.7], "size": 10},
    # 11: amount "10 000,00 ₽" in TWO places (Суммаси + жами). size 10
    "summa_1":    {"rect": [12.0, 1303.3, 63.3, 1315.8], "size": 10},
    "summa_2":    {"rect": [14.2, 1371.6, 65.4, 1384.1], "size": 10},
    # 12: amount in Russian words "Десять тысяч рублей 00 копеек", wraps. size 10
    "propis":     {"rect": [14.2, 1403.6, 123.8, 1416.1], "size": 10},
}

MONTHS_RU = ["января","февраля","марта","апреля","мая","июня",
             "июля","августа","сентября","октября","ноября","декабря"]


#: What each field is called on screen while it is being arranged, and a sample
#: of it — so the office sees the real thing in the real face and size.
SAMPLES: tuple[tuple[str, str, str], ...] = (
    ("datetime", "Сана ва вақт", "20 июля 2026 10:11:12 мск"),
    ("fio_l1", "Ф.И.О. — 1-қатор", "ИСАКОВ ШАХБОЗ"),
    ("fio_l2", "Ф.И.О. — 2-қатор", "БАХТИЁРОВИЧ"),
    ("card4", "Карта охирги 4", "1234"),
    ("inn", "ИНН", "123456789012"),
    ("ism", "Исм", "ШАХБОЗ"),
    ("otch", "Отчество", "БАХТИЁРОВИЧ"),
    ("fam", "Фамилия", "ИСАКОВ"),
    ("inn12", "121000000000 + ИНН", "121000000000123456789012"),
    ("sana_baza", "База сана", "10445252250090062007202611071538"),
    ("avtoriz", "Код авторизации", "123456"),
    ("summa_1", "Сумма (юқорида)", "15 000,50 ₽"),
    ("summa_2", "Сумма (жами)", "15 000,50 ₽"),
    ("propis", "Сумма сўз билан", "Пятнадцать тысяч рублей 50 копеек"),
)

#: The face the receipt is set in, for the arranging screen.
SCREEN_FONT = "Microsoft Sans Serif"
