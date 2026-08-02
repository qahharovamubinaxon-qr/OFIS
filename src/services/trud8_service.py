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
from src.pdf.trud8_renderer import Trud8Data, output_stem, render, values
from src.services import blank_layout
from src.services.trud8_docx import fill, to_pdf

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
        """The bundled firms, copied once — and folders seeded in the old
        PDF days are UPGRADED file-by-file, so the Word blanks arrive
        without touching anything the office added itself."""
        bundled = bundled_dir()
        if not bundled.exists():
            return
        for firm in bundled.iterdir():
            if not firm.is_dir():
                continue
            dest = firms_dir() / firm.name
            dest.mkdir(parents=True, exist_ok=True)
            for item in firm.iterdir():
                if not (dest / item.name).exists():
                    shutil.copyfile(item, dest / item.name)

    def _install(self, folder: Path, kind: str, source: Path) -> None:
        """One blank into the firm: a Word file is probed for its OLD
        worker so replacement works with no hand-made map."""
        source = Path(source)
        suffix = source.suffix.lower()
        if suffix not in (".docx", ".pdf") or not source.exists():
            raise ValidationError("Бланка Word (.docx) ёки PDF бўлиши керак")
        shutil.copyfile(source, folder / f"{kind}{suffix}")
        if suffix == ".docx":
            from src.services.trud8_probe import doc_texts, td_values, uv_values

            texts = doc_texts(folder / f"{kind}{suffix}")
            found = uv_values(texts) if kind == "uv" else td_values(texts)
            (folder / f"{kind}.values.json").write_text(
                json.dumps(found, ensure_ascii=False, indent=1),
                encoding="utf-8")

    def add_firm(self, name: str, td_file: Path,
                 uv_file: Path | None = None) -> Path:
        folder = firms_dir() / _safe(name)
        folder.mkdir(parents=True, exist_ok=True)
        self._install(folder, "td", td_file)
        if uv_file is not None:
            self._install(folder, "uv", uv_file)
        log.info("ТРУД фирмаси қўшилди: %s", folder.name)
        return folder

    def set_uv(self, firm: Path, uv_file: Path) -> None:
        self._install(Path(firm), "uv", uv_file)

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
    def _replacements(self, firm: Path, kind: str,
                      data: Trud8Data) -> dict[str, str]:
        """old worker's strings (off the firm's own json) → the new ones."""
        stored_path = Path(firm) / f"{kind}.values.json"
        if not stored_path.exists():
            return {}
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
        texts = values(data)
        out: dict[str, str] = {}
        for key, old in stored.items():
            new = (texts.get(key) or "").strip()
            old = (old or "").strip()
            if old and new and old != new:
                out[old] = new
        return out

    def generate(self, data: Trud8Data, firm: Path | None,
                 want_pdf: bool = False) -> Trud8Result:
        """Both papers as the firm's own Word files — PDF for the бот."""
        if firm is None:
            raise ValidationError("Фирмани танланг.")
        firm = Path(firm)
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")
        out_dir = paths.output_dir() / "trud"
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for kind, tag in (("td", "ТД"), ("uv", "УВ")):
            template = firm / f"{kind}.docx"
            if template.exists():
                target = out_dir / f"{output_stem(data)}_{tag}.docx"
                counter = 2
                while target.exists():
                    target = out_dir / (f"{output_stem(data)}_{tag} "
                                        f"({counter}).docx")
                    counter += 1
                fill(template, self._replacements(firm, kind, data), target)
                if want_pdf:
                    pdf = to_pdf(target)
                    saved.append(pdf if pdf is not None else target)
                else:
                    saved.append(target)
                continue
            # a firm the office added with a PDF blank keeps the old path
            template = firm / f"{kind}.pdf"
            if template.exists():
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
                f"«{firm.name}» да бланка йўқ — ТД/УВ файлларини юкланг.")
        log.info("ТРУД: %s — %s (%s)", data.fio(), firm.name,
                 ", ".join(p.name for p in saved))
        return Trud8Result(saved=saved, surname=(data.surname or "").strip())
