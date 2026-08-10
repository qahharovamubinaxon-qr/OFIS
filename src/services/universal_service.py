"""УНИВЕРСАЛ — the office's own library of blanks, and printing onto them.

The office said why this exists in one sentence: it does not want a new
section written for every new form. So a *form* here is nothing but a blank
it uploaded, a name it gave, and the texts it dragged into place. Add a form
by uploading it; never by changing code.

Where things live
-----------------
::

    <AppData>/OFIS/templates/universal/<form>/blank.pdf
                                             /fields.json
                                             /stamp.png       (ихтиёрий)
                                             /signature.png   (ихтиёрий)

In AppData, because anything kept beside the program is lost the next time
the EXE is rebuilt — and an afternoon of lining texts up on a blank is
exactly what the office must never lose. **Nothing here deletes a form on its
own.** Only :func:`remove` does, and only when the office asks it to.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.universal_fields import (
    PICTURES,
    Field,
    UniversalData,
    is_custom,
    output_stem,
)
from src.pdf.universal_renderer import page_pngs, render

log = get_logger(__name__)

SECTION = "universal"
BLANK_STEM = "blank"
FIELDS_FILE = "fields.json"
#: The pictures a form keeps for itself, so the office uploads its stamp once
#: rather than with every worker. The worker's own photograph is not among
#: them — that changes every time.
KEPT_PICTURES = ("stamp", "signature")

#: What a blank may arrive as. The office scans some forms and photographs
#: others; both become pages that can be written on.
BLANK_KINDS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")


def folder() -> Path:
    made = paths.user_templates_dir() / SECTION
    made.mkdir(parents=True, exist_ok=True)
    return made


def _safe(name: str) -> str:
    """A form's name as a folder name — the office types these freely."""
    kept = "".join(c if c.isalnum() or c in " _-()№" else "_"
                   for c in (name or "")).strip()
    return " ".join(kept.split()) or "blank"


def _home(name: str) -> Path:
    return folder() / _safe(name)


# ------------------------------------------------------------- the library
def names() -> list[str]:
    """Every form the office has saved, in alphabetical order."""
    return sorted(p.name for p in folder().iterdir()
                  if p.is_dir() and blank_of(p.name) is not None)


def blank_of(name: str) -> Path | None:
    home = _home(name)
    for suffix in BLANK_KINDS:
        found = home / f"{BLANK_STEM}{suffix}"
        if found.exists():
            return found
    return None


def add(name: str, source: Path | str) -> str:
    """Take a blank into the library under the office's own name for it."""
    name = " ".join((name or "").split())
    if not name:
        raise ValidationError("Бланкага ном беринг.")
    source = Path(source)
    if source.suffix.lower() not in BLANK_KINDS:
        raise ValidationError("Бланка PDF ёки расм бўлиши керак.")
    if not source.exists():
        raise ValidationError("Бланка файли топилмади.")
    if _safe(name) in names():
        raise ValidationError(f"«{name}» номли бланка аллақачон бор — "
                              "бошқа ном беринг ёки эскисини ўчиринг.")
    home = _home(name)
    home.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, home / f"{BLANK_STEM}{source.suffix.lower()}")
    log.info("УНИВЕРСАЛ: «%s» бланкаси юкланди", name)
    return _safe(name)


def rename(name: str, into: str) -> str:
    into = " ".join((into or "").split())
    if not into:
        raise ValidationError("Янги ном бўш.")
    if _safe(into) in names():
        raise ValidationError(f"«{into}» номли бланка аллақачон бор.")
    home = _home(name)
    if not home.exists():
        raise ValidationError(f"«{name}» топилмади.")
    home.rename(folder() / _safe(into))
    return _safe(into)


def remove(name: str) -> None:
    """Delete a form — the ONLY thing here that ever does.

    The office was explicit: «йуклаган бланкаларим узим учирмагунимча
    хечкачон учмасин». Nothing else in this module removes anything.
    """
    home = _home(name)
    if home.exists():
        shutil.rmtree(home, ignore_errors=True)
        log.info("УНИВЕРСАЛ: «%s» ўчирилди — офиснинг ўз сўровига кўра", name)


def pages(name: str, zoom: float = 1.6) -> list[bytes]:
    """The blank's pages as pictures, for arranging texts on."""
    blank = blank_of(name)
    if blank is None:
        raise ValidationError(f"«{name}» бланкаси топилмади.")
    return page_pngs(blank, zoom)


# -------------------------------------------------------------- the texts
def fields(name: str) -> list[Field]:
    """What the office arranged on this form."""
    store = _home(name) / FIELDS_FILE
    if not store.exists():
        return []
    try:
        raw = json.loads(store.read_text("utf-8"))
    except (OSError, ValueError):
        log.warning("УНИВЕРСАЛ: «%s» майдонлари ўқилмади", name)
        return []
    if not isinstance(raw, list):
        return []
    out: list[Field] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        # `Field.as_dict` does not carry the turn — it was added for the
        # blanks that print up their own edge — so it is read back here.
        out.append(replace(Field.from_dict(entry),
                           rotate=int(entry.get("rotate") or 0)))
    return out


def save_fields(name: str, placed: list[Field]) -> None:
    home = _home(name)
    if not home.exists():
        raise ValidationError(f"«{name}» бланкаси топилмади.")
    raw = []
    for item in placed:
        entry = item.as_dict()
        entry["rotate"] = int(getattr(item, "rotate", 0) or 0)
        raw.append(entry)
    (home / FIELDS_FILE).write_text(
        json.dumps(raw, ensure_ascii=False, indent=1), "utf-8")
    log.info("УНИВЕРСАЛ: «%s» — %d та матн сақланди", name, len(raw))


