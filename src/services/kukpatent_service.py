"""КУК ПАТЕНТ — the office's two blanks, its firms and its numbering.

Three things are kept between runs and nothing else:

* a BLANK per side — the office's own scan, uploaded once;
* the FIRMS it issues cards for, saved as they are typed, because the same
  handful come round again and nobody should retype a legal name;
* the card number it is up to — «АА3915699», which moves on by TWO for the
  next worker, on the office's own instruction.

Whatever was dragged in «📐 Созлаш» is kept beside them. Everything lives in
AppData, so rebuilding the EXE never touches any of it.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.kukpatent_renderer import KukPatentData, output_stem, render_pair
from src.pdf.kukpatent_spec import BACK, FRONT, SIDE_NAMES, SIDES

log = get_logger(__name__)

SECTION = "kukpatent"
_FIRMS = "firms.json"
_COUNTER = "number.json"
_TYPED = "typed.json"
_PICTURES = (".png", ".jpg", ".jpeg")
_BLANK_KINDS = (".pdf", *_PICTURES)

#: How far the card's own number moves for the next worker. The office was
#: exact about it: «ҳар ишчида 2 рақамдан ўзгариб туради».
STEP = 2
#: «АА3915699» — two letters and seven digits.
_CARD = re.compile(r"^\s*([^\W\d_]{0,4})\s*(\d+)\s*$", re.UNICODE)


def folder() -> Path:
    made = paths.user_templates_dir() / SECTION
    made.mkdir(parents=True, exist_ok=True)
    return made


# ---------------------------------------------------------------- blanks
def blank_of(side: str) -> Path | None:
    for suffix in _BLANK_KINDS:
        found = folder() / f"{side}{suffix}"
        if found.exists():
            return found
    return None


def blanks() -> dict[str, Path]:
    return {s: found for s in SIDES if (found := blank_of(s)) is not None}


def set_blank(side: str, source: Path) -> Path:
    if side not in SIDES:
        raise ValidationError("Томони «олди» ёки «орқаси» бўлиши керак")
    source = Path(source)
    if source.suffix.lower() not in _BLANK_KINDS:
        raise ValidationError("Бланка PDF ёки расм бўлиши керак")
    if not source.exists():
        raise ValidationError("Бланка файли топилмади")
    clear_blank(side)
    target = folder() / f"{side}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("КУК ПАТЕНТ: «%s» бланкаси юкланди", SIDE_NAMES[side])
    return target


def clear_blank(side: str) -> None:
    found = blank_of(side)
    if found is not None:
        found.unlink(missing_ok=True)


# ----------------------------------------------------------- the firms
def firms() -> list[str]:
    """Every firm the office has typed, newest first."""
    store = folder() / _FIRMS
    if not store.exists():
        return []
    try:
        kept = json.loads(store.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [str(f) for f in kept if str(f).strip()] \
        if isinstance(kept, list) else []


def remember_firm(firm: str) -> None:
    """Keep the firm for next time; typing it again just moves it to the top."""
    firm = "\n".join(line.strip() for line in (firm or "").splitlines()).strip()
    if not firm:
        return
    kept = [f for f in firms() if f.strip().casefold() != firm.casefold()]
    kept.insert(0, firm)
    (folder() / _FIRMS).write_text(
        json.dumps(kept[:40], ensure_ascii=False), "utf-8")


def forget_firm(firm: str) -> None:
    kept = [f for f in firms() if f.strip().casefold() != (firm or "").casefold()]
    (folder() / _FIRMS).write_text(
        json.dumps(kept, ensure_ascii=False), "utf-8")


# ------------------------------------------------ what the office typed
#: The серия and the номер printed at the top of the front. They belong to
#: the office's own run of blanks, not to the worker, so they are the same
#: from one card to the next — «киритган номерларим майдонда доим турсин,
#: ўзим бошқасига ўзгартирмагунимча». Kept the moment the box is left, so
#: closing the program without printing loses nothing.
TYPED = ("series", "number")


def typed() -> dict[str, str]:
    store = folder() / _TYPED
    if not store.exists():
        return {}
    try:
        kept = json.loads(store.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(kept, dict):
        return {}
    return {k: str(kept.get(k, "") or "") for k in TYPED}


def remember_typed(**boxes: str) -> None:
    """Keep what the office typed. Only what is named is touched."""
    kept = typed()
    for key, value in boxes.items():
        if key in TYPED:
            kept[key] = (value or "").strip()
    (folder() / _TYPED).write_text(
        json.dumps(kept, ensure_ascii=False), "utf-8")


# --------------------------------------------------------- the numbering
def next_number() -> str:
    """The card number the office is up to — "" until it types one."""
    store = folder() / _COUNTER
    if not store.exists():
        return ""
    try:
        return str(json.loads(store.read_text("utf-8")).get("next", "") or "")
    except (OSError, ValueError):
        return ""


def step_number(used: str) -> str:
    """«АА3915699» → «АА3915701». Two on, letters untouched, width kept.

    A number that is not one is handed back as it stands: the office alone
    knows how its own series runs, and inventing a shape for it would put a
    number on a card that belongs to nobody.
    """
    found = _CARD.match(used or "")
    if not found:
        return (used or "").strip()
    letters, digits = found.group(1), found.group(2)
    return f"{letters}{str(int(digits) + STEP).zfill(len(digits))}"


def remember_number(used: str) -> None:
    """One card done — the NEXT worker's is two along."""
    used = (used or "").strip()
    if not used:
        return
    (folder() / _COUNTER).write_text(
        json.dumps({"next": step_number(used)}, ensure_ascii=False), "utf-8")


