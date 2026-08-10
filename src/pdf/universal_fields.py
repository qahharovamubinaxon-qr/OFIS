"""УНИВЕРСАЛ — every text the office can put on a blank of its own.

The office was clear about why this exists: it does not want a new section
written for every new form. It wants to upload the empty form, drag the texts
where they belong, name the arrangement and keep it — and from then on drop a
worker's passport and get that form filled.

So this file is the LIST of things a text can be. Nothing here knows about any
one form; a form is only ever a blank plus a set of these keys with positions.

Three groups, and one open end
------------------------------
*The worker* — read off his passport and patent. His name whole and in three
pieces, his birth date whole and split into day, month and year, and the month
in words as well, because a Russian form as often wants «11 авг 2026» as
«11.08.2026».

*The documents* — six free серия/номер pairs. The office asked for six by
name: a worker arrives with a passport, a patent, a migration card, a
registration, a medical book and whatever else the month has invented, and
each carries a series and a number that some form wants together and another
wants apart.

*The dates and the places* — the day the paper is issued, the day it runs out,
who issued it, the region, the address, the position held.

*And whatever else* — a key of the form ``custom:Название`` is a box the office
made up itself, with the name it typed. Those are why this section does not
need extending every time a new form appears.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from src.pdf.trud8_fields import (
    BLACK,
    DEFAULT_BASELINE,
    DEFAULT_SIZE,
    DEFAULT_X,
    Field,
)

#: How many серия/номер pairs the office gets. Six, because that is what it
#: asked for — «серия номер 1 … серия номер 6».
DOC_SLOTS = 6

#: Pictures rather than words. Each is placed like a text but drawn as itself,
#: and its `size` is its HEIGHT on the page.
PHOTO = "photo"
STAMP = "stamp"
SIGNATURE = "signature"
PICTURES = (PHOTO, STAMP, SIGNATURE)
PICTURE_LABELS = {
    PHOTO: "🖼 Ишчининг расми",
    STAMP: "🔴 Печать",
    SIGNATURE: "✒️ Имзо",
}

#: What a custom text's key starts with. Everything after it is the name the
#: office typed, and that name is also what the box is called on screen.
CUSTOM = "custom:"

MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_RU_SHORT = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг",
                   "сен", "окт", "ноя", "дек")


def _dates(prefix: str, name: str) -> dict[str, str]:
    """One date, offered every way a Russian form ever asks for it."""
    return {
        f"{prefix}": f"{name} (КК.ОО.ЙЙЙЙ)",
        f"{prefix}_day": f"{name} — куни",
        f"{prefix}_month": f"{name} — ойи (сон)",
        f"{prefix}_month_ru": f"{name} — ойи (сўз: августа)",
        f"{prefix}_month_short": f"{name} — ойи (қисқа: авг)",
        f"{prefix}_year": f"{name} — йили",
        f"{prefix}_year_short": f"{name} — йили (2 рақам)",
        f"{prefix}_words": f"{name} — тўлиқ сўз билан (11 августа 2026)",
        f"{prefix}_short": f"{name} — қисқа (11 авг 2026)",
    }


def _catalogue() -> dict[str, str]:
    made: dict[str, str] = {
        # ---- the worker
        "fio": "ФИО — тўлиқ (Фамилия Исм Отчество)",
        "fio_upper": "ФИО — БОШ ҲАРФЛАРДА",
        "surname": "Фамилия",
        "name": "Исм",
        "patronymic": "Отчество",
        "gender": "Жинси (Мужской/Женский)",
        "citizenship": "Гражданство",
        "birth_place": "Туғилган жой",
    }
    made.update(_dates("birth", "Туғилган сана"))
    # ---- the passport, by name
    made.update({
        "pass_series": "Паспорт — серия",
        "pass_number": "Паспорт — номер",
        "pass_full": "Паспорт — серия ва номер бирга",
        "pass_pin": "Паспорт — ПИН (ПИНФЛ)",
        "pass_issued_by": "Паспорт — ким берган (кем выдан)",
    })
    made.update(_dates("pass_issued", "Паспорт — берилган сана"))
    made.update(_dates("pass_expires", "Паспорт — амал қилиш охири"))
    # ---- the patent, by name
    made.update({
        "pat_series": "Патент — серия",
        "pat_number": "Патент — номер",
        "pat_full": "Патент — серия ва номер бирга",
        "pat_blank_series": "Патент — бланка серияси",
        "pat_blank_number": "Патент — бланка номери",
        "pat_blank_full": "Патент — бланка серия ва номер бирга",
        "pat_issued_by": "Патент — ким берган (кем выдан)",
        "pat_region": "Патент — регион (серия бўйича ўзи чиқади)",
    })
    made.update(_dates("pat_issued", "Патент — берилган сана"))
    made.update(_dates("pat_expires", "Патент — амал қилиш охири"))
    # ---- and six free pairs for everything else a worker arrives with:
    # the migration card, the registration, the medical book…
    for slot in range(1, DOC_SLOTS + 1):
        made[f"doc{slot}_series"] = f"Бошқа ҳужжат {slot} — серия"
        made[f"doc{slot}_number"] = f"Бошқа ҳужжат {slot} — номер"
        made[f"doc{slot}_full"] = f"Бошқа ҳужжат {slot} — серия ва номер бирга"
    # ---- the dates on the paper itself
    made.update(_dates("issued", "Берилган сана"))
    made.update(_dates("expires", "Тугаш санаси"))
    made.update(_dates("today", "Бугунги сана"))
    # ---- the rest
    made.update({
        "issued_by": "Ким берган (кем выдан)",
        "region": "Регион",
        "address": "Адрес",
        "position": "Должность / касби",
        "organisation": "Ташкилот / фирма",
        "note": "Изоҳ (эркин матн)",
    })
    for key in PICTURES:
        made[key] = PICTURE_LABELS[key]
    return made


#: key → what the office sees in the picker.
CATALOGUE: dict[str, str] = _catalogue()

#: What stands in for a value while it is being dragged, so the office can see
#: how wide the real thing will be before a worker is anywhere near it.
SAMPLES: dict[str, str] = {
    "fio": "Исоев Аслидин Холбердиевич",
    "fio_upper": "ИСОЕВ АСЛИДИН ХОЛБЕРДИЕВИЧ",
    "surname": "Исоев", "name": "Аслидин", "patronymic": "Холбердиевич",
    "gender": "Мужской", "citizenship": "Таджикистан",
    "birth_place": "Таджикистан",
    "issued_by": "ГУ МВД России по г. Москве",
    "region": "77", "address": "г Москва, ул Тагильская, д 45, кв 12",
    "position": "Подсобный рабочий",
    "organisation": 'ООО "ГОРСТРОЙ"',
    "note": "изоҳ",
    "pass_series": "P", "pass_number": "405847273",
    "pass_full": "P 405847273", "pass_pin": "50707994120019",
    "pass_issued_by": "ХШБ дар Ч.Балхи",
    "pat_series": "77", "pat_number": "2400796702",
    "pat_full": "77 2400796702",
    "pat_blank_series": "77", "pat_blank_number": "24012345678",
    "pat_blank_full": "77 24012345678",
    "pat_issued_by": "ГУ МВД России по г. Москве",
    "pat_region": "Москва",
    PHOTO: "РАСМ", STAMP: "ПЕЧАТЬ", SIGNATURE: "ИМЗО",
}
for _slot in range(1, DOC_SLOTS + 1):
    SAMPLES[f"doc{_slot}_series"] = "77"
    SAMPLES[f"doc{_slot}_number"] = "2400796702"
    SAMPLES[f"doc{_slot}_full"] = "77 2400796702"
for _prefix, _day in (("birth", date(1999, 7, 25)), ("issued", date(2025, 1, 18)),
                      ("expires", date(2035, 1, 17)), ("today", date(2026, 8, 10)),
                      ("pass_issued", date(2025, 1, 18)),
                      ("pass_expires", date(2035, 1, 17)),
                      ("pat_issued", date(2025, 3, 4)),
                      ("pat_expires", date(2026, 3, 3))):
    SAMPLES[_prefix] = _day.strftime("%d.%m.%Y")
    SAMPLES[f"{_prefix}_day"] = f"{_day.day:02d}"
    SAMPLES[f"{_prefix}_month"] = f"{_day.month:02d}"
    SAMPLES[f"{_prefix}_month_ru"] = MONTHS_RU[_day.month - 1]
    SAMPLES[f"{_prefix}_month_short"] = MONTHS_RU_SHORT[_day.month - 1]
    SAMPLES[f"{_prefix}_year"] = str(_day.year)
    SAMPLES[f"{_prefix}_year_short"] = str(_day.year)[2:]
    SAMPLES[f"{_prefix}_words"] = (f"{_day.day} {MONTHS_RU[_day.month - 1]} "
                                   f"{_day.year}")
    SAMPLES[f"{_prefix}_short"] = (f"{_day.day} "
                                   f"{MONTHS_RU_SHORT[_day.month - 1]} "
                                   f"{_day.year}")


def is_custom(key: str) -> bool:
    return key.startswith(CUSTOM)


def custom_name(key: str) -> str:
    """«custom:Договор №» → «Договор №»."""
    return key[len(CUSTOM):] if is_custom(key) else key


def custom_key(name: str) -> str:
    return CUSTOM + " ".join((name or "").split())


def label_of(key: str) -> str:
    if is_custom(key):
        return f"✎ {custom_name(key)}"
    return CATALOGUE.get(key, key)


def sample_of(key: str) -> str:
    if is_custom(key):
        return custom_name(key)
    return SAMPLES.get(key, CATALOGUE.get(key, key))


def catalogue_with(keys) -> dict[str, str]:
    """The picker's list, with whatever custom boxes this blank already has."""
    made = dict(CATALOGUE)
    for key in keys:
        if is_custom(key):
            made[key] = label_of(key)
    return made


