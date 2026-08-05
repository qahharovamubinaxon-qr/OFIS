"""ЧЕК (премия чеки) controller — patent photo + operator inputs → receipt PDF.

Deliberately self-contained: it reads the patent with its OWN prompt (the shared
Patent model carries no ИНН, and this section must not touch shared code) and
renders through src/pdf/chek_renderer. Templates live in templates/chek/*.pdf;
the operator can add more (same layout, different background) — the 12 field
positions are identical across them by design.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from src.ai.russian import RUSSIAN_SHORT
from src.common.logging import get_logger
from src.domain.enums import DocType
from src.ocr.preprocess import prepare_image
from src.ocr.service import OcrService
from src.pdf.chek_renderer import ChekData, render_chek

log = get_logger(__name__)

TEMPLATES_DIR = Path("templates") / "chek"

#: The office's own company id, recorded once. It used to be generated at
#: random on every receipt, which made the printed id belong to nobody.
KEY_COMPANY_ID = "chek.company_id"

#: The blank the office actually prints on, remembered from the desktop.
#:
#: The phone has no template picker — and it must not need one: the office
#: prints ЧЕК on one blank, arranges its values once, and expects that
#: everywhere. Without this the bot passed no template at all, so no arranged
#: layout was ever found and the receipt came back in the untouched positions.
KEY_TEMPLATE = "chek.template"

_CHEK_PROMPT = RUSSIAN_SHORT + (
    "You are an OCR extraction engine for Russian migration documents. "
    "Read the image and return ONLY a JSON object, no explanation, no markdown. "
    "Use empty string for anything you cannot read. "
    "Output names in RUSSIAN CYRILLIC, uppercased; transliterate Latin if needed. "
    "This is a Russian work PATENT card. The worker's ИНН is a 12-digit number "
    "printed on the card (label ИНН). "
    'Keys: {"surname":"","name":"","patronymic":"","inn":""}'
)


class ChekController:
    def __init__(self, ocr: OcrService, settings=None) -> None:
        self._ocr = ocr
        self._settings = settings

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ── the office's own company id ──────────────────────────────────
    def company_id(self) -> str:
        if self._settings is None:
            return ""
        return str(self._settings.get(KEY_COMPANY_ID, "") or "").strip()

    def set_company_id(self, value: str) -> None:
        if self._settings is not None:
            self._settings.set(KEY_COMPANY_ID, (value or "").strip())

    # ── patent → editable fields ─────────────────────────────────────
    def read_patent_fields(self, image: bytes) -> dict[str, str]:
        answer = self._ocr.ai.extract(
            prepare_image(image), DocType.PATENT, _CHEK_PROMPT)
        f = answer.fields
        inn = "".join(ch for ch in f.get("inn", "") if ch.isdigit())
        return {
            "fam": (f.get("surname") or "").strip().upper(),
            "ism": (f.get("name") or "").strip().upper(),
            "otch": (f.get("patronymic") or "").strip().upper(),
            "inn": inn,
        }

    # ── templates ────────────────────────────────────────────────────
    def templates(self) -> list[Path]:
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(TEMPLATES_DIR.glob("*.pdf"))

    def default_template(self) -> Path | None:
        """The blank to print on when the caller does not name one.

        The one last used on the desktop, while it is still there; otherwise
        the first blank the office has. ``None`` only when there are none, and
        then the renderer falls back to the built-in background.
        """
        if self._settings is not None:
            remembered = str(self._settings.get(KEY_TEMPLATE, "") or "").strip()
            if remembered and Path(remembered).exists():
                return Path(remembered)
        found = self.templates()
        return found[0] if found else None

    def set_default_template(self, template: Path | None) -> None:
        """Remember what the desktop just printed on, for the phone to follow."""
        if self._settings is not None:
            self._settings.set(KEY_TEMPLATE, str(template) if template else "")

    def add_template(self, source: Path) -> Path:
        """Copy an operator-supplied blank into templates/chek/ (never move)."""
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        dest = TEMPLATES_DIR / source.name
        n = 1
        while dest.exists():
            dest = TEMPLATES_DIR / f"{source.stem}-{n}{source.suffix}"
            n += 1
        shutil.copy2(source, dest)
        log.info("chek template added: %s", dest)
        return dest

    # ── generation ───────────────────────────────────────────────────
    @staticmethod
    def parse_amount(text: str) -> tuple[int, int]:
        """"15 000,50" / "15000.50" / "15000" → (15000, 50). Raises ValueError."""
        s = text.strip().replace(" ", "").replace(" ", "")
        s = s.replace(",", ".")
        if not s:
            raise ValueError("summa kiritilmadi")
        if s.count(".") > 1:
            raise ValueError("summa formati noto'g'ri")
        rub_s, _, kop_s = s.partition(".")
        if not rub_s.isdigit() or (kop_s and not kop_s.isdigit()):
            raise ValueError("summa faqat raqamlardan iborat bo'lsin")
        kop = int((kop_s + "00")[:2]) if kop_s else 0
        return int(rub_s), kop

    # ── where this blank wants its values ────────────────────────────
    SECTION = "chek"

    def layout(self, template: Path | None) -> dict:
        from src.services import blank_layout

        return blank_layout.load(self.SECTION, template)

    def save_layout(self, template: Path, layout: dict):
        from src.services import blank_layout

        return blank_layout.save(self.SECTION, template, layout)

    def reset_layout(self, template: Path) -> None:
        from src.services import blank_layout

        blank_layout.reset(self.SECTION, template)

    def generate(self, *, fam: str, ism: str, otch: str, inn: str,
                 card4: str, when: datetime, rub: int, kop: int,
                 avtoriz: str, template: Path | None = None) -> tuple[bytes, str]:
        """``avtoriz`` is the bank's own authorisation code, typed in by the
        operator; the company id comes from Sozlamalar. The renderer refuses
        to print without either — neither is ever generated."""
        data = ChekData(fam=fam, ism=ism, otch=otch, inn=inn,
                        card4=card4, when=when, rub=rub, kop=kop,
                        avtoriz=avtoriz, idci=self.company_id())
        # a caller that names no blank gets the office's own, layout and all —
        # never the untouched default while the desktop prints something else
        if template is None:
            template = self.default_template()
        return render_chek(data, str(template) if template else None,
                           layout=self.layout(template))

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
