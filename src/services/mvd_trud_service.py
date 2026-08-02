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

#: Where each region keeps its blanks. Moscow stays at the root the section
#: has always used, so nothing the office already uploaded moves.
REGION_DIRS = {"moscow": "", "oblast": "oblast"}


def region_of(template) -> str:
    """Which packet a stored blank belongs to — told by where it lives."""
    return "oblast" if Path(template).parent.name == "oblast" else "moscow"


#: The blank is a scanned packet — it arrives as a PDF.
BLANK_SUFFIXES = {".pdf"}


@dataclass(frozen=True)
class MvdTrudResult:
    pdf: bytes
    saved: Path
    surname: str


def templates_dir(region: str = "moscow") -> Path:
    folder = paths.user_templates_dir() / "mvd_trud"
    sub = REGION_DIRS.get(region, "")
    if sub:
        folder = folder / sub
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


#: The область form asks the place of work; it is the firm's own and
#: constant, so it is typed once and offered back every next run.
KEY_WORK_ADDRESS = "mvdtrud.work_address"


class MvdTrudService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ------------------------------------------------------- work address
    def work_address(self) -> str:
        if self._settings is None:
            return ""
        return str(self._settings.get(KEY_WORK_ADDRESS, "") or "").strip()

    def remember_work_address(self, value: str) -> None:
        value = " ".join((value or "").split())
        if self._settings is not None and value:
            self._settings.set(KEY_WORK_ADDRESS, value)

    # ---------------------------------------------------------- templates
    def templates(self, region: str = "moscow") -> list[Path]:
        return sorted(p for p in templates_dir(region).iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path,
                     region: str = "moscow") -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка кўп саҳифали PDF бўлиши керак",
                                  context={"path": str(source)})
        dest = templates_dir(region) / f"{_safe(name)}.pdf"
        shutil.copyfile(source, dest)
        log.info("МВД ТРУДАВОЙ (%s) бланкаси қўшилди: %s", region, dest.name)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        blank_layout.reset(self._section(template), template)

    # ------------------------------------------------------------ layout
    @staticmethod
    def _section(template: Path | str) -> str:
        """Each region keeps its own layouts — the same blank name in the
        other region must never inherit this one's dragging."""
        return (SECTION if region_of(template) == "moscow"
                else f"{SECTION}_oblast")

    def layout(self, template: Path | None) -> dict:
        if not template:
            return {}
        return blank_layout.load(self._section(template), template)

    def save_layout(self, template: Path, layout: dict) -> Path:
        return blank_layout.save(self._section(template), template, layout)

    def reset_layout(self, template: Path) -> None:
        blank_layout.reset(self._section(template), template)

    # ---------------------------------------------------------- printing
    def generate(self, data: MvdTrudData, template: Path | None) -> MvdTrudResult:
        if template is None:
            raise ValidationError(
                "МВД ТРУДАВОЙ бланкаси юкланмаган — «➕ Бланка» орқали "
                "фирманинг 10 саҳифали тўпламини юкланг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — паспортни ўқитинг")

        region = region_of(template)
        data.layout = self.layout(Path(template))
        pdf = render(data, Path(template), region)

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
