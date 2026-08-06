"""УЗБ СПРАВКАЛАР — the office's blanks, its firms' seals and the whole chain.

Four certificates go home to the agency about one worker: how he behaves,
what he is paid, how his family is housed and schooled, and that he really
works here. The office keeps three things between runs:

* a BLANK per certificate — its own scanned sheet, uploaded once;
* a SEAL per firm, kept by NAME, because a worker is placed with one of
  several firms and every one of his four certificates carries that firm's
  seal and no other;
* whatever it dragged in «📐 Созлаш».

One press of «Тайёрлаш» then runs each certificate through the same chain:
draw it → photograph it → imgbb (public, DIRECT link) → qrixtools, which
locks that link behind the FOUR-DIGIT CODE printed at the foot → the QR of
the short link seated beside that code → saved as its own PDF.

**Every certificate gets its OWN code.** A sheet that travels on its own —
photographed, forwarded, left on a desk — then opens itself and nothing
else: the other three stay shut behind three other codes.
"""

from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.uzbspravka_renderer import UzbData, output_stem, render

log = get_logger(__name__)

SECTION = "uzbspravka"
#: The four certificates, by the numbers the office calls them.
SHEETS = (1, 2, 3, 4)
SHEET_NAMES = {
    1: "Ишчининг хулқ-атвори",
    2: "Ишчининг маоши",
    3: "Оила ҳолати — яшаш жойи ва болалар мактаби",
    4: "Ҳақиқатан ишлаётгани ҳақида",
}
_PICTURES = (".png", ".jpg", ".jpeg")
_SHEET_KINDS = (".pdf", *_PICTURES)
#: How finely the certificate is photographed for the copy the QR opens —
#: it is read on a phone, so the small print must survive.
QR_DPI = 150


def folder() -> Path:
    made = paths.user_templates_dir() / SECTION
    made.mkdir(parents=True, exist_ok=True)
    return made


def seals_dir() -> Path:
    made = folder() / "seals"
    made.mkdir(parents=True, exist_ok=True)
    return made


def _safe(name: str) -> str:
    """A firm's name, as a file may carry it."""
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-.«»\"'").strip()
    if not cleaned:
        raise ValidationError("Фирма номини ёзинг")
    return cleaned


# ---------------------------------------------------------------- blanks
def blank_of(sheet: int) -> Path | None:
    for suffix in _SHEET_KINDS:
        found = folder() / f"sheet{sheet}{suffix}"
        if found.exists():
            return found
    return None


def blanks() -> dict[int, Path]:
    return {s: found for s in SHEETS if (found := blank_of(s)) is not None}


def set_blank(sheet: int, source: Path) -> Path:
    if sheet not in SHEETS:
        raise ValidationError("Справка 1 дан 4 гача бўлиши керак")
    source = Path(source)
    if source.suffix.lower() not in _SHEET_KINDS:
        raise ValidationError("Бланка PDF ёки расм бўлиши керак")
    if not source.exists():
        raise ValidationError("Бланка файли топилмади")
    clear_blank(sheet)
    target = folder() / f"sheet{sheet}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("УЗБ СПРАВКА: %d-справка бланкаси юкланди", sheet)
    return target


def clear_blank(sheet: int) -> None:
    found = blank_of(sheet)
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------- the firms' seals
def seals() -> dict[str, Path]:
    """Every firm's seal the office has uploaded, by the name it gave it."""
    found: dict[str, Path] = {}
    for path in sorted(seals_dir().iterdir()):
        if path.is_file() and path.suffix.lower() in _PICTURES:
            found[path.stem] = path
    return found


def seal_of(firm: str) -> Path | None:
    return seals().get(_safe(firm)) if (firm or "").strip() else None


def add_seal(firm: str, source: Path) -> Path:
    """One firm, one seal. Uploading again replaces it."""
    source = Path(source)
    if source.suffix.lower() not in _PICTURES:
        raise ValidationError("Печать расм бўлиши керак (шаффоф PNG яхши)")
    if not source.exists():
        raise ValidationError("Печать файли топилмади")
    name = _safe(firm)
    remove_seal(name)
    target = seals_dir() / f"{name}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    log.info("УЗБ СПРАВКА: «%s» печати юкланди", name)
    return target


