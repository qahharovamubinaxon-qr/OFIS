"""A firm typed in by hand, for when there is no template to upload.

The office knows its own requisites; what it does not always have is a Word
file from that firm. These are the details the two documents need in order to
be built from nothing — everything else on the page is the worker's, and comes
from the passport and the patent.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domain.enums import LegalForm

_DIGITS = re.compile(r"\D")


def _digits(value: str) -> str:
    return _DIGITS.sub("", value or "")


class FirmDetails(BaseModel):
    """Requisites of a Трудовой firm entered by hand."""

    model_config = ConfigDict(str_strip_whitespace=True)

    legal_form: LegalForm = LegalForm.OOO
    name: str                       # ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СФЕРА"
    short_name: str = ""            # ООО "СФЕРА"
    inn: str = ""
    kpp: str = ""                   # юр. лицо only — ИП has none
    ogrn: str = ""                  # ОГРН (13) or ОГРНИП (15)
    okved: str = ""
    address: str = ""               # юридический адрес
    district: str = ""              # район / городской округ
    mvd_office: str = ""            # территориальный орган МВД России
    director: str = ""              # Ф.И.О. руководителя (или самого ИП)
    director_position: str = "Генеральный директор"
    phone: str = ""
    stamp_path: Path | None = None  # печать, PNG (прозрачный фон)

    @field_validator("inn", "kpp", "ogrn", mode="before")
    @classmethod
    def _only_digits(cls, value: object) -> str:
        return _digits(str(value or ""))

    @model_validator(mode="after")
    def _check(self) -> "FirmDetails":
        if not self.name:
            raise ValueError("Фирма номи керак")
        if self.inn and len(self.inn) not in (10, 12):
            raise ValueError("ИНН 10 та (юр. лицо) ёки 12 та (ИП) рақам бўлади")
        if self.legal_form is LegalForm.IP:
            if self.kpp:
                raise ValueError("ИП да КПП бўлмайди")
            if self.ogrn and len(self.ogrn) != 15:
                raise ValueError("ОГРНИП 15 та рақам бўлади")
        else:
            if self.kpp and len(self.kpp) != 9:
                raise ValueError("КПП 9 та рақам бўлади")
            if self.ogrn and len(self.ogrn) != 13:
                raise ValueError("ОГРН 13 та рақам бўлади")
        if self.stamp_path is not None and self.stamp_path.suffix.lower() != ".png":
            raise ValueError("Печать PNG форматда бўлиши керак")
        return self

    # ------------------------------------------------------------------
    @property
    def is_ip(self) -> bool:
        return self.legal_form is LegalForm.IP

    @property
    def display_name(self) -> str:
        return self.short_name or self.name

    @property
    def ogrn_label(self) -> str:
        return "ОГРНИП" if self.is_ip else "ОГРН"

    @property
    def status_line(self) -> str:
        return ("Индивидуальный предприниматель" if self.is_ip
                else "Юридическое лицо")

    @property
    def signatory(self) -> str:
        """Who signs — the director, or the предприниматель themselves."""
        return self.director or self.display_name

    @property
    def signatory_position(self) -> str:
        return ("Индивидуальный предприниматель" if self.is_ip
                else self.director_position or "Генеральный директор")

    def requisites(self) -> list[tuple[str, str]]:
        """Label/value pairs as the documents print them, blanks dropped."""
        pairs = [("ИНН", self.inn), ("КПП", self.kpp),
                 (self.ogrn_label, self.ogrn), ("ОКВЭД", self.okved)]
        return [(label, value) for label, value in pairs if value]

    def acting_clause(self) -> str:
        """«…в лице Генерального директора …, действующего на основании Устава»."""
        if self.is_ip:
            # the предприниматель is the person — «в лице» would name them twice
            return (f"{self.display_name}, действующий на основании"
                    " свидетельства о государственной регистрации")
        who = (f" в лице {_genitive(self.signatory_position)} {self.signatory},"
               if self.signatory else ",")
        return f"{self.display_name}{who} действующего на основании Устава"


_GENITIVE = {"директор": "директора", "предприниматель": "предпринимателя",
             "руководитель": "руководителя", "president": "президента",
             "президент": "президента", "управляющий": "управляющего",
             "заведующий": "заведующего", "начальник": "начальника"}


def _genitive(position: str) -> str:
    """«Генеральный директор» → «Генерального директора».

    Only the handful of titles a firm actually signs with; anything else the
    office typed is left exactly as typed rather than mangled by a guess.
    """
    words = position.split()
    out: list[str] = []
    for word in words:
        low = word.lower()
        if low in _GENITIVE:
            out.append(_GENITIVE[low])
        elif low.endswith(("ый", "ий")):
            out.append(word[:-2] + "ого")
        elif low.endswith("ой"):
            out.append(word[:-2] + "ого")
        else:
            return position
    return " ".join(out)