def custom_keys(name: str) -> list[str]:
    """The boxes the office invented for this form, in the order placed."""
    seen: list[str] = []
    for item in fields(name):
        if is_custom(item.key) and item.key not in seen:
            seen.append(item.key)
    return seen


def wants(name: str) -> set[str]:
    """Every key this form actually uses — the screen shows only these."""
    return {item.key for item in fields(name)}


# ----------------------------------------------------- the kept pictures
def picture_of(name: str, which: str) -> Path | None:
    if which not in KEPT_PICTURES:
        return None
    for suffix in (".png", ".jpg", ".jpeg"):
        found = _home(name) / f"{which}{suffix}"
        if found.exists():
            return found
    return None


def set_picture(name: str, which: str, source: Path | str) -> Path:
    """The firm's stamp or signature, kept with the form that uses it."""
    if which not in KEPT_PICTURES:
        raise ValidationError("Фақат печать ёки имзо сақланади.")
    source = Path(source)
    if source.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValidationError("Печать ва имзо PNG ёки JPG бўлиши керак.")
    if not source.exists():
        raise ValidationError("Файл топилмади.")
    clear_picture(name, which)
    home = _home(name)
    home.mkdir(parents=True, exist_ok=True)
    target = home / f"{which}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    return target


def clear_picture(name: str, which: str) -> None:
    found = picture_of(name, which)
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------------- the making
@dataclass(frozen=True)
class UniversalResult:
    pdf: Path
    form: str
    surname: str


class UniversalService:
    def generate(self, name: str, data: UniversalData,
                 output_dir: Path | None = None) -> UniversalResult:
        blank = blank_of(name)
        if blank is None:
            raise ValidationError(f"«{name}» бланкаси топилмади.")
        placed = fields(name)
        if not placed:
            raise ValidationError(
                f"«{name}» да бирорта матн жойлаштирилмаган — "
                "«📐 Созлаш» орқали қўйинг.")

        # the stamp and signature the form keeps for itself, unless this run
        # brought its own
        for which in KEPT_PICTURES:
            attribute = f"{which}_png"
            if getattr(data, attribute, None):
                continue
            kept = picture_of(name, which)
            if kept is not None:
                setattr(data, attribute, kept.read_bytes())

        target_dir = output_dir if output_dir is not None else (
            paths.output_dir() / SECTION)
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = output_stem(data, name)
        made = target_dir / f"{stem}.pdf"
        counter = 2
        while made.exists():
            made = target_dir / f"{stem}_{counter:03d}.pdf"
            counter += 1
        made.write_bytes(render(data, blank, placed))
        log.info("УНИВЕРСАЛ: «%s» — %s", name, made.name)
        return UniversalResult(pdf=made, form=name,
                               surname=(data.surname or "").strip())


def _said(source, *names: str) -> str:
    for name in names:
        value = getattr(source, name, "") or ""
        if str(value).strip():
            return str(value).strip()
    return ""


def data_of(passport=None, patent=None) -> UniversalData:
    """What the reader found, in the shape the fields want.

    Both documents are optional: some forms need only a name, and the office
    said as much — «бази хужатларга ишчи расми керак, базисига керак эмас».

    The passport and the patent each fill their OWN named boxes, and are
    copied into the first two free slots as well, so a form arranged either
    way prints. The patent's region is not read at all — it is worked out
    from the series, which is what the series is for.
    """
    made = UniversalData()
    if passport is not None:
        gender = getattr(getattr(passport, "gender", None), "value",
                         getattr(passport, "gender", "")) or ""
        made.surname = _said(passport, "surname").title()
        made.name = _said(passport, "name").title()
        made.patronymic = _said(passport, "patronymic").title()
        made.gender = ("Женский" if str(gender).lower().startswith(("f", "ж"))
                       else "Мужской")
        made.citizenship = _said(passport, "nationality").title()
        made.birth_place = (_said(passport, "birth_place")
                            or made.citizenship).title()
        made.birth_date = getattr(passport, "birth_date", None)

        made.pass_series = _said(passport, "series")
        made.pass_number = _said(passport, "number")
        made.pass_issued_by = _said(passport, "issued_by")
        made.pass_issued = getattr(passport, "issue_date", None)
        made.pass_expires = getattr(passport, "expiry_date", None)
        if made.pass_series or made.pass_number:
            made.documents[1] = (made.pass_series, made.pass_number)

    if patent is not None:
        made.pat_series = _said(patent, "series")
        made.pat_number = _said(patent, "number")
        made.pat_blank_series = _said(patent, "blank_series")
        made.pat_blank_number = _said(patent, "blank_number")
        made.pat_issued_by = _said(patent, "issued_by")
        made.pat_issued = getattr(patent, "issue_date", None) or getattr(
            patent, "valid_from", None)
        made.pat_expires = getattr(patent, "valid_to", None) or getattr(
            patent, "expire_date", None)
        made.position = _said(patent, "profession")
        if made.pat_series or made.pat_number:
            made.documents[2] = (made.pat_series, made.pat_number)

        from src.domain.patent_regions import region_of_series

        made.pat_region = region_of_series(made.pat_series)
        # the plain «регион» box follows the patent when nothing else set it
        made.region = made.region or made.pat_region
        made.issued = made.issued or made.pat_issued
        made.expires = made.expires or made.pat_expires
    return made


__all__ = ["BLANK_KINDS", "KEPT_PICTURES", "PICTURES", "SECTION",
           "UniversalData", "UniversalResult", "UniversalService", "add",
           "blank_of", "clear_picture", "custom_keys", "data_of", "fields",
           "folder", "names", "pages", "picture_of", "remove", "rename",
           "save_fields", "set_picture", "wants"]
