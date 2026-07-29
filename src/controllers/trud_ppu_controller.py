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

from src.ai.text_client import ask
from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.trud_ppu_service import TrudPpuResult, TrudPpuService

log = get_logger(__name__)

#: Below this much extractable text a PDF is treated as a scan and photographed.
_TEXT_FLOOR = 150

_CONTRACT_PROMPT = """Ты читаешь ТРУДОВОЙ ДОГОВОР, заключённый российской \
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
 "passport": "<серия и номер паспорта работника, например FA7822242>"
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
        return {
            "uved_number": _digits(answer.get("number", "")),
            "uved_fio": " ".join(p for p in parts if p),
        }

    def read_patent(self, front: bytes, back: bytes | None = None) -> dict[str, str]:
        """The patent's series, number and issue date, off the patent itself."""
        patent = self._ocr.read_patent(front, back)
        # the expiry is NOT taken from the patent: the office writes exactly one
        # year on from the issue date, and the screen derives it from there. The
        # operator can still overtype it for a patent that says otherwise.
        return {
            "patent_series": (patent.series or "").strip(),
            "patent_number": "".join((patent.number or "").split()),
            "patent_issue": _dmy(patent.issue_date or patent.valid_from),
            "surname": (patent.holder_surname or "").strip(),
            "name": (patent.holder_name or "").strip(),
            "patronymic": (patent.holder_patronymic or "").strip(),
            "citizenship": (patent.holder_citizenship or "").strip(),
        }

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