def remove_seal(firm: str) -> None:
    found = seals().get(_safe(firm))
    if found is not None:
        found.unlink(missing_ok=True)


# ------------------------------------------------------------ the layout
def load_layout() -> dict:
    from src.services import blank_layout

    return blank_layout.load(SECTION, SECTION)


def save_layout(layout: dict) -> None:
    from src.services import blank_layout

    blank_layout.save(SECTION, SECTION, layout)


# ----------------------------------------------------------- the numbers
@dataclass
class SheetNumbers:
    """What one certificate carries that is its own and no other's."""

    #: the four digits at the foot — the key to that certificate's QR
    code: str = ""
    #: «1547-1548» — the tail of the №
    number_tail: str = ""
    #: «Номер заявки»
    request_no: str = ""


def new_code() -> str:
    """Four digits nobody can work out from the last worker's.

    Counted numbers would give the whole run away: hold one certificate and
    you hold the neighbouring codes. :mod:`secrets` is the same source the
    program's own passwords would come from.
    """
    return f"{secrets.randbelow(9000) + 1000:04d}"


def new_numbers(sheets=SHEETS) -> dict[int, SheetNumbers]:
    """A fresh set for one worker — offered to the office, not imposed.

    The screen shows every one of these in a box the office may type over:
    when the state portal has already given a certificate its own number,
    THAT number is the right one and the program must not overwrite it.
    """
    return {sheet: SheetNumbers(
        code=new_code(),
        number_tail=f"{secrets.randbelow(9000) + 1000:04d}-"
                    f"{secrets.randbelow(9000) + 1000:04d}",
        request_no=str(secrets.randbelow(900_000_000) + 100_000_000))
        for sheet in sheets}


# ------------------------------------------------------------- the chain
@dataclass(frozen=True)
class UzbSpravkaResult:
    """One worker's set: where each certificate went and what opens it."""

    #: certificate number → the saved PDF
    pdfs: dict[int, Path]
    #: certificate number → its four-digit code
    codes: dict[int, str]
    #: certificate number → the short link its QR carries («» without one)
    links: dict[int, str]
    surname: str
    firm: str


