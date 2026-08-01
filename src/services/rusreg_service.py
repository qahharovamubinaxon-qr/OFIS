"""РУС РЕГ — registration sheets for the office's Russian-citizen workers.

They are registered at a flat the firm provides, on the firm's own blank
(«ИШЧИНИ РЕГИСТРАЦИЯСИ»), against a Russian internal passport — or, for a
worker's child, a birth certificate. This service owns everything around the
rendering: the uploaded blanks, the dragged layouts, and the values the office
types once and expects to find still there tomorrow — the address, the firm,
the running registration number, and every address ever used (the same flat
houses many workers, so yesterday's address is next week's too).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.rusreg_renderer import RusRegData, output_name, render
from src.services import blank_layout

log = get_logger(__name__)

#: A blank arrives as whichever the office happens to have.
BLANK_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}

SECTION = "rusreg"

#: Values the office types once and expects to keep. The address is a LIST —
#: the firm's flats — with the latest first.
KEY_ADDRESSES = "rusreg.addresses"
KEY_FIRM = "rusreg.firm"
KEY_REG_NUMBER = "rusreg.reg_number"
KEY_SIGNER = "rusreg.signer"

#: How many old addresses the list keeps. Enough for every flat the firm has;
#: a hundred-line dropdown helps nobody.
MAX_ADDRESSES = 30


@dataclass(frozen=True)
class RusRegResult:
    pdf: bytes
    saved: Path
    surname: str


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "rusreg"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


class RusRegService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        return sorted(p for p in templates_dir().iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка PDF ёки расм бўлиши керак",
                                  context={"path": str(source)})
        dest = templates_dir() / f"{_safe(name)}{source.suffix.lower()}"
        shutil.copyfile(source, dest)
        log.info("РУС РЕГ бланкаси қўшилди: %s", dest.name)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        blank_layout.reset(SECTION, template)

    # ------------------------------------------------------------ layout
    def layout(self, template: Path | None) -> dict:
        return blank_layout.load(SECTION, template) if template else {}

    def save_layout(self, template: Path, layout: dict) -> Path:
        return blank_layout.save(SECTION, template, layout)

    def reset_layout(self, template: Path) -> None:
        blank_layout.reset(SECTION, template)

    # ---------------------------------------- what the office typed once
    def _get(self, key: str) -> str:
        if self._settings is None:
            return ""
        return str(self._settings.get(key, "") or "").strip()

    def _set(self, key: str, value: str) -> None:
        if self._settings is not None:
            self._settings.set(key, (value or "").strip())

    def firm(self) -> str:
        return self._get(KEY_FIRM)

    def reg_number(self) -> str:
        return self._get(KEY_REG_NUMBER)

    def signer(self) -> str:
        return self._get(KEY_SIGNER)

    def addresses(self) -> list[str]:
        """Every address the office has registered at, the latest first."""
        if self._settings is None:
            return []
        raw = str(self._settings.get(KEY_ADDRESSES, "") or "")
        try:
            data = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
        return [str(a) for a in data if str(a).strip()] if isinstance(data, list) else []

    def address(self) -> str:
        """The one to offer first: the last one used."""
        known = self.addresses()
        return known[0] if known else ""

    def remember(self, *, address: str = "", firm: str = "",
                 reg_number: str = "", signer: str = "") -> None:
        """Keep what was just used, so tomorrow starts where today left off.

        The address goes to the FRONT of the list — used-most-recently is the
        order the operator reaches for — and duplicates collapse, so re-using
        an old flat moves it up rather than listing it twice.
        """
        if firm:
            self._set(KEY_FIRM, firm)
        if reg_number:
            self._set(KEY_REG_NUMBER, reg_number)
        if signer:
            self._set(KEY_SIGNER, signer)
        address = " ".join((address or "").split())
        if address and self._settings is not None:
            known = [a for a in self.addresses()
                     if a.strip().upper() != address.upper()]
            known.insert(0, address)
            self._settings.set(
                KEY_ADDRESSES,
                json.dumps(known[:MAX_ADDRESSES], ensure_ascii=False))

    # ---------------------------------------------------------- printing
    def generate(self, data: RusRegData, template: Path | None) -> RusRegResult:
        if template is None:
            raise ValidationError(
                "РУС РЕГ бланкаси юкланмаган — «➕ Бланка» орқали фирманинг "
                "бланкасини юкланг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатни ўқитинг ёки ёзинг")

        data.layout = self.layout(Path(template))
        pdf = render(data, Path(template))

        folder = paths.output_dir() / "rusreg"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / output_name(data)
        counter = 2
        while target.exists():
            target = folder / f"{target.stem.split(' (')[0]} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)

        self.remember(address=data.address, firm=data.firm,
                      reg_number=data.reg_number, signer=data.signer)
        log.info("РУС РЕГ: %s — %s", data.fio(), target.name)
        return RusRegResult(pdf=pdf, saved=target,
                            surname=(data.surname or "").strip())
