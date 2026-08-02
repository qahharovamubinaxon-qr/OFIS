"""СТРАХОВКА МАШИНАГА — PDF blanks, layouts, and the printing.

Each insurer's blank is uploaded once as a PDF and picks its starting map —
Ингосстрах or РЕСО style, both measured 1:1 off the owner's samples. Every
text can then be dragged and resized against that very blank. The choice of
who the policy covers follows the uploads: no licences → «неограниченного
количества лиц» with its tick; one to four licences → the named list and the
other tick, exactly the way the samples print them.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.osago_renderer import OsagoData, output_name, render
from src.services import blank_layout

log = get_logger(__name__)

SECTION = "osago"
BLANK_SUFFIXES = {".pdf"}


def cover_until(start: date) -> date:
    """A year of cover ends the day before the anniversary."""
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:                        # cover taken out on 29 February
        anniversary = date(start.year + 1, 3, 1)
    return anniversary - timedelta(days=1)


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "osago"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


@dataclass(frozen=True)
class OsagoResult:
    pdf: bytes
    saved: Path
    plate: str
    drivers: int


class OsagoService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        return sorted(p for p in templates_dir().iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path,
                     base: str = "ingosstrah") -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка PDF бўлиши керак")
        dest = templates_dir() / f"{_safe(name)}.pdf"
        shutil.copyfile(source, dest)
        # the insurer style rides inside the blank's own layout file
        kept = blank_layout.load(SECTION, dest)
        kept["base"] = base
        blank_layout.save(SECTION, dest, kept)
        log.info("СТРАХОВКА бланкаси қўшилди: %s (%s)", dest.name, base)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        blank_layout.reset(SECTION, template)

    # ------------------------------------------------------------ layout
    def layout(self, template: Path | None) -> dict:
        return blank_layout.load(SECTION, template) if template else {}

    def save_layout(self, template: Path, layout: dict) -> Path:
        kept = self.layout(template)
        return blank_layout.save(SECTION, template,
                                 {**kept, **layout})

    def base_of(self, template: Path | None) -> str:
        base = str(self.layout(template).get("base") or "")
        return base if base in ("ingosstrah", "reso") else "ingosstrah"

    # ---------------------------------------------------------- printing
    def generate(self, data: OsagoData,
                 template: Path | None) -> OsagoResult:
        if template is None:
            raise ValidationError(
                "СТРАХОВКА бланкаси юкланмаган — «➕ Бланка» орқали "
                "суғурта компаниясининг PDF бланкасини юкланг.")
        if not (data.sts.plate or data.sts.vin or "").strip():
            raise ValidationError(
                "СТС ўқилмади — олд томонининг аниқ расмини ташланг.")

        data.layout = self.layout(Path(template))
        pdf = render(data, Path(template), self.base_of(Path(template)))

        folder = paths.output_dir() / "osago"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / output_name(data)
        counter = 2
        while target.exists():
            target = folder / f"{target.stem.split(' (')[0]} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)
        named = [d for d in data.drivers if not d.is_empty()]
        log.info("СТРАХОВКА: %s — %s (%s)", data.sts.plate, target.name,
                 "чексиз" if data.unlimited else f"{len(named)} ҳайдовчи")
        return OsagoResult(pdf=pdf, saved=target,
                           plate=(data.sts.plate or "").strip(),
                           drivers=len(named))