# ------------------------------------------------------------ the layout
def load_layout() -> dict:
    from src.services import blank_layout

    return blank_layout.load(SECTION, SECTION)


def save_layout(layout: dict) -> None:
    from src.services import blank_layout

    blank_layout.save(SECTION, SECTION, layout)


# ------------------------------------------------------------ the making
@dataclass(frozen=True)
class KukPatentResult:
    """One worker's card: where it went and what number it carries."""

    #: ONE document — the front is its first page, the back its second
    pdf: Path
    surname: str
    firm: str
    card_no: str


class KukPatentService:
    def generate(self, data: KukPatentData,
                 output_dir: Path | None = None) -> KukPatentResult:
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — паспортни ўқитинг")
        if not (data.firm or "").strip():
            raise ValidationError("Фирмани танланг ёки ёзинг")
        if not (data.series or "").strip() or not (data.number or "").strip():
            raise ValidationError("Серия ва номерни киритинг (88 · 3259366)")
        have = blanks()
        missing = [SIDE_NAMES[s] for s in SIDES if s not in have]
        if missing:
            raise ValidationError(
                f"{', '.join(missing)} бланкаси юкланмаган — «📄 Бланкалар» "
                "орқали юкланг.")

        data.layout = load_layout()
        if not (data.card_no or "").strip():
            data.card_no = next_number()

        target_dir = output_dir if output_dir is not None else (
            paths.output_dir() / SECTION)
        target_dir.mkdir(parents=True, exist_ok=True)
        made = _write(target_dir, output_stem(data), render_pair(data, have))

        remember_firm(data.firm)
        remember_number(data.card_no)
        remember_typed(series=data.series, number=data.number)
        log.info("КУК ПАТЕНТ: %s — %s, № %s", data.fio(), data.firm,
                 data.card_no)
        return KukPatentResult(pdf=made, surname=data.surname.strip(),
                               firm=data.firm.strip(),
                               card_no=(data.card_no or "").strip())


def _write(folder_: Path, stem: str, pdf: bytes) -> Path:
    """Saved without ever writing over the worker printed a minute ago."""
    target = folder_ / f"{stem}.pdf"
    counter = 2
    while target.exists():
        target = folder_ / f"{stem}_{counter:03d}.pdf"
        counter += 1
    target.write_bytes(pdf)
    return target


def data_of(passport, *, firm: str, series: str, number: str,
            issued, card_no: str = "",
            photo_png: bytes | None = None) -> KukPatentData:
    """The card's values out of the worker's passport.

    The document line is what the card itself prints — «Иностранный паспорт»
    and the series and number run together, exactly as the office's own
    sample has it.
    """
    series_p = (getattr(passport, "series", "") or "")
    number_p = (getattr(passport, "number", "") or "")
    gender = getattr(passport, "gender", None)
    said = getattr(gender, "value", gender) or ""
    return KukPatentData(
        surname=(getattr(passport, "surname", "") or "").title(),
        name=(getattr(passport, "name", "") or "").title(),
        patronymic=(getattr(passport, "patronymic", "") or "").title(),
        birth_date=getattr(passport, "birth_date", None),
        gender="Ж" if str(said).lower().startswith(("f", "ж", "жен")) else "М",
        citizenship=(getattr(passport, "nationality", "") or "").title(),
        document=f"Иностранный паспорт {series_p}{number_p}".strip(),
        series=(series or "").strip(), number=(number or "").strip(),
        firm=(firm or "").strip(), issued=issued,
        card_no=(card_no or "").strip(), photo_png=photo_png)


__all__ = ["FRONT", "BACK", "KukPatentResult", "KukPatentService", "blank_of",
           "blanks", "clear_blank", "data_of", "firms", "folder",
           "forget_firm", "load_layout", "next_number", "remember_firm",
           "remember_number", "remember_typed", "save_layout", "set_blank",
           "step_number", "typed"]