def samples_with(keys) -> dict[str, str]:
    made = dict(SAMPLES)
    for key in keys:
        if is_custom(key):
            made[key] = sample_of(key)
    return made


# ------------------------------------------------------------ the worker
@dataclass
class UniversalData:
    """Everything the office may type or the reader may fill in.

    Deliberately flat and all-optional: a blank uses the handful of keys the
    office dragged onto it and ignores the rest, so one shape serves every
    form the office will ever upload.
    """

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    gender: str = ""
    citizenship: str = ""
    birth_place: str = ""
    birth_date: date | None = None
    # ---- the passport, by name
    pass_series: str = ""
    pass_number: str = ""
    pass_pin: str = ""
    pass_issued_by: str = ""
    pass_issued: date | None = None
    pass_expires: date | None = None
    # ---- the patent, by name
    pat_series: str = ""
    pat_number: str = ""
    pat_blank_series: str = ""
    pat_blank_number: str = ""
    pat_issued_by: str = ""
    pat_region: str = ""
    pat_issued: date | None = None
    pat_expires: date | None = None
    #: slot → (series, number), 1…6 — for everything else a worker brings
    documents: dict[int, tuple[str, str]] = field(default_factory=dict)
    issued: date | None = None
    expires: date | None = None
    issued_by: str = ""
    region: str = ""
    address: str = ""
    position: str = ""
    organisation: str = ""
    note: str = ""
    #: custom key (with its «custom:» head) → what the office typed
    custom: dict[str, str] = field(default_factory=dict)
    #: pictures, as PNG bytes
    photo_png: bytes | None = None
    stamp_png: bytes | None = None
    signature_png: bytes | None = None

    def fio(self) -> str:
        return " ".join(p for p in (self.surname, self.name, self.patronymic)
                        if (p or "").strip())

    def picture(self, key: str) -> bytes | None:
        return {PHOTO: self.photo_png, STAMP: self.stamp_png,
                SIGNATURE: self.signature_png}.get(key)


