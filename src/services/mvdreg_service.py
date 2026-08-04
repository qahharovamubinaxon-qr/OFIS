"""МВД РЕГИСТРАЦИЯ — the office's own отрывная часть, sent to МВД as a PDF.

The same МВД form the ХОСТЕЛ section fills, but on the office's OWN blank
and with the office's own hands on everything: the worker comes off the
passport, the operator types the start and end dates, and the start date is
stamped in BLUE — «10 АВГ 2026» — inside the «Отметка о подтверждении» box
on the back, exactly the way МВД's own stamp prints it.

Everything else the office may change itself, in one window: every printed
value can be moved, resized, recoloured and given any font the computer
has; its own texts can be added (each told what it means); a signature is
drawn with the mouse; a stamp picture is uploaded. What it arranges is kept
beside the blank in AppData and survives every update of the EXE.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.domain.documents import Passport, Patent
from src.domain.registration_address import RegistrationAddress
from src.pdf.engine import fill
from src.pdf.mapping import Field_, FieldMapping, with_layout
from src.services.registration_values import build_registration_values

log = get_logger(__name__)

SECTION = "mvdreg"
STAY_FROM = "reg.stay_from"
#: The layout format's age. Bumped whenever saved positions stop being
#: trustworthy: v2 dropped the spots the first editor pinned wholesale;
#: v3 dropped drags made against the FIRST blank, which the office then
#: replaced with the hostel-identical print (its cells sit elsewhere).
LAYOUT_V = 3

#: The blue the МВД date stamp prints in, measured off the office's scan.
STAMP_INK = (0.291, 0.676, 0.917)
#: The signature's ink.
SIGN_INK = (0.10, 0.13, 0.45)

#: What a text the office adds may mean — everything the program knows.
CATALOGUE: dict[str, str] = {
    "fio": "ФИО — тўлиқ",
    "surname": "Фамилия", "name": "Исм", "patronymic": "Отчество",
    "citizenship": "Гражданство",
    "birth_date": "Туғилган сана (КК.ОО.ЙЙЙЙ)",
    "pass_full": "Паспорт — серия ва номер",
    "pass_issued": "Паспорт — берилган сана",
    "pass_expiry": "Паспорт — амал қилиш охири",
    "start_date": "Бошланиш санаси (КК.ОО.ЙЙЙЙ)",
    "start_stamp": "Бошланиш санаси — штамп (10 АВГ 2026)",
    "end_date": "Тугаш санаси (КК.ОО.ЙЙЙЙ)",
    "address": "Адрес — тўлиқ",
    "host_fio": "Қабул қилувчи — ФИО",
    "org": "Ташкилот номи", "inn": "Ташкилот ИНН",
    "regional_number": "Уведомление рақами (№)",
    "free1": "Эркин матн 1", "free2": "Эркин матн 2", "free3": "Эркин матн 3",
}

SAMPLES: dict[str, str] = {
    "fio": "Жураева Нафиса Абдуллаевна", "surname": "Жураева",
    "name": "Нафиса", "patronymic": "Абдуллаевна",
    "citizenship": "УЗБЕКИСТАН", "birth_date": "28.05.1982",
    "pass_full": "FB 0701509", "pass_issued": "27.01.2025",
    "pass_expiry": "26.01.2035", "start_date": "10.08.2026",
    "start_stamp": "10 АВГ 2026", "end_date": "08.11.2026",
    "address": "Московская обл., г. Балашиха, ул. Ленина, д. 33",
    "host_fio": "ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ",
    "org": "ООО «СФЕРА»", "inn": "7733481040",
    "regional_number": "02\\770-2026", "free1": "матн", "free2": "матн",
    "free3": "матн",
}

#: The three fixed labels the editor shows for the two pictures.
IMG_KEYS = ("img_sign", "img_stamp")
IMG_LABELS = {"img_sign": "✍ ИМЗО (қўл қўйиш)", "img_stamp": "⬤ ПЕЧАТЬ"}
#: x = left edge, baseline = bottom edge, size = height — page fractions.
#: The signature starts inside the «Подпись принимающей стороны» box
#: (measured 0.091–0.464 × 0.308–0.413 on this blank), the stamp inside
#: «Печать организации» below it; the office drags both from there.
IMG_DEFAULTS = {"img_sign": (2, 0.15, 0.400, 0.055),
                "img_stamp": (2, 0.13, 0.600, 0.130)}


def bundled_dir() -> Path:
    return paths.templates_dir() / "mvdreg"


def store_dir() -> Path:
    folder = paths.user_templates_dir() / "mvdreg"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def blank_path() -> Path:
    """The office's current blank — its own upload, else the bundled one."""
    own = store_dir() / "blank.pdf"
    return own if own.exists() else bundled_dir() / "blank.pdf"


def set_blank(source: Path) -> Path:
    source = Path(source)
    if source.suffix.lower() != ".pdf" or not source.exists():
        raise ValidationError("Бланка PDF бўлиши керак")
    dest = store_dir() / "blank.pdf"
    shutil.copyfile(source, dest)
    log.info("МВД РЕГ: янги бланка юкланди")
    return dest


