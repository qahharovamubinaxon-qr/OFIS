"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the office's own blanks and its own field maps.

Nothing ships with the program any more: the office uploads an empty ТД
and УВ per firm, then places every text and says what it means. The map
lives beside the blank as ``td.fields.json`` / ``uv.fields.json``, so a
firm can be adjusted for ever without touching the program.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.trud8_fields import CATALOGUE, Field
from src.pdf.trud8_renderer import Trud8Data, output_stem, render

log = get_logger(__name__)

KINDS = ("td", "uv")
KIND_TITLES = {"td": "ТД", "uv": "УВ"}

#: The firms that used to ship with the program printed wrong, so the office
#: throws them away and uploads its own empty PDFs. These are the files only
#: that old way ever wrote — a folder holding one of them is a leftover.
LEGACY_FILES = ("td.docx", "uv.docx", "td.values.json", "uv.values.json",
                "td.json", "uv.json")
#: Written once the leftovers are gone, so a firm rebuilt under its old name
#: is never mistaken for one.
LEGACY_MARK = ".pdf-only"


def firms_dir() -> Path:
    folder = paths.user_templates_dir() / "trud8"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def drop_legacy_firms() -> list[str]:
    """Clear away the old bundled firms — once, and never again."""
    root = firms_dir()
    mark = root / LEGACY_MARK
    if mark.exists():
        return []
    dropped = []
    for firm in root.iterdir():
        if firm.is_dir() and any((firm / n).exists() for n in LEGACY_FILES):
            shutil.rmtree(firm, ignore_errors=True)
            dropped.append(firm.name)
    mark.write_text("Эски фирмалар ўчирилди — энди ўз PDF бланкангиз.\n",
                    encoding="utf-8")
    if dropped:
        log.info("ТРУД: эски фирмалар ўчирилди — %s", ", ".join(dropped))
    return dropped


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
        drop_legacy_firms()
        return sorted(p for p in firms_dir().iterdir() if p.is_dir())

    def add_firm(self, name: str, td_pdf: Path | None = None,
                 uv_pdf: Path | None = None) -> Path:
        drop_legacy_firms()
        folder = firms_dir() / _safe(name)
        folder.mkdir(parents=True, exist_ok=True)
        if td_pdf is not None:
            self.set_blank(folder, "td", td_pdf)
        if uv_pdf is not None:
            self.set_blank(folder, "uv", uv_pdf)
        log.info("ТРУД фирмаси қўшилди: %s", folder.name)
        return folder

    def remove_firm(self, firm: Path) -> None:
        shutil.rmtree(Path(firm), ignore_errors=True)

    # ------------------------------------------------------------- blanks
    def blank(self, firm: Path, kind: str) -> Path | None:
        found = Path(firm) / f"{kind}.pdf"
        return found if found.exists() else None

    def set_blank(self, firm: Path, kind: str, source: Path) -> Path:
        if kind not in KINDS:
            raise ValidationError("Бланка тури нотўғри")
        source = Path(source)
        if source.suffix.lower() != ".pdf" or not source.exists():
            raise ValidationError("Бланка PDF бўлиши керак")
        dest = Path(firm) / f"{kind}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        log.info("ТРУД бланкаси юкланди: %s / %s", Path(firm).name, kind)
        return dest

    def pages(self, firm: Path, kind: str) -> int:
        blank = self.blank(firm, kind)
        if blank is None:
            return 0
        import fitz

        with fitz.open(str(blank)) as doc:
            return doc.page_count

    # ------------------------------------------------------------- fields
    def _fields_path(self, firm: Path, kind: str) -> Path:
        return Path(firm) / f"{kind}.fields.json"

    def fields(self, firm: Path, kind: str) -> list[Field]:
        path = self._fields_path(firm, kind)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Field.from_dict(item) for item in (raw.get("fields") or [])]

    def save_fields(self, firm: Path, kind: str,
                    fields: list[Field]) -> Path:
        path = self._fields_path(firm, kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"fields": [f.as_dict() for f in fields]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def add_field(self, firm: Path, kind: str, key: str,
                  page: int = 1) -> Field:
        if key not in CATALOGUE:
            raise ValidationError("Бундай маълумот рўйхатда йўқ")
        made = Field(key=key, page=max(1, page))
        kept = self.fields(firm, kind)
        kept.append(made)
        self.save_fields(firm, kind, kept)
        return made

    def remove_field(self, firm: Path, kind: str, index: int) -> None:
        kept = self.fields(firm, kind)
        if 0 <= index < len(kept):
            kept.pop(index)
            self.save_fields(firm, kind, kept)

    def restyle_field(self, firm: Path, kind: str, index: int, *,
                      colour: tuple[float, float, float] | None = None,
                      bold: bool | None = None,
                      serif: bool | None = None) -> None:
        kept = self.fields(firm, kind)
        if not (0 <= index < len(kept)):
            return
        old = kept[index]
        kept[index] = Field(
            key=old.key, page=old.page, x=old.x, baseline=old.baseline,
            size=old.size,
            bold=old.bold if bold is None else bold,
            serif=old.serif if serif is None else serif,
            colour=old.colour if colour is None else colour)
        self.save_fields(firm, kind, kept)

    def move_fields(self, firm: Path, kind: str, moved: dict) -> None:
        """What the drag editor handed back: «key#index» → x, baseline, size."""
        kept = self.fields(firm, kind)
        for tag, place in (moved or {}).items():
            if len(place) != 3 or "#" not in tag:
                continue
            index = int(tag.rsplit("#", 1)[1])
            if not (0 <= index < len(kept)):
                continue
            old = kept[index]
            x, baseline, size = (float(v) for v in place)
            kept[index] = Field(key=old.key, page=old.page, x=x,
                                baseline=baseline, size=size, bold=old.bold,
                                serif=old.serif, colour=old.colour)
        self.save_fields(firm, kind, kept)

    # ----------------------------------------------------------- printing
    def generate(self, data: Trud8Data, firm: Path | None,
                 want_pdf: bool = True) -> Trud8Result:
        if firm is None:
            raise ValidationError("Фирмани танланг.")
        firm = Path(firm)
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")
        out_dir = paths.output_dir() / "trud"
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for kind in KINDS:
            blank = self.blank(firm, kind)
            if blank is None:
                continue
            fields = self.fields(firm, kind)
            pdf = render(data, blank, fields)
            tag = KIND_TITLES[kind]
            target = out_dir / f"{output_stem(data)}_{tag}.pdf"
            counter = 2
            while target.exists():
                target = out_dir / f"{output_stem(data)}_{tag} ({counter}).pdf"
                counter += 1
            target.write_bytes(pdf)
            saved.append(target)
        if not saved:
            raise ValidationError(
                f"«{firm.name}» да бланка йўқ — ТД/УВ PDF ларини юкланг.")
        log.info("ТРУД: %s — %s (%s)", data.fio(), firm.name,
                 ", ".join(p.name for p in saved))
        return Trud8Result(saved=saved, surname=(data.surname or "").strip())
