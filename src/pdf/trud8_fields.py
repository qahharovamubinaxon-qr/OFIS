"""What a text on a ТД/УВ blank can mean, and how it prints.

The office builds its own map: it uploads an empty PDF, adds a text, and
picks from THIS list what that text stands for. Everything the program can
read off the worker's documents is here — nothing else can be chosen, so a
field can never mean something the program cannot fill.
"""

from __future__ import annotations

from dataclasses import dataclass

#: key → what the operator sees in the picker
CATALOGUE: dict[str, str] = {
    "fio": "ФИО — тўлиқ (Фамилия Исм Отчество)",
    "surname": "Фамилия",
    "name": "Исм",
    "patronymic": "Отчество",
    "fio_upper": "ФИО — БОШ ҲАРФЛАРДА",
    "gender": "Жинси (Мужской/Женский)",
    "citizenship": "Гражданство",
    "birth_place": "Туғилган жой",
    "birth_date": "Туғилган сана (КК.ОО.ЙЙЙЙ)",
    "birth_day": "Туғилган сана — куни",
    "birth_month": "Туғилган сана — ойи",
    "birth_year": "Туғилган сана — йили",
    "pass_kind": "Ҳужжат тури (Иностранный паспорт)",
    "pass_series": "Паспорт — серия",
    "pass_number": "Паспорт — номер",
    "pass_full": "Паспорт — серия ва номер бирга",
    "pass_issued": "Паспорт — берилган сана",
    "pass_issued_by": "Паспорт — ким берган",
    "pat_kind": "Патент тури (Патент ИГ (ЛБГ))",
    "pat_series": "Патент — серия",
    "pat_number": "Патент — номер",
    "pat_full": "Патент — серия ва номер бирга",
    "pat_blank_series": "Патент — бланка серияси",
    "pat_blank_number": "Патент — бланка номери",
    "pat_issued": "Патент — берилган сана",
    "pat_valid_to": "Патент — амал қилиш охири",
    "profession": "Профессия / должность",
    "deal_date": "Шартнома санаси (КК.ОО.ЙЙЙЙ)",
    "deal_day": "Шартнома санаси — куни",
    "deal_month": "Шартнома санаси — ойи (сон)",
    "deal_month_ru": "Шартнома санаси — ойи (сўз билан)",
    "deal_year": "Шартнома санаси — йили",
    "deal_year_short": "Шартнома санаси — йили (2 рақам)",
    "work_address": "Иш жойи адреси",
}

#: What each key shows while the office is dragging it into place.
SAMPLES: dict[str, str] = {
    "fio": "Корёгдиев Тулкинжон Теша Угли",
    "surname": "Корёгдиев", "name": "Тулкинжон", "patronymic": "Теша Угли",
    "fio_upper": "КОРЁГДИЕВ ТУЛКИНЖОН ТЕША УГЛИ",
    "gender": "Мужской", "citizenship": "Узбекистан",
    "birth_place": "Узбекистан", "birth_date": "10.11.1994",
    "birth_day": "10", "birth_month": "11", "birth_year": "1994",
    "pass_kind": "Иностранный паспорт",
    "pass_series": "FA", "pass_number": "2533791",
    "pass_full": "FA 2533791", "pass_issued": "12.04.2021",
    "pass_issued_by": "MIA OF UZBEKISTAN",
    "pat_kind": "Патент ИГ (ЛБГ)",
    "pat_series": "77", "pat_number": "250695887",
    "pat_full": "77 250695887",
    "pat_blank_series": "ПР", "pat_blank_number": "5094937",
    "pat_issued": "01.07.2026", "pat_valid_to": "01.07.2027",
    "profession": "Разнорабочий",
    "deal_date": "02.08.2026", "deal_day": "02", "deal_month": "08",
    "deal_month_ru": "августа", "deal_year": "2026", "deal_year_short": "26",
    "work_address": "г. Москва, ул. Митинская, д. 50",
}

#: A brand-new text lands here until the office drags it.
DEFAULT_X = 0.1200
DEFAULT_BASELINE = 0.1500
DEFAULT_SIZE = 0.0130
BLACK = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Field:
    """One text the office placed on its own blank."""

    key: str
    page: int = 1
    x: float = DEFAULT_X
    baseline: float = DEFAULT_BASELINE
    size: float = DEFAULT_SIZE
    bold: bool = False
    serif: bool = True
    colour: tuple[float, float, float] = BLACK

    def label(self) -> str:
        return CATALOGUE.get(self.key, self.key)

    def sample(self) -> str:
        return SAMPLES.get(self.key, self.key)

    def as_dict(self) -> dict:
        return {"key": self.key, "page": self.page, "x": round(self.x, 4),
                "baseline": round(self.baseline, 4),
                "size": round(self.size, 4), "bold": self.bold,
                "serif": self.serif, "colour": list(self.colour)}

    @staticmethod
    def from_dict(raw: dict) -> Field:
        colour = raw.get("colour") or list(BLACK)
        return Field(key=str(raw.get("key") or ""),
                     page=int(raw.get("page") or 1),
                     x=float(raw.get("x", DEFAULT_X)),
                     baseline=float(raw.get("baseline", DEFAULT_BASELINE)),
                     size=float(raw.get("size", DEFAULT_SIZE)),
                     bold=bool(raw.get("bold", False)),
                     serif=bool(raw.get("serif", True)),
                     colour=tuple(float(c) for c in colour[:3]))
