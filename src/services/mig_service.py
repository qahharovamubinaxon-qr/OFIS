"""МИГ — the «ИШЧИ КАРТАСИ» the office prints for each firm it works for.

The office works for three or four firms and each has its own blank and its own
stamp, so both are kept as NAMED lists rather than one of each: upload once,
pick from the list every time after.

A stamp remembers where it was put and how big it was made. The operator drags
it onto the card once, with the mouse, against that firm's own blank — and every
card for that firm afterwards has it in the same place. That is the whole point
of keeping it: nobody wants to line a stamp up twice.

Everything lives in AppData, never in the program folder, so rebuilding the EXE
never throws a firm's blank or stamp away.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.mig_renderer import MigData, as_png, render
from src.pdf.mig_spec import DEFAULT_STAMP

log = get_logger(__name__)

#: What a firm may hand over as a blank or a stamp.
BLANK_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
STAMP_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

_PLACEMENT = "placement.json"


@dataclass(frozen=True)
class Stamp:
    """One firm's stamp, and where on the card it goes."""

    name: str
    path: Path
    #: (left, top, right, bottom) shares of the page
    box: tuple[float, float, float, float] = DEFAULT_STAMP


@dataclass(frozen=True)
class MigResult:
    pdf: bytes
    png: bytes
    saved: Path
    surname: str


def _root() -> Path:
    return paths.user_templates_dir() / "mig"


def templates_dir() -> Path:
    folder = _root() / "blanks"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stamps_dir() -> Path:
    folder = _root() / "stamps"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


def _file_stem(surname: str) -> str:
    stem = "".join(c for c in (surname or "").strip()
                   if c.isalnum() or c in " _-").strip()
    return stem or "ИШЧИ КАРТАСИ"


class MigService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        """The firms' blanks, newest name order. Empty until one is uploaded."""
        folder = templates_dir()
        return sorted(p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES
                      and not p.name.endswith(".layout.json"))

    def add_template(self, name: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка PDF ёки расм бўлиши керак",
                                  context={"path": str(source)})
        dest = templates_dir() / f"{_safe(name)}{source.suffix.lower()}"
        shutil.copyfile(source, dest)
        log.info("МИГ бланкаси қўшилди: %s", dest.name)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        self._layout_file(template).unlink(missing_ok=True)

    # ------------------------------------------------------------ layout
    @staticmethod
    def _layout_file(template: Path) -> Path:
        return Path(template).with_suffix(".layout.json")

    def layout(self, template: Path | None) -> dict:
        """Where this firm's blank wants its values, if it has been arranged.

        Empty when it has not: the renderer then uses the measured defaults in
        :mod:`src.pdf.mig_spec`. Kept beside the blank rather than in the
        program, so arranging one firm's card never moves another's — and so a
        move needs no new EXE.
        """
        if template is None:
            return {}
        path = self._layout_file(template)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("МИГ: %s жойлашуви ўқилмади", path.name)
            return {}
        return data if isinstance(data, dict) else {}

    def save_layout(self, template: Path, layout: dict) -> Path:
        path = self._layout_file(template)
        path.write_text(json.dumps(layout, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        log.info("МИГ: %s жойлашуви сақланди", path.name)
        return path

    def reset_layout(self, template: Path) -> None:
        self._layout_file(template).unlink(missing_ok=True)

    # ------------------------------------------------------------- stamps
    def _placements(self) -> dict:
        path = stamps_dir() / _PLACEMENT
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def stamps(self) -> list[Stamp]:
        """Every firm's stamp, each with the place the office put it."""
        placed = self._placements()
        out = []
        for path in sorted(p for p in stamps_dir().iterdir()
                           if p.is_file() and p.suffix.lower() in STAMP_SUFFIXES):
            box = placed.get(path.name)
            out.append(Stamp(
                name=path.stem, path=path,
                box=tuple(box) if isinstance(box, list) and len(box) == 4
                else DEFAULT_STAMP))
        return out

    def add_stamp(self, name: str, source: Path) -> Stamp:
        source = Path(source)
        if source.suffix.lower() not in STAMP_SUFFIXES or not source.exists():
            raise ValidationError("Печат расм бўлиши керак (png, jpg)",
                                  context={"path": str(source)})
        dest = stamps_dir() / f"{_safe(name)}{source.suffix.lower()}"
        shutil.copyfile(source, dest)
        log.info("МИГ печати қўшилди: %s", dest.name)
        return Stamp(name=dest.stem, path=dest, box=DEFAULT_STAMP)

    def place_stamp(self, stamp: Stamp | Path,
                    box: tuple[float, float, float, float]) -> None:
        """Remember where this stamp goes and how big it is.

        Kept beside the stamps themselves rather than in the settings database,
        so copying the folder to another machine carries the placements with it.
        """
        path = stamp.path if isinstance(stamp, Stamp) else Path(stamp)
        left, top, right, bottom = (float(v) for v in box)
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            raise ValidationError("Печат жойи варақдан ташқарида")
        placed = self._placements()
        placed[path.name] = [left, top, right, bottom]
        (stamps_dir() / _PLACEMENT).write_text(
            json.dumps(placed, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("МИГ: %s печатининг жойи сақланди", path.name)

    def remove_stamp(self, stamp: Stamp | Path) -> None:
        path = stamp.path if isinstance(stamp, Stamp) else Path(stamp)
        path.unlink(missing_ok=True)
        placed = self._placements()
        if placed.pop(path.name, None) is not None:
            (stamps_dir() / _PLACEMENT).write_text(
                json.dumps(placed, ensure_ascii=False, indent=1), encoding="utf-8")

    # ----------------------------------------------------------- printing
    def generate(
        self,
        *,
        template: Path | None,
        series: str = "",
        number: str = "",
        visa: str = "",
        jobs: tuple[str, ...] = (),
        valid_from: date | None = None,
        valid_to: date | None = None,
        issued: str = "",
        surname: str = "",
        surname_latin: str = "",
        name: str = "",
        patronymic: str = "",
        birth_date: date | None = None,
        citizenship: str = "",
        passport: str = "",
        gender: str = "",
        code: str = "",
        stamp: Stamp | None = None,
    ) -> MigResult:
        if template is None:
            raise ValidationError(
                "МИГ бланкаси юкланмаган — «➕ Бланка» орқали фирманинг бўш "
                "картасини юкланг.")
        if not surname.strip() and not number.strip():
            raise ValidationError("Камида фамилия ёки карта номери керак")

        data = MigData(
            series=series, number=number, visa=visa, jobs=tuple(jobs),
            valid_from=valid_from, valid_to=valid_to, issued=issued,
            surname=surname, surname_latin=surname_latin, name=name,
            patronymic=patronymic, birth_date=birth_date,
            citizenship=citizenship, passport=passport, gender=gender,
            code=code,
            stamp=stamp.path.read_bytes() if stamp is not None else None,
            stamp_box=stamp.box if stamp is not None else DEFAULT_STAMP)
        pdf = render(data, Path(template), self.layout(template))
        png = as_png(pdf)

        folder = paths.output_dir() / "mig"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{_file_stem(surname)}.pdf"
        counter = 2
        while target.exists():
            target = folder / f"{_file_stem(surname)} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)

        log.info("МИГ: %s — %s", surname, target.name)
        return MigResult(pdf=pdf, png=png, saved=target,
                         surname=surname.strip())
