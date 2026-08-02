"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the eight firms, their maps, and the printing.

The firms ship with the program (templates/trud8/<ФИРМА>/td.pdf + td.json,
uv.pdf + uv.json) and are seeded into the user's own store on first use, so
new firms can be added and every text dragged per page without rebuilding.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.trud8_renderer import Trud8Data, output_stem, render
from src.services import blank_layout

log = get_logger(__name__)

SECTIONS = {"td": "trud8_td", "uv": "trud8_uv"}


def bundled_dir() -> Path:
    return paths.templates_dir() / "trud8"


def firms_dir() -> Path:
    folder = paths.user_templates_dir() / "trud8"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Фирма номи керак")
    return cleaned


@dataclass(frozen=True)
class Trud8Result:
    saved: list[Path]
    surname: str


class Trud8Service:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # -------------------------------------------------------------- firms
    def firms(self) -> list[Path]:
        self.seed()
        return sorted(p for p in firms_dir().iterdir() if p.is_dir())

    def seed(self) -> None:
        """The bundled eight, copied once — never overwriting the office's."""
        bundled = bundled_dir()
        if not bundled.exists():
            return
        for firm in bundled.iterdir():
            dest = firms_dir() / firm.name
            if firm.is_dir() and not dest.exists():
                shutil.copytree(firm, dest)

    def add_firm(self, name: str, td_pdf: Path,
                 uv_pdf: Path | None = None) -> Path:
        td_pdf = Path(td_pdf)
        if td_pdf.suffix.lower() != ".pdf" or not td_pdf.exists():
            raise ValidationError("ТД бланкаси PDF бўлиши керак")
        folder = firms_dir() / _safe(name)
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(td_pdf, folder / "td.pdf")
        # a fresh firm starts from МОНОТЕК's map — the closest style — and
        # the office drags from there
        for kind, _source in (("td", td_pdf), ("uv", uv_pdf)):
            if kind == "uv":
                if uv_pdf is None:
                    continue
                shutil.copyfile(Path(uv_pdf), folder / "uv.pdf")
            donor = bundled_dir() / "МОНОТЕК СТРОЙ" / f"{kind}.json"
            if donor.exists() and not (folder / f"{kind}.json").exists():
                shutil.copyfile(donor, folder / f"{kind}.json")
        log.info("ТРУД фирмаси қўшилди: %s", folder.name)
        return folder

    def set_uv(self, firm: Path, uv_pdf: Path) -> None:
        uv_pdf = Path(uv_pdf)
        if uv_pdf.suffix.lower() != ".pdf" or not uv_pdf.exists():
            raise ValidationError("УВ бланкаси PDF бўлиши керак")
        shutil.copyfile(uv_pdf, Path(firm) / "uv.pdf")
        donor = bundled_dir() / "МОНОТЕК СТРОЙ" / "uv.json"
        if donor.exists() and not (Path(firm) / "uv.json").exists():
            shutil.copyfile(donor, Path(firm) / "uv.json")

    def remove_firm(self, firm: Path) -> None:
        firm = Path(firm)
        for kind in ("td", "uv"):
            blank_layout.reset(SECTIONS[kind], firm / f"{kind}.pdf")
        shutil.rmtree(firm, ignore_errors=True)

    # ------------------------------------------------------------ layouts
    def slots(self, firm: Path, kind: str) -> list[dict]:
        path = Path(firm) / f"{kind}.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("slots") or []

    def layout(self, firm: Path, kind: str) -> dict:
        return blank_layout.load(SECTIONS[kind], Path(firm) / f"{kind}.pdf")

    def save_layout(self, firm: Path, kind: str, layout: dict):
        return blank_layout.save(SECTIONS[kind], Path(firm) / f"{kind}.pdf",
                                 layout)

    # ----------------------------------------------------------- printing
    def generate(self, data: Trud8Data, firm: Path | None) -> Trud8Result:
        if firm is None:
            raise ValidationError("Фирмани танланг.")
        firm = Path(firm)
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")
        out_dir = paths.output_dir() / "trud"
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for kind, tag in (("td", "ТД"), ("uv", "УВ")):
            template = firm / f"{kind}.pdf"
            if not template.exists():
                continue
            pdf = render(data, template, self.slots(firm, kind),
                         self.layout(firm, kind))
            target = out_dir / f"{output_stem(data)}_{tag}.pdf"
            counter = 2
            while target.exists():
                target = out_dir / (f"{output_stem(data)}_{tag} "
                                    f"({counter}).pdf")
                counter += 1
            target.write_bytes(pdf)
            saved.append(target)
        if not saved:
            raise ValidationError(
                f"«{firm.name}» да бланка йўқ — ТД/УВ PDF ларини юкланг.")
        log.info("ТРУД: %s — %s (%s)", data.fio(), firm.name,
                 ", ".join(p.name for p in saved))
        return Trud8Result(saved=saved, surname=(data.surname or "").strip())
