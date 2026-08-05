"""ТРУД ППУ controller — four documents in, one editable form out.

The трудовой договор and the уведомление are PDFs the office already has, so
they are read from their own TEXT where they have any (exact, free, instant) and
only photographed and sent to the AI when they turn out to be scans. The patent
goes through the ordinary patent reader.

Every answer is a suggestion. All of them stay editable on screen: a firm name
or a contract date that is wrong on a filed package is not a small thing, and
the operator has the paper in front of him.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from src.ai.russian import RUSSIAN_RULES
from src.ai.text_client import ask
from src.common.errors import OfisError
from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.trud_ppu_service import TrudPpuResult, TrudPpuService

log = get_logger(__name__)

#: Below this much extractable text a PDF is treated as a scan and photographed.
_TEXT_FLOOR = 150

_CONTRACT_PROMPT = RUSSIAN_RULES + """Ты читаешь ТРУДОВОЙ ДОГОВОР, заключённый российской \
организацией с иностранным работником.

Найди и верни СТРОГО JSON, без пояснений и без markdown:
{{
 "contract_date": "<дата заключения договора, ДД.ММ.ГГГГ>",
 "firm": "<работодатель ровно как написано, вместе с ООО и кавычками, \
например: ООО \\"ЭКСПЕРТ\\">",
 "surname": "<фамилия работника>",
 "name": "<имя работника>",
 "patronymic": "<отчество работника, если есть>",
 "birth_date": "<дата рождения работника, ДД.ММ.ГГГГ>",
 "gender": "<Мужской или Женский>",
 "citizenship": "<гражданство работника>",
 "passport": "<серия и номер паспорта РОВНО как напечатано; серию НЕ выдумывать>"
}}

ПРАВИЛА:
- любое значение — СТРОКА; ведущие нули не терять;
- если чего-то в документе нет — верни пустую строку "";
- дата заключения договора — та, что стоит рядом с городом в начале договора, \
а НЕ дата начала работы и НЕ дата рождения;
- работодатель — организация, а не работник.

{payload}"""

_UVED_PROMPT = """Ты читаешь УВЕДОМЛЕНИЕ о заключении трудового договора с \
иностранным гражданином (уведомление в МВД России).

Найди и верни СТРОГО JSON, без пояснений и без markdown:
{{
 "number": "<номер уведомления — длинное число сверху документа, только цифры>",
 "surname": "<фамилия работника>",
 "name": "<имя работника>",
 "patronymic": "<отчество работника, если есть>"
}}

ПРАВИЛА:
- любое значение — СТРОКА; ведущие нули НЕ терять — номер часто начинается с 0;
- номер уведомления — это одно число из 8-14 цифр наверху документа. Не путай \
его с ИНН (12 цифр внутри таблицы), с номером патента и с датами;
- если чего-то в документе нет — верни пустую строку "".

{payload}"""


_PATENT_EXTRA_PROMPT = """На фотографиях РАБОЧИЙ ПАТЕНТ иностранного гражданина \
(российская карточка «ПАТЕНТ»), возможно с обеих сторон.

Прочитай и верни СТРОГО JSON, без пояснений и без markdown:
{{
 "birth_date": "<дата рождения, ДД.ММ.ГГГГ>",
 "citizenship": "<гражданство, например УЗБЕКИСТАН или ТАДЖИКИСТАН>",
 "passport": "<серия и номер документа РОВНО как напечатано, ничего не \
добавляя и не выдумывая>",
 "gender": "<Мужской или Женский, если указан>"
}}

ПРАВИЛА:
- любое значение — СТРОКА; ведущие нули НЕ терять;
- поле «Документ, удостоверяющий личность» на патенте содержит серию и номер \
паспорта, а рядом может стоять ИНН из 12 цифр — ИНН НЕ БРАТЬ;
- серию НЕ ДОБАВЛЯТЬ и НЕ ВЫДУМЫВАТЬ: у таджикских паспортов серии нет, там \
только цифры. Если букв в документе не напечатано — букв в ответе быть не должно;
- если чего-то на патенте нет — верни пустую строку "".

