"""КРКОД РЕГ — blanks, the address book, and the whole QR pipeline.

One press of «Тайёрлаш» runs the chain the owner described: fill the
подтверждение → photograph it → imgbb (public, DIRECT link) → QR of that link
→ the QR seated in the box on the registration's back → front+back saved as
one PDF **onto the Desktop**, named after the worker.

The dormitory's address, its «Уведомление зарегистрировано №» code and the
host person are typed once and kept; every saved address carries its own code
and host, so switching dormitories switches everything together.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.qrreg_renderer import (
    QrRegData,
    make_qr,
    output_name,
    render_podt,
    render_registration,
)
from src.services import blank_layout
from src.services.imgbb import KEY_IMGBB, upload

log = get_logger(__name__)

SECTION = "qrreg"
PODT_SECTION = "qrreg_podt"
BLANK_SUFFIXES = {".pdf"}

KEY_ADDRESSES = "qrreg.addresses"
MAX_ADDRESSES = 30

#: What one saved dormitory carries — the address pieces, its code, its host.
ADDRESS_FIELDS = ("label", "addr_subject", "addr_district", "addr_punkt",
                  "addr_street", "dom", "korpus", "kvartira", "code",
                  "host_surname", "host_name", "host_patronymic")


@dataclass(frozen=True)
class QrRegResult:
    pdf: bytes
    saved: Path
    surname: str
    link: str


def templates_dir(kind: str = "reg") -> Path:
    folder = paths.user_templates_dir() / "qrreg"
    if kind == "podt":
        folder = folder / "podt"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


def desktop_dir() -> Path:
    """The owner asked for the finished PDF on the РАБОЧИЙ СТОЛ."""
    desktop = Path.home() / "Desktop"
    if not desktop.exists():                     # OneDrive-redirected machines
        desktop = Path.home() / "OneDrive" / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    return desktop


def _drop_legacy(layout: dict) -> dict:
    """Saved layouts from before the cell grid was re-measured repeat the old
    defaults verbatim for every field the office never touched. Those entries
    must not pin the letters to the old spots — a genuine drag differs from
    the legacy numbers and survives untouched."""
    from src.pdf.qrreg_spec import LEGACY_REG

    fields = (layout or {}).get("fields") or {}
    kept = {}
    for key, moved in fields.items():
        old = LEGACY_REG.get(key)
        if old is not None and len(moved) == 3 and all(
                abs(float(a) - b) < 1e-6
                for a, b in zip(moved, old, strict=True)):
            continue
        kept[key] = moved
    if not kept:
        return {}
    return {**layout, "fields": kept}


class QrRegService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        return sorted(p for p in templates_dir().iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка 2 саҳифали PDF бўлиши керак")
        dest = templates_dir() / f"{_safe(name)}.pdf"
        shutil.copyfile(source, dest)
        log.info("КРКОД РЕГ бланкаси қўшилди: %s", dest.name)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        blank_layout.reset(SECTION, template)

    def podt_template(self) -> Path | None:
        """The one подтверждение blank — uploaded once, used everywhere."""
        found = sorted(templates_dir("podt").glob("*.pdf"))
        return found[0] if found else None

    def set_podt_template(self, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Подтверждение PDF бўлиши керак")
        for old in templates_dir("podt").glob("*.pdf"):
            old.unlink(missing_ok=True)
        dest = templates_dir("podt") / "podtverjdenie.pdf"
        shutil.copyfile(source, dest)
        log.info("Подтверждение шаблони янгиланди")
        return dest

    # ------------------------------------------------------------ layout
    def layout(self, template: Path | None) -> dict:
        if not template:
            return {}
        return _drop_legacy(blank_layout.load(SECTION, template))

    def save_layout(self, template: Path, layout: dict) -> Path:
        return blank_layout.save(SECTION, template, layout)

    def podt_layout(self) -> dict:
        template = self.podt_template()
        return blank_layout.load(PODT_SECTION, template) if template else {}

    def save_podt_layout(self, layout: dict) -> None:
        template = self.podt_template()
        if template:
            blank_layout.save(PODT_SECTION, template, layout)

    # ------------------------------------------------------ the addresses
    def addresses(self) -> list[dict]:
        if self._settings is None:
            return []
        raw = str(self._settings.get(KEY_ADDRESSES, "") or "")
        try:
            data = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
        return [a for a in data if isinstance(a, dict)] \
            if isinstance(data, list) else []

    def remember_address(self, entry: dict) -> None:
        """Keep the dormitory — its address, code and host — for next time."""
        if self._settings is None:
            return
        entry = {k: " ".join(str(entry.get(k, "")).split())
                 for k in ADDRESS_FIELDS}
        if not entry["addr_street"] and not entry["addr_subject"]:
            return
        key = json.dumps([entry[k].upper() for k in
                          ("addr_subject", "addr_street", "dom", "kvartira")])
        kept = [a for a in self.addresses()
                if json.dumps([str(a.get(k, "")).upper() for k in
                               ("addr_subject", "addr_street", "dom",
                                "kvartira")]) != key]
        kept.insert(0, entry)
        self._settings.set(KEY_ADDRESSES,
                           json.dumps(kept[:MAX_ADDRESSES], ensure_ascii=False))

    def imgbb_key(self) -> str:
        if self._settings is None:
            return ""
        return str(self._settings.get(KEY_IMGBB, "") or "").strip()

    # ---------------------------------------------------------- the chain
    def generate(self, data: QrRegData, template: Path | None,
                 uploader=upload) -> QrRegResult:
        """Подтверждение → imgbb → QR → registration → Desktop."""
        if template is None:
            raise ValidationError(
                "КРКОД РЕГ бланкаси юкланмаган — «➕ Бланка» орқали юкланг.")
        podt = self.podt_template()
        if podt is None:
            raise ValidationError(
                "Подтверждение шаблони юкланмаган — «Подтверждение» тугмаси "
                "билан бир марта юклаб қўйинг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")

        podt_data = QrRegData(**{**data.__dict__,
                                 "layout": self.podt_layout()})
        _podt_pdf, podt_png = render_podt(podt_data, podt)
        link = uploader(podt_png, self.imgbb_key(),
                        name=output_name(data).removesuffix(".pdf"))
        qr = make_qr(link)

        data.layout = self.layout(Path(template))
        pdf = render_registration(data, Path(template), qr)

        target = desktop_dir() / output_name(data)
        counter = 2
        while target.exists():
            target = (desktop_dir()
                      / f"{target.stem.split(' (')[0]} ({counter}).pdf")
            counter += 1
        target.write_bytes(pdf)

        self.remember_address({
            "label": data.full_address(),
            "addr_subject": data.addr_subject,
            "addr_district": data.addr_district,
            "addr_punkt": data.addr_punkt,
            "addr_street": data.addr_street,
            "dom": data.dom, "korpus": data.korpus, "kvartira": data.kvartira,
            "code": data.code,
            "host_surname": data.host_surname, "host_name": data.host_name,
            "host_patronymic": data.host_patronymic})
        log.info("КРКОД РЕГ: %s — %s (%s)", data.fio(), target.name, link)
        return QrRegResult(pdf=pdf, saved=target,
                           surname=(data.surname or "").strip(), link=link)
