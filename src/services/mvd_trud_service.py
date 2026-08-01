"""МВД ТРУДАВОЙ — the ten-page packet for the office's long-term workers.

Owns the uploaded blanks (each a full ten-page PDF carrying the firm's own
constants), the per-blank layouts the office dragged, and the printing itself.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.mvd_trud_renderer import MvdTrudData, output_name, render
from src.services import blank_layout

log = get_logger(__name__)

SECTION = "mvd_trud"

#: The blank is a scanned packet — it arrives as a PDF.
BLANK_SUFFIXES = {".pdf"}


@dataclass(frozen=True)
class MvdTrudResult:
    pdf: bytes
    saved: Path
    surname: str


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "mvd_trud"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


class MvdTrudService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        return sorted(p for p in templates_dir().iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка 10 саҳифали PDF бўлиши керак",
                                  context={"path": str(source)})
        dest = templates_dir() / f"{_safe(name)}.pdf"
        shutil.copyfile(source, dest)
        log.info("МВД ТРУДАВОЙ бланкаси қўшилди: %s", dest.name)
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

    # ---------------------------------------------------------- printing
    def generate(self, data: MvdTrudData, template: Path | None) -> MvdTrudResult:
        if template is None:
            raise ValidationError(
                "МВД ТРУДАВОЙ бланкаси юкланмаган — «➕ Бланка» орқали "
                "фирманинг 10 саҳифали тўпламини юкланг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — паспортни ўқитинг")

        data.layout = self.layout(Path(template))
        pdf = render(data, Path(template))

        folder = paths.output_dir() / "mvd_trud"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / output_name(data)
        counter = 2
        while target.exists():
            target = folder / f"{target.stem.split(' (')[0]} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)
        log.info("МВД ТРУДАВОЙ: %s — %s", data.fio(), target.name)
        return MvdTrudResult(pdf=pdf, saved=target,
                             surname=(data.surname or "").strip())