{payload}"""

#: Russian and Uzbek patronymic endings. A patent does not print «Пол», and the
#: ППУ front has a «Пол» row that has to say something — the patronymic says it.
_MALE_ENDINGS = ("ович", "евич", "ич", "ўғли", "угли", "оглы", "уулу")
_FEMALE_ENDINGS = ("овна", "евна", "ична", "инична", "қизи", "кизи", "кызы")


def gender_from_patronymic(patronymic: str) -> str:
    """«Зафаровна» → «Женский», «Абдулохонович» → «Мужской», else «»."""
    word = " ".join((patronymic or "").split()).lower()
    if not word:
        return ""
    for ending in _FEMALE_ENDINGS:
        if word.endswith(ending):
            return "Женский"
    for ending in _MALE_ENDINGS:
        if word.endswith(ending):
            return "Мужской"
    return ""


def _pdf_text(data: bytes) -> str:
    import fitz

    try:
        with fitz.open("pdf", data) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as exc:                      # noqa: BLE001
        log.warning("ТРУД ППУ: PDF матни ўқилмади: %s", exc)
        return ""


def _pdf_images(data: bytes, *, limit: int = 3, zoom: float = 2.0) -> list[bytes]:
    import fitz

    out: list[bytes] = []
    try:
        with fitz.open("pdf", data) as doc:
            for page in list(doc)[:limit]:
                shot = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                out.append(shot.tobytes("png"))
    except Exception as exc:                      # noqa: BLE001
        log.warning("ТРУД ППУ: PDF расмга айланмади: %s", exc)
    return out


def _payload(data: bytes) -> tuple[str, list[bytes]]:
    """The document as the cheapest thing the AI can read it from.

    A PDF this program produced carries its own text, and reading that is exact
    and costs nothing. A photographed or scanned one has none, so its pages go
    up as pictures instead.
    """
    text = " ".join(_pdf_text(data).split())
    if len(text) >= _TEXT_FLOOR:
        return f"ТЕКСТ ДОКУМЕНТА:\n{text[:12000]}", []
    return "Документ приложен фотографиями.", _pdf_images(data)


def _answer(key: str, prompt: str, document: bytes) -> dict[str, str]:
    body, images = _payload(document)
    raw = ask(key, prompt.format(payload=body), images or None, json_out=True)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("ТРУД ППУ: AI жавоби JSON эмас: %r", raw[:200])
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): ("" if v is None else str(v)).strip()
            for k, v in parsed.items()}


class TrudPpuController:
    def __init__(self, ocr: OcrService, service: TrudPpuService,
                 key_getter=None) -> None:
        self._ocr = ocr
        self._service = service
        self._key_getter = key_getter or (lambda: "")

    # ------------------------------------------------------------- state
    def ai_available(self) -> bool:
        return self._ocr.available()

    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, page2: Path, page3: Path) -> Path:
        return self._service.add_template(name, page2, page3)

    # ------------------------------------------------------------ readers
    def read_contract(self, pdf: bytes) -> dict[str, str]:
        """The contract's date, the firm, and the worker it names."""
        answer = _answer(self._key_getter(), _CONTRACT_PROMPT, pdf)
        return {
            "contract_date": answer.get("contract_date", ""),
            "firm": _firm(answer.get("firm", "")),
            "surname": answer.get("surname", ""),
            "name": answer.get("name", ""),
            "patronymic": answer.get("patronymic", ""),
            "birth_date": answer.get("birth_date", ""),
            "gender": answer.get("gender", ""),
            "citizenship": answer.get("citizenship", ""),
            "document": answer.get("passport", ""),
        }

    def read_uved(self, pdf: bytes) -> dict[str, str]:
        """The notification's number and the Ф.И.О. it was accepted for."""
        answer = _answer(self._key_getter(), _UVED_PROMPT, pdf)
        parts = [answer.get("surname", ""), answer.get("name", ""),
                 answer.get("patronymic", "")]
        number = _digits(answer.get("number", ""))
        if not number:
            number = uved_number_from_text(_pdf_text(pdf))
        return {
            "uved_number": number,
            "uved_fio": " ".join(p for p in parts if p),
        }

    def read_patent(self, front: bytes, back: bytes | None = None) -> dict[str, str]:
        """The patent's series, number and issue date, off the patent itself."""
        patent = self._ocr.read_patent(front, back)
        patronymic = (patent.holder_patronymic or "").strip()
        # The ППУ front sheet also wants the date of birth, the sex and the
        # passport, and the Patent model carries none of the three. The трудовой
        # договор often does not either — which is why the office's first
        # packages came out with «Дата рождения», «Пол» and «Иностранный
        # паспорт» blank. They are all on the patent card, so they are read off
        # it here with one free-form call.
        extra = self._patent_extra(front, back)
        fields = {
            "patent_series": (patent.series or "").strip(),
            "patent_number": "".join((patent.number or "").split()),
            # the expiry is NOT taken from the patent: the office writes exactly
            # one year on from the issue date, and the screen derives it there
            "patent_issue": _dmy(patent.issue_date or patent.valid_from),
            "surname": (patent.holder_surname or "").strip(),
            "name": (patent.holder_name or "").strip(),
            "patronymic": patronymic,
            "citizenship": ((patent.holder_citizenship or "").strip()
                            or extra.get("citizenship", "")),
            "birth_date": extra.get("birth_date", ""),
            "document": _passport(extra.get("passport", "")),
        }
        # «Пол» is not printed on a patent at all. A patronymic tells it without
        # asking anyone: «…овна» is a woman, «…ович» and «…ўғли» a man.
        fields["gender"] = extra.get("gender", "") or gender_from_patronymic(
            patronymic)
        return fields

    def _patent_extra(self, front: bytes, back: bytes | None) -> dict[str, str]:
        """The three fields the Patent model does not carry, off the same card."""
        images = [i for i in (front, back) if i]
        try:
            raw = ask(self._key_getter(),
                      _PATENT_EXTRA_PROMPT.format(payload=""),
                      images, json_out=True)
            parsed = json.loads(raw)
        except (OfisError, json.JSONDecodeError, ValueError) as exc:
            log.warning("ТРУД ППУ: патентдан қўшимча майдонлар олинмади: %s", exc)
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(k): ("" if v is None else str(v)).strip()
                for k, v in parsed.items()}

    # --------------------------------------------------------- printing
    def generate(self, **kwargs) -> TrudPpuResult:
        return self._service.generate(**kwargs)

    @staticmethod
    def read_file(path: Path) -> bytes:
        return Path(path).read_bytes()

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _digits(text: str) -> str:
    """Only the digits, so «№ 4785796716» and «4785796716» both come out same."""
    return "".join(c for c in (text or "") if c.isdigit())


