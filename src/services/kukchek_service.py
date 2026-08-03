"""КУК ЧЕК — blanks, the печать, and the printing."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.kukchek_renderer import KukChekData, output_name, render
from src.services import blank_layout
from src.services.alpinist_service import ink_only

log = get_logger(__name__)

SECTION = "kukchek"
BLANK_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
STAMP_SUFFIXES = {".png", ".jpg", ".jpeg"}


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "kukchek"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


@dataclass(frozen=True)
class KukChekResult:
    pdf: bytes
    saved: Path
    surname: str


class KukChekService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        return sorted(p for p in templates_dir().iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка PDF ёки расм бўлиши керак")
        dest = templates_dir() / f"{_safe(name)}{source.suffix.lower()}"
        shutil.copyfile(source, dest)
        log.info("КУК ЧЕК бланкаси қўшилди: %s", dest.name)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        blank_layout.reset(SECTION, template)

    # ------------------------------------------------------------ печать
    def stamp(self) -> Path | None:
        found = sorted((templates_dir() / "stamp").glob("stamp.png"))
        return found[0] if found else None

    def set_stamp(self, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in STAMP_SUFFIXES or not source.exists():
            raise ValidationError("Печать PNG ёки JPG расм бўлиши керак")
        folder = templates_dir() / "stamp"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "stamp.png"
        dest.write_bytes(ink_only(source.read_bytes()))
        log.info("КУК ЧЕК печати янгиланди")
        return dest

    def remove_stamp(self) -> None:
        found = self.stamp()
        if found:
            found.unlink(missing_ok=True)

    # ------------------------------------------------------------ layout
    def layout(self, template: Path | None) -> dict:
        return blank_layout.load(SECTION, template) if template else {}

    def save_layout(self, template: Path, layout: dict):
        return blank_layout.save(SECTION, template, layout)

    # ---------------------------------------------------------- printing
    def generate(self, data: KukChekData,
                 template: Path | None) -> KukChekResult:
        if template is None:
            raise ValidationError(
                "КУК ЧЕК бланкаси юкланмаган — «➕ Бланка» орқали юкланг.")
        if not (data.fam or "").strip():
            raise ValidationError("Фамилия керак — патентни ўқитинг")
        stamp = self.stamp()
        if stamp is not None and data.stamp_png is None:
            data.stamp_png = stamp.read_bytes()
        data.layout = self.layout(Path(template))
        pdf = render(data, Path(template))
        folder = paths.output_dir() / "kukchek"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / output_name(data)
        counter = 2
        while target.exists():
            target = folder / f"{target.stem.split(' (')[0]} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)
        log.info("КУК ЧЕК: %s %s — %s", data.fam, data.ism, target.name)
        return KukChekResult(pdf=pdf, saved=target,
                             surname=(data.fam or "").strip())