class UzbSpravkaService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    def _key(self, name: str) -> str:
        if self._settings is None:
            return ""
        return str(self._settings.get(name, "") or "").strip()

    def imgbb_key(self) -> str:
        from src.services.imgbb import KEY_IMGBB

        return self._key(KEY_IMGBB)

    def qrixtools_key(self) -> str:
        from src.services import qrixtools

        return self._key(qrixtools.SETTING_KEY)

    def can_make_qr(self) -> bool:
        """Both keys typed — the office may ask for the code-gated QR."""
        return bool(self.imgbb_key() and self.qrixtools_key())

    def generate(self, data: UzbData, sheets=SHEETS, *,
                 numbers: dict[int, SheetNumbers] | None = None,
                 with_qr: bool = True, output_dir: Path | None = None,
                 uploader=None, linker=None) -> UzbSpravkaResult:
        """Every certificate the office asked for, drawn, gated and saved."""
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — паспортни ўқитинг")
        if not (data.firm or "").strip():
            raise ValidationError("Фирмани танланг — печати ўшаники бўлади")
        seal = seal_of(data.firm)
        if seal is None:
            raise ValidationError(
                f"«{data.firm}» фирмасининг печати юкланмаган — "
                "«⬤ Печатлар» орқали юкланг.")
        wanted = [s for s in SHEETS if s in set(sheets)]
        if not wanted:
            raise ValidationError("Ҳеч бўлмаса битта справкани белгиланг")
        missing = [s for s in wanted if blank_of(s) is None]
        if missing:
            raise ValidationError(
                f"{', '.join(str(s) for s in missing)}-справка бланкаси "
                "юкланмаган — «📄 Бланкалар» орқали юкланг.")
        if with_qr and not self.can_make_qr():
            raise ValidationError(
                "QR учун иккита калит керак — Созламаларда «КРКОД РЕГ» "
                "(imgbb) ва «QRIXTOOLS». Ёки QR'сиз тайёрланг.")

        numbers = numbers or new_numbers(wanted)
        layout = load_layout()
        seal_png = seal.read_bytes()
        target_dir = output_dir if output_dir is not None else (
            paths.output_dir() / SECTION)
        target_dir.mkdir(parents=True, exist_ok=True)

        pdfs: dict[int, Path] = {}
        codes: dict[int, str] = {}
        links: dict[int, str] = {}
        for sheet in wanted:
            own = numbers.get(sheet) or SheetNumbers()
            sheet_data = replace(
                data, layout=layout, seal_png=seal_png, qr_png=None,
                code=own.code or data.code or new_code(),
                number_tail=own.number_tail or data.number_tail,
                request_no=own.request_no or data.request_no)
            pdf = render(sheet_data, sheet, blank_of(sheet))
            if with_qr:
                sheet_data.qr_png, links[sheet] = self._gate(
                    pdf, sheet_data.code,
                    f"{output_stem(data, sheet)}",
                    uploader=uploader, linker=linker)
                pdf = render(sheet_data, sheet, blank_of(sheet))
            pdfs[sheet] = _write(target_dir, output_stem(data, sheet), pdf)
            codes[sheet] = sheet_data.code

        log.info("УЗБ СПРАВКА: %s — %s, %d варақ%s", data.fio(), data.firm,
                 len(pdfs), " (QR билан)" if with_qr else "")
        return UzbSpravkaResult(pdfs=pdfs, codes=codes, links=links,
                                surname=(data.surname or "").strip(),
                                firm=(data.firm or "").strip())

    def _gate(self, pdf: bytes, code: str, name: str, *,
              uploader=None, linker=None) -> tuple[bytes, str]:
        """The certificate → imgbb → a link only ``code`` opens → its QR."""
        import fitz

        from src.services import qrixtools
        from src.services.imgbb import upload

        uploader = uploader or upload
        linker = linker or qrixtools.create_link
        with fitz.open("pdf", pdf) as doc:
            picture = doc[0].get_pixmap(dpi=QR_DPI).tobytes("png")
        direct = uploader(picture, self.imgbb_key(), name=name)
        short = linker(direct, code, name, key=self.qrixtools_key())
        return qrixtools.qr_png(short.url), short.url


def _write(folder: Path, stem: str, pdf: bytes) -> Path:
    """Saved without ever writing over the worker printed a minute ago."""
    target = folder / f"{stem}.pdf"
    counter = 2
    while target.exists():
        target = folder / f"{stem}_{counter:03d}.pdf"
        counter += 1
    target.write_bytes(pdf)
    return target


def data_of(passport, *, firm: str, pinfl: str = "") -> UzbData:
    """The worker as the four certificates name him, out of his passport.

    The Latin line is the passport's OWN Latin, never a transliteration made
    here: «Документ выдан» on these certificates is copied off the document,
    and a name spelled two ways on one desk is a query from the agency.
    """
    latin = " ".join(p for p in (
        getattr(passport, "surname_latin", "") or "",
        getattr(passport, "name_latin", "") or "",
        getattr(passport, "patronymic_latin", "") or "") if p.strip())
    series = getattr(passport, "series", "") or ""
    number = getattr(passport, "number", "") or ""
    return UzbData(
        surname=getattr(passport, "surname", "") or "",
        name=getattr(passport, "name", "") or "",
        patronymic=getattr(passport, "patronymic", "") or "",
        latin_name=latin,
        birth_date=getattr(passport, "birth_date", None),
        # the certificates print it the way the passport does — «FA3445084»
        passport=f"{series}{number}".strip(),
        pinfl=(pinfl or "").strip(),
        firm=(firm or "").strip())