def mapping_path() -> Path:
    return bundled_dir() / "mapping.v1.json"


def _asset(name: str) -> Path:
    return store_dir() / name


def set_signature(png: bytes) -> Path:
    _asset("sign.png").write_bytes(png)
    return _asset("sign.png")


def set_stamp(source: Path) -> Path:
    from src.services.alpinist_service import ink_only

    source = Path(source)
    if not source.exists():
        raise ValidationError("Печать расми топилмади")
    _asset("stamp.png").write_bytes(ink_only(source.read_bytes()))
    return _asset("stamp.png")


def asset(name: str) -> Path | None:
    found = _asset(f"{name}.png")
    return found if found.exists() else None


def clear_asset(name: str) -> None:
    _asset(f"{name}.png").unlink(missing_ok=True)


@dataclass(frozen=True)
class MvdRegResult:
    pdf_path: Path
    surname: str


def texts_of(passport: Passport, address: RegistrationAddress | None,
             start: date, expiry: date) -> dict[str, str]:
    """Every catalogue meaning's finished text."""
    from src.pdf.formatters import FORMATTERS

    fio = " ".join(p for p in (passport.surname, passport.name,
                               passport.patronymic or "") if p)
    return {
        "fio": fio.title(), "surname": passport.surname.title(),
        "name": passport.name.title(),
        "patronymic": (passport.patronymic or "").title(),
        "citizenship": passport.nationality or "",
        "birth_date": (f"{passport.birth_date:%d.%m.%Y}"
                       if passport.birth_date else ""),
        "pass_full": " ".join(p for p in (passport.series or "",
                                          passport.number) if p),
        "pass_issued": (f"{passport.issue_date:%d.%m.%Y}"
                        if passport.issue_date else ""),
        "pass_expiry": (f"{passport.expiry_date:%d.%m.%Y}"
                        if passport.expiry_date else ""),
        "start_date": f"{start:%d.%m.%Y}",
        "start_stamp": FORMATTERS["date_stamp_ru"](start),
        "end_date": f"{expiry:%d.%m.%Y}",
        "address": (address.address_text if address else "") or "",
        "host_fio": (address.host_fio if address else "") or "",
        "org": (address.organization_name if address else "") or "",
        "inn": (address.inn if address else "") or "",
        "regional_number": (address.regional_number if address else "") or "",
        "free1": "・", "free2": "・", "free3": "・",
    }


def _decorated(mapping: FieldMapping, layout: dict) -> FieldMapping:
    """The shared mapping, wearing everything the office arranged.

    ``styles``  — per printed value: its font, colour, weight.
    ``extra``   — the office's own added texts (trud8-style dicts).
    ``images``  — where the signature and the stamp go.
    """
    width, height = mapping.page_size
    styles = layout.get("styles") or {}
    fields: list[Field_] = []
    for field in mapping.fields:
        chosen = styles.get(field.id)
        if chosen:
            update: dict = {}
            if chosen.get("font"):
                update["font"] = str(chosen["font"])
            if chosen.get("colour"):
                update["colour"] = [float(c) for c in chosen["colour"][:3]]
            field = field.model_copy(update=update)
        fields.append(field)

    for index, extra in enumerate(layout.get("extra") or []):
        key = str(extra.get("key") or "free1")
        fields.append(Field_.model_validate({
            "id": f"extra.{key}#{index}", "type": "text",
            "page": int(extra.get("page") or 1),
            "x": float(extra.get("x", 0.1)) * width,
            "y": float(extra.get("baseline", 0.1)) * height,
            "size": float(extra.get("size", 0.013)) * height,
            "font": str(extra.get("font") or "Times New Roman"),
            "align": "left", "_calibrated": True,
            "colour": [float(c) for c in (extra.get("colour")
                                          or (0, 0, 0))[:3]],
        }))

    images = layout.get("images") or {}
    for key in IMG_KEYS:
        if asset(key.removeprefix("img_")) is None:
            continue
        page, x, bottom, h = images.get(key) or IMG_DEFAULTS[key]
        fields.append(Field_.model_validate({
            "id": key, "type": "image", "page": int(page),
            "x": float(x) * width, "y": (float(bottom) - float(h)) * height,
            "width": float(h) * height * 3.0, "height": float(h) * height,
            "_calibrated": True,
        }))
    return mapping.model_copy(update={"fields": fields})


