"""РУС РЕГ — the view's door to reading documents and printing the sheet.

Two documents can stand behind one sheet: a **Russian internal passport** for
a grown worker, a **birth certificate** for a worker's child. Whichever image
the operator drops decides what the form's «вид» line will say — the sheet
must name the document it was actually issued against — so the controller
keeps track of which one was read, not just what it said.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from src.ai.russian import RUSSIAN_RULES
from src.common.logging import get_logger
from src.domain.enums import DocType
from src.ocr.mrz_reader import strip_document_check_digit
from src.ocr.preprocess import prepare_image
from src.ocr.service import OcrService
from src.pdf.rusreg_renderer import RusRegData
from src.services.rusreg_service import RusRegResult, RusRegService

log = get_logger(__name__)

#: The Russian internal passport and the birth certificate are not the foreign
#: passports the standard prompt is tuned to, so each gets its own ask.
_PASSPORT_PROMPT = RUSSIAN_RULES + """\
Ты — OCR для российских документов. На фото — ПАСПОРТ ГРАЖДАНИНА РФ
(внутренний), возможно оба разворота.

Прочитай и верни СТРОГО JSON, без пояснений и без markdown:
{
 "surname": "<фамилия>",
 "name": "<имя>",
 "patronymic": "<отчество, если есть>",
 "birth_date": "<дата рождения, ДД.ММ.ГГГГ>",
 "birth_place": "<место рождения РОВНО как напечатано>",
 "series": "<серия — 4 цифры, с пробелом как напечатано, например 45 25>",
 "number": "<номер — 6 цифр>",
 "issue_date": "<дата выдачи, ДД.ММ.ГГГГ>",
 "issued_by": "<кем выдан, РОВНО как напечатано>"
}

ПРАВИЛА:
- любое значение — СТРОКА; ведущие нули НЕ терять;
- серию и номер НЕ объединять и ничего к ним не добавлять;
- если чего-то не видно — верни пустую строку "".
"""

_BIRTH_PROMPT = RUSSIAN_RULES + """\
Ты — OCR для российских документов. На фото — СВИДЕТЕЛЬСТВО О РОЖДЕНИИ
(метрика), выданное в России.

Прочитай и верни СТРОГО JSON, без пояснений и без markdown:
{
 "surname": "<фамилия ребёнка>",
 "name": "<имя ребёнка>",
 "patronymic": "<отчество ребёнка, если есть>",
 "birth_date": "<дата рождения, ДД.ММ.ГГГГ>",
 "birth_place": "<место рождения РОВНО как напечатано>",
 "series": "<серия бланка, например X-МЮ или IV-АБ>",
 "number": "<номер бланка — 6 цифр>",
 "issue_date": "<дата выдачи, ДД.ММ.ГГГГ>",
 "issued_by": "<орган ЗАГС, выдавший свидетельство, РОВНО как напечатано>"
}

ПРАВИЛА:
- любое значение — СТРОКА; ведущие нули НЕ терять;
- если чего-то не видно — верни пустую строку "".
"""


def _fields_from(text: str) -> dict[str, str]:
    """The JSON out of whatever wrapper the model put around it."""
    raw = (text or "").strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return {k: str(v or "").strip() for k, v in data.items()} \
        if isinstance(data, dict) else {}


class RusRegController:
    def __init__(self, ocr: OcrService, service: RusRegService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, source: Path) -> Path:
        return self._service.add_template(name, source)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def reset_layout(self, template: Path) -> None:
        self._service.reset_layout(template)

    def addresses(self) -> list[str]:
        return self._service.addresses()

    def remembered(self) -> dict[str, str]:
        """What the office typed last time, to put back into the fields."""
        return {"address": self._service.address(),
                "firm": self._service.firm(),
                "reg_number": self._service.reg_number(),
                "signer": self._service.signer()}

    # ------------------------------------------------------------ reading
    def read_document(self, image: bytes, *, is_passport: bool) -> dict[str, str]:
        """The sheet's fields off a паспорт РФ or a birth certificate.

        Read through :data:`DocType.UNKNOWN` on purpose. The PASSPORT schema
        judges the answer against the foreign-passport shape and insists its
        dates parse as ISO — while these prompts ask for ДД.ММ.ГГГГ, so every
        answer died with «birth_date санаси ўқилмади» and the operator got an
        error instead of the fields. UNKNOWN takes the flat strings as they
        are; whatever cannot be read stays empty and is typed by hand.
        """
        prompt = _PASSPORT_PROMPT if is_passport else _BIRTH_PROMPT
        answer = self._ocr.ai.extract(prepare_image(image),
                                      DocType.UNKNOWN, prompt)
        fields = dict(answer.fields) if answer.fields else {}
        if not fields.get("surname"):
            fields.update(_fields_from(answer.text))
        # a model shown the machine zone hands the check digit back too
        series = fields.get("series", "")
        if series and not series.replace(" ", "").isdigit():
            fields["series"] = strip_document_check_digit(series)
        return {k: (fields.get(k) or "").strip() for k in
                ("surname", "name", "patronymic", "birth_date", "birth_place",
                 "series", "number", "issue_date", "issued_by")}

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    # ----------------------------------------------------------- printing
    def generate(self, *, template: Path | None, **kwargs) -> RusRegResult:
        data = RusRegData(**kwargs)
        return self._service.generate(data, template)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()