def _spread(out: dict[str, str], prefix: str, when: date | None) -> None:
    if when is None:
        for suffix in ("", "_day", "_month", "_month_ru", "_month_short",
                       "_year", "_year_short", "_words", "_short"):
            out[prefix + suffix] = ""
        return
    out[prefix] = when.strftime("%d.%m.%Y")
    out[f"{prefix}_day"] = f"{when.day:02d}"
    out[f"{prefix}_month"] = f"{when.month:02d}"
    out[f"{prefix}_month_ru"] = MONTHS_RU[when.month - 1]
    out[f"{prefix}_month_short"] = MONTHS_RU_SHORT[when.month - 1]
    out[f"{prefix}_year"] = str(when.year)
    out[f"{prefix}_year_short"] = str(when.year)[2:]
    out[f"{prefix}_words"] = f"{when.day} {MONTHS_RU[when.month - 1]} {when.year}"
    out[f"{prefix}_short"] = (f"{when.day} {MONTHS_RU_SHORT[when.month - 1]} "
                              f"{when.year}")


def values(data: UniversalData) -> dict[str, str]:
    """Every key's text for THIS worker. Missing ones come back empty."""
    out: dict[str, str] = {
        "fio": data.fio(),
        "fio_upper": data.fio().upper(),
        "surname": (data.surname or "").strip(),
        "name": (data.name or "").strip(),
        "patronymic": (data.patronymic or "").strip(),
        "gender": (data.gender or "").strip(),
        "citizenship": (data.citizenship or "").strip(),
        "birth_place": (data.birth_place or "").strip(),
        "issued_by": (data.issued_by or "").strip(),
        "region": (data.region or "").strip(),
        "address": (data.address or "").strip(),
        "position": (data.position or "").strip(),
        "organisation": (data.organisation or "").strip(),
        "note": (data.note or "").strip(),
    }
    # the passport and the patent, each by its own name
    for prefix, series, number in (
        ("pass", data.pass_series, data.pass_number),
        ("pat", data.pat_series, data.pat_number),
        ("pat_blank", data.pat_blank_series, data.pat_blank_number),
    ):
        series, number = (series or "").strip(), (number or "").strip()
        out[f"{prefix}_series"] = series
        out[f"{prefix}_number"] = number
        out[f"{prefix}_full"] = " ".join(p for p in (series, number) if p)
    out["pass_pin"] = (data.pass_pin or "").strip()
    out["pass_issued_by"] = (data.pass_issued_by or "").strip()
    out["pat_issued_by"] = (data.pat_issued_by or "").strip()
    out["pat_region"] = (data.pat_region or "").strip()

    _spread(out, "birth", data.birth_date)
    _spread(out, "issued", data.issued)
    _spread(out, "expires", data.expires)
    _spread(out, "today", date.today())
    _spread(out, "pass_issued", data.pass_issued)
    _spread(out, "pass_expires", data.pass_expires)
    _spread(out, "pat_issued", data.pat_issued)
    _spread(out, "pat_expires", data.pat_expires)
    for slot in range(1, DOC_SLOTS + 1):
        series, number = data.documents.get(slot, ("", ""))
        series, number = (series or "").strip(), (number or "").strip()
        out[f"doc{slot}_series"] = series
        out[f"doc{slot}_number"] = number
        out[f"doc{slot}_full"] = " ".join(p for p in (series, number) if p)
    for key, said in (data.custom or {}).items():
        out[key] = (said or "").strip()
    return out


def output_stem(data: UniversalData, blank: str = "") -> str:
    """«ИСОЕВ_АСЛИДИН» — the worker, and the form when he has no name yet."""
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or " ".join((blank or "UNIVERSAL").split())
    return "".join(c for c in stem if c.isalnum() or c in "_-") or "UNIVERSAL"


__all__ = ["CATALOGUE", "CUSTOM", "DOC_SLOTS", "MONTHS_RU", "MONTHS_RU_SHORT",
           "PHOTO", "PICTURES", "PICTURE_LABELS", "SAMPLES", "SIGNATURE",
           "STAMP", "BLACK", "DEFAULT_BASELINE", "DEFAULT_SIZE", "DEFAULT_X",
           "Field", "UniversalData", "catalogue_with", "custom_key",
           "custom_name", "is_custom", "label_of", "output_stem", "replace",
           "sample_of", "samples_with", "values"]
