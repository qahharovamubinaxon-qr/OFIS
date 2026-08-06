"""МЕД КНИЖКА — the office's blanks, its arrangement and its numbering.

Three things are kept between runs and nothing else: the scanned blanks the
office uploads for the four pages, whatever it dragged in «📐 Созлаш», and
the booklet number it is up to. The number is the office's own — it reads
it off the booklet in its hand — and the program only offers the next one,
so a package for the next worker starts one along instead of being typed
again.
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
from src.pdf.medkniga_renderer import MedKnigaData, output_stem, render
from src.pdf.medkniga_spec import DEFAULT_KIT, KITS, PAGES

log = get_logger(__name__)

SECTION = "medkniga"
_COUNTER = "number.json"


def folder(kit: str = DEFAULT_KIT) -> Path:
    """One kit's own corner. The blanks differ between Москва and the
    область; nothing else does, so only the blanks live in here."""
    made = paths.user_templates_dir() / SECTION / _kit(kit)
    made.mkdir(parents=True, exist_ok=True)
    return made


def _kit(kit: str | None) -> str:
    """Whatever was passed, as one of the two kits the office keeps."""
    name = (kit or "").strip().lower()
    if name in KITS:
        return name
    for key, label in KITS.items():          # «Московская область» → oblast
        if name and (name in label.lower() or label.lower() in name):
            return key
    return DEFAULT_KIT


# ---------------------------------------------------------------- blanks
def blank_of(page: int, kit: str = DEFAULT_KIT) -> Path | None:
    """The office's own scan for one page of one kit, if it uploaded one."""
    for suffix in (".pdf", ".png", ".jpg", ".jpeg"):
        found = folder(kit) / f"page{page}{suffix}"
        if found.exists():
            return found
    return None


def blanks(kit: str = DEFAULT_KIT) -> dict[int, Path]:
    return {p: found for p in range(1, PAGES + 1)
            if (found := blank_of(p, kit)) is not None}


def set_blank(page: int, source: Path, kit: str = DEFAULT_KIT) -> Path:
    """Upload one page's blank. A page may be replaced at any time."""
    if not 1 <= page <= PAGES:
        raise ValidationError(f"Бет 1 дан {PAGES} гача бўлиши керак")
    source = Path(source)
    if source.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg"):
        raise ValidationError("Бланка PDF ёки расм бўлиши керак")
    if not source.exists():
        raise ValidationError("Бланка файли топилмади")
    clear_blank(page, kit)
    target = folder(kit) / f"page{page}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("МЕДКНИЖКА: «%s» — %d-бет бланкаси юкланди", _kit(kit), page)
    return target


def clear_blank(page: int, kit: str = DEFAULT_KIT) -> None:
    found = blank_of(page, kit)
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------------- the seal
def stamp() -> Path | None:
    """The office's OWN seal, uploaded once and used for every worker.

    Shared by both kits, like the arrangement: it is one firm with one
    seal, whichever booklet its worker is given.
    """
    for suffix in (".png", ".jpg", ".jpeg"):
        found = _root() / f"stamp{suffix}"
        if found.exists():
            return found
    return None


def set_stamp(source: Path) -> Path:
    source = Path(source)
    if source.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValidationError("Печать расм бўлиши керак (PNG яхши)")
    if not source.exists():
        raise ValidationError("Печать файли топилмади")
    clear_stamp()
    target = _root() / f"stamp{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("МЕДКНИЖКА: фирма печати юкланди")
    return target


def clear_stamp() -> None:
    found = stamp()
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------------ the number
def _root() -> Path:
    """What both kits share: the numbering and the arrangement."""
    made = paths.user_templates_dir() / SECTION
    made.mkdir(parents=True, exist_ok=True)
    return made


def next_number() -> str:
    """The booklet number the office is up to — «» until it types one."""
    store = _root() / _COUNTER
    if not store.exists():
        return ""
    try:
        return str(json.loads(store.read_text("utf-8")).get("next", "") or "")
    except (OSError, ValueError):
        return ""


def remember_number(used: str) -> None:
    """One package done — the NEXT booklet is one along.

    Only a plain run of digits is counted on; a number with letters in it
    is remembered as it stands, because the office alone knows how its own
    series runs.
    """
    used = "".join((used or "").split())
    if not used:
        return
    following = str(int(used) + 1).zfill(len(used)) if used.isdigit() else used
    (_root() / _COUNTER).write_text(
        json.dumps({"next": following}, ensure_ascii=False), "utf-8")


# ------------------------------------------------------------ the layout
def load_layout() -> dict:
    """ONE arrangement for both kits: the office said the blanks differ but
    every mark sits in the same place, so it is dragged once."""
    from src.services import blank_layout

    return blank_layout.load(SECTION, SECTION)


def save_layout(layout: dict) -> None:
    from src.services import blank_layout

    blank_layout.save(SECTION, SECTION, layout)


@dataclass(frozen=True)
class MedKnigaResult:
    pdf_path: Path
    surname: str
    number: str
    exam_date: date | None
    expires: date | None


class MedKnigaService:
    def generate(self, data: MedKnigaData, kit: str = DEFAULT_KIT,
                 output_dir: Path | None = None) -> MedKnigaResult:
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатни ўқитинг")
        if data.exam_date is None:
            raise ValidationError("Кўрик санасини белгиланг")
        if not (data.number or "").strip():
            raise ValidationError("Китоб рақамини киритинг")
        data.blanks = blanks(kit)
        data.layout = load_layout()
        if data.stamp_png is None:
            seal = stamp()
            if seal is not None:
                data.stamp_png = seal.read_bytes()
        pdf = render(data)

        target_dir = output_dir if output_dir is not None else (
            paths.output_dir() / SECTION)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{output_stem(data)}.pdf"
        counter = 2
        while target.exists():
            target = target_dir / f"{output_stem(data)}_{counter:03d}.pdf"
            counter += 1
        target.write_bytes(pdf)
        remember_number(data.number)
        log.info("МЕДКНИЖКА: %s — «%s», № %s, %s", data.surname,
                 KITS[_kit(kit)], data.number, data.exam_date)
        return MedKnigaResult(pdf_path=target, surname=data.surname,
                              number=data.number, exam_date=data.exam_date,
                              expires=data.expires())


def data_of(passport, patent, *, position: str, city: str, number: str,
            exam_date: date | None, photo_png: bytes | None = None,
            signature_png: bytes | None = None) -> MedKnigaData:
    """The book's values out of whichever document the operator dropped."""
    born = getattr(passport, "birth_date", None)
    return MedKnigaData(
        surname=(getattr(passport, "surname", "") or "")
        or (getattr(patent, "holder_surname", "") or "") or "",
        name=(getattr(passport, "name", "") or "")
        or (getattr(patent, "holder_name", "") or "") or "",
        patronymic=(getattr(passport, "patronymic", "") or "")
        or (getattr(patent, "holder_patronymic", "") or "") or "",
        birth_year=str(born.year) if born else "",
        city=city, position=position, number=number, exam_date=exam_date,
        photo_png=photo_png, signature_png=signature_png)
