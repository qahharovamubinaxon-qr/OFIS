"""What a text on an АЛЬЯНСКОТ blank can mean, and the two pictures it can
carry.

The office uploads its own удостоверение/справка blanks and places these
itself — so, exactly like ТРУД-8, nothing may be chosen that the program
cannot fill. The ``Field`` dataclass is re-exported from ТРУД-8 so the
arranger and the saved layout JSON are byte-for-byte identical.
"""

from __future__ import annotations

from src.pdf.trud8_fields import (
    DEFAULT_BASELINE,
    DEFAULT_SIZE,
    DEFAULT_X,
    Field,
)

#: key → what the operator sees in the picker
CATALOGUE: dict[str, str] = {
    "fio": "ФИО — тўлиқ (Фамилия Исм Отчество)",
    "fio_upper": "ФИО — БОШ ҲАРФЛАРДА",
    "surname": "Фамилия",
    "name": "Исм",
    "patronymic": "Отчество",
    "gender": "Жинси (Мужской/Женский)",
    "ud_number": "Удостоверение №",
    "dolzhnost": "Должность",
    "start_date": "Бошланиш санаси (КК.ОО.ЙЙЙЙ)",
    "end_date": "Тугаш санаси (+3 йил, КК.ОО.ЙЙЙЙ)",
}

#: What each key shows while the office is dragging it into place.
SAMPLES: dict[str, str] = {
    "fio": "Ашуров Дилмурод Суюнбоевич",
    "fio_upper": "АШУРОВ ДИЛМУРОД СУЮНБОЕВИЧ",
    "surname": "Ашуров", "name": "Дилмурод", "patronymic": "Суюнбоевич",
    "gender": "Мужской",
    "ud_number": "2400-0145",
    "dolzhnost": "ПОДСОБНЫЙ РАБОЧИЙ",
    "start_date": "07.09.2026", "end_date": "07.09.2029",
}

#: The two pictures a blank can carry — placed like everything else.
IMG_KEYS: tuple[str, ...] = ("img_photo", "img_sign")
IMG_LABELS: dict[str, str] = {
    "img_photo": "🖼 РАСМ (3×4)",
    "img_sign": "✒ ИМЗО",
}

__all__ = ["CATALOGUE", "SAMPLES", "IMG_KEYS", "IMG_LABELS", "Field",
           "DEFAULT_X", "DEFAULT_BASELINE", "DEFAULT_SIZE"]