class MvdRegService:
    def generate(
        self,
        passport: Passport,
        patent: Patent | None,
        address: RegistrationAddress,
        *,
        registration_expiry: date,
        registration_start: date | None = None,
        output_dir: Path | None = None,
    ) -> MvdRegResult:
        from src.services import blank_layout

        start = registration_start or date.today()
        values: dict[str, object] = build_registration_values(
            passport, patent, registration_expiry=registration_expiry)
        values[STAY_FROM] = start.isoformat()
        for key in IMG_KEYS:
            found = asset(key.removeprefix("img_"))
            if found is not None:
                values[key] = str(found)
        # the office's own texts print whatever their meaning stands for
        texts = texts_of(passport, address, start, registration_expiry)
        layout = blank_layout.load(SECTION, address.template_path)
        for index, extra in enumerate(layout.get("extra") or []):
            key = str(extra.get("key") or "free1")
            values[f"extra.{key}#{index}"] = texts.get(key, "")

        mapping = _decorated(
            with_layout(FieldMapping.load(mapping_path()), layout), layout)
        out = self._unique_path(address, passport, output_dir)
        fill(address.template_path, mapping, values, out)
        log.info("МВД РЕГ: %s — %s", passport.surname, address.label)
        return MvdRegResult(pdf_path=out, surname=passport.surname)

    @staticmethod
    def _unique_path(address: RegistrationAddress, passport: Passport,
                     base: Path | None) -> Path:
        folder = base if base is not None else (
            paths.output_dir() / "mvdreg"
            / "".join(c for c in address.label if c.isalnum() or c in " _-"))
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c for c in f"{passport.surname}_{passport.name}".upper()
                       if c.isalnum() or c in "_-") or "MVDREG"
        made = folder / f"{stem}.pdf"
        i = 1
        while made.exists():
            made = folder / f"{stem}_{i:03d}.pdf"
            i += 1
        return made


def _drop_stale_layout(template: Path) -> bool:
    """Old saved positions, cleared once — they pinned the WRONG cells.

    The first editor wrote down every value's position on OK, moved or
    not, and it opened with the uncorrected map — so those saved spots
    keep overriding the corrected one. Everything the office really made
    itself (extra texts, styles, the pictures) is kept.
    """
    from src.services import blank_layout

    layout = blank_layout.load(SECTION, template)
    if not layout or int(layout.get("v") or 1) >= LAYOUT_V:
        return False
    layout.pop("fields", None)
    layout["v"] = LAYOUT_V
    blank_layout.save(SECTION, template, layout)
    log.info("МВД РЕГ: %s даги эски жойлашув тозаланди", Path(template).name)
    return True


def refresh_templates(addresses: list[RegistrationAddress]) -> int:
    """Rebuild address templates older than the shared address map.

    The office added addresses, then the map was corrected — every template
    those addresses were printed with still carries the OLD cell positions.
    Rather than asking the office to re-add each address, any template built
    before the map's last change is quietly rebuilt from the same data.
    Uploaded ready-made templates carry no address parts, so they are never
    touched.
    """
    map_file = bundled_dir() / "address_mapping.v1.json"
    if not map_file.exists():
        return 0
    stamp = map_file.stat().st_mtime
    rebuilt = 0
    builder = MvdRegTemplateBuilder()
    for address in addresses:
        template = Path(address.template_path)
        forced = _drop_stale_layout(template)
        if not (address.oblast or address.gorod or address.ulitsa):
            continue
        try:
            if (not forced and template.exists()
                    and template.stat().st_mtime >= stamp):
                continue
            builder.build(template, address)
            rebuilt += 1
        except Exception as exc:                      # noqa: BLE001
            log.warning("МВД РЕГ: «%s» шаблони янгиланмади: %s",
                        address.label, exc)
    if rebuilt:
        log.info("МВД РЕГ: %d та адрес шаблони янги харитага қайта қурилди",
                 rebuilt)
    return rebuilt


class MvdRegTemplateBuilder:
    """Print an address's fixed data onto the office's blank — once, when the
    address is added; every worker then prints on that ready template."""

    def available(self) -> bool:
        return blank_path().exists() and \
            (bundled_dir() / "address_mapping.v1.json").exists()

    def build(self, out: Path, address: RegistrationAddress) -> Path:
        from src.services import blank_layout

        # the office may have dragged or restyled the address/host texts in
        # «📐» — their saved spots and styles are laid over the shared map
        # for THIS template
        layout = blank_layout.load(SECTION, out)
        mapping = _decorated(with_layout(
            FieldMapping.load(bundled_dir() / "address_mapping.v1.json"),
            layout), {"styles": layout.get("styles") or {}})
        fio = (address.host_fio or "").split()
        values = {
            "host.addr.subject": address.oblast or "",
            "host.addr.locality": address.raion or "",
            "host.addr.settlement": address.gorod or "",
            "host.addr.street": address.ulitsa or "",
            "host.addr.dom": f"ДОМ {address.dom}" if address.dom else "",
            "host.addr.korpus": (f"КОРПУС {address.korpus}"
                                 if address.korpus else ""),
            "host.addr.litera": (f"ЛИТЕРА {address.stroenie}"
                                 if address.stroenie else ""),
            "host.addr.komnata": (f"КВ. {address.kvartira}"
                                  if address.kvartira else
                                  (f"КОМ. {address.komnata}"
                                   if address.komnata else "")),
            "host.surname": fio[0] if fio else "",
            "host.name": fio[1] if len(fio) > 1 else "",
            "host.patronymic": " ".join(fio[2:]),
            "host.org": address.organization_name or "",
            "host.inn": address.inn or "",
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        fill(blank_path(), mapping, values, out)
        log.info("МВД РЕГ: «%s» шаблони қурилди", address.label)
        return out