#: Where a notification's number is written, in the words used around it.
_UVED_LABELS = (
    r"уведомлени[ея][^\n]{0,40}?№",
    r"регистрационн\w+\s+номер[^\n]{0,20}?№?",
    r"№\s*уведомлени\w+",
)


def uved_number_from_text(text: str) -> str:
    """Find the notification's number in the document's own text.

    The reader misses it often: on the МВД form the number is a bare run of
    digits with nothing but a «№» beside it, and the form is full of other long
    numbers — the ИНН (twelve digits), the patent, the ОГРН, dates. So the text
    is searched by LABEL first, and a bare number is only accepted when it is
    8–14 digits, is not twelve (that is an ИНН), and is bounded by non-digits so
    two numbers running together are never read as one.
    """
    import re

    flat = " ".join((text or "").split())
    if not flat:
        return ""
    for label in _UVED_LABELS:
        found = re.search(label + r"\s*(?<!\d)(\d{8,14})(?!\d)", flat,
                          re.IGNORECASE)
        if found and len(found.group(1)) != 12:
            return found.group(1)
    # nothing labelled — take the first plausible long number in the opening of
    # the document, where the number is printed
    for run in re.findall(r"(?<!\d)(\d{8,14})(?!\d)", flat[:1200]):
        if len(run) != 12:
            return run
    return ""


def _passport(text: str) -> str:
    """«FA 7822242» / «FA7822242 / 072501692992» → «FA7822242».

    The patent prints the passport and the twelve-digit ИНН on ONE line, so a
    reader that hands both back has to be cut down to the first of them. A
    passport is letters-then-digits or 9–10 digits alone; an ИНН is exactly 12
    digits, and 12 digits are never a passport.
    """
    import re

    packed = "".join((text or "").split()).upper()
    if not packed:
        return ""
    match = re.search(r"[A-ZА-Я]{1,3}\d{6,9}", packed)
    if match:
        # the reader often copies the machine zone, where the nine document
        # characters are followed by their CHECK digit — «FB2254876» arrives
        # as «FB22548766». Taken back off only when the arithmetic proves it.
        from src.ocr.mrz_reader import strip_document_check_digit

        return strip_document_check_digit(match.group(0))
    for run in re.findall(r"\d+", packed):
        if 6 <= len(run) <= 10:
            return run
    return packed[:12]


def _firm(text: str) -> str:
    """The firm as the Госуслуги page shows it: «ООО “ЭКСПЕРТ”».

    The readers hand the name back with straight quotes, with none at all, or
    with the form spelled out. Only the quote marks are normalised — the name
    itself is left exactly as the contract writes it, because two firms in the
    office differ by one word.
    """
    text = " ".join((text or "").split())
    if not text:
        return ""
    quoted = re.search(r"[\"'«“]([^\"'»”]+)[\"'»”]", text)
    if quoted:
        form = text[:quoted.start()].strip() or "ООО"
        return f"{form} “{quoted.group(1).strip()}”"
    return text
