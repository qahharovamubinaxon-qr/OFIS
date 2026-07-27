"""The module catalogue shared by every remote front end.

The Telegram bot and the Mini App must offer exactly the same work, so each
module is described once here: its label, what has to be picked first, how many
images it needs, which extra questions to ask, and how to run it. Adding a
module to both front ends means adding one row to :data:`MODULES`.

Runners receive a :class:`RunContext` — the built controllers plus a ``note``
callback for progress lines — so they never depend on a particular transport.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.common.errors import OfisError

# ---------------------------------------------------------------- helpers


def parse_date(text: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime((text or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def label_of(item) -> str:
    for attr in ("name", "label", "title"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return str(item)


@dataclass
class RunContext:
    ctl: dict
    note: Callable[[str], None] = lambda text: None


@dataclass(frozen=True)
class Ask:
    """One extra question asked after the images, before the work starts."""

    field: str
    prompt: str
    kind: str = "date"               # date | text
    default_days: int | None = None  # date default = today + N days


@dataclass(frozen=True)
class Module:
    key: str
    button: str
    run: Callable[[RunContext, dict], list[Path]]
    targets: Callable[[dict], list] | None = None
    target_prompt: str = "Танланг:"
    photo_prompt: str = "Расмларни юборинг."
    photo_labels: tuple[str, ...] = ()
    min_photos: int = 1
    asks: tuple[Ask, ...] = ()
    text_only: bool = False          # no images — answers questions instead
    needs_ai: bool = True

    @property
    def title(self) -> str:
        """The button without its leading emoji — for the web UI."""
        parts = self.button.split(" ", 1)
        return parts[1] if len(parts) == 2 else self.button

    @property
    def icon(self) -> str:
        return self.button.split(" ", 1)[0]


def new_state() -> dict:
    return {"mode": None, "step": None, "photos": [], "answers": {},
            "targets": None, "target": None, "ask_index": 0}


# ---------------------------------------------------------------- runners


def _trio(state: dict) -> tuple[bytes, bytes | None, bytes | None]:
    ph = state["photos"]
    return ph[0], (ph[1] if len(ph) > 1 else None), (ph[2] if len(ph) > 2 else None)


def _run_patent(ctx: RunContext, state: dict) -> list[Path]:
    passport, patent, back = _trio(state)
    r = ctx.ctl["process"].generate_from_images(
        state["target"], passport, patent, back,
        form_date=state["answers"].get("form_date") or date.today(), profession=None)
    ctx.note(f"№ {r.reg_number}")
    return [r.pdf_path]


def _run_reg(ctx: RunContext, state: dict) -> list[Path]:
    passport, patent, back = _trio(state)
    r = ctx.ctl["reg"].generate_from_images(
        state["target"], passport, patent, back,
        registration_expiry=state["answers"]["expiry"])
    return [r.pdf_path]


def _run_hostel(ctx: RunContext, state: dict) -> list[Path]:
    passport, patent, back = _trio(state)
    r = ctx.ctl["hostel"].generate_from_images(
        state["target"], passport, patent, back,
        registration_expiry=state["answers"]["expiry"],
        registration_start=state["answers"]["start"])
    return [r.pdf_path]


def _run_trud(ctx: RunContext, state: dict) -> list[Path]:
    passport, patent, back = _trio(state)
    r = ctx.ctl["trud"].generate_from_images(
        state["target"], passport, patent, back,
        form_date=state["answers"].get("form_date") or date.today(), profession=None)
    return [p for p in (r.trud_path, r.uved_path, getattr(r, "hod_path", None)) if p]


def _run_svera(ctx: RunContext, state: dict) -> list[Path]:
    from src.config import paths

    if len(state["photos"]) < 2:
        raise OfisError("Ишчининг расмини ҳам юборинг (2-расм).")
    portrait = paths.output_dir() / "svera" / f"remote_{uuid.uuid4().hex[:8]}.jpg"
    portrait.parent.mkdir(parents=True, exist_ok=True)
    portrait.write_bytes(state["photos"][1])
    r = ctx.ctl["svera"].generate_from_images(
        state["target"], state["photos"][0], portrait,
        issue_date=state["answers"].get("issue_date") or date.today())
    ctx.note(f"Удостоверение № {r.udo_number} · ПО{r.po_number}")
    return [r.pdf_path]


def _run_perevod(ctx: RunContext, state: dict) -> list[Path]:
    r = ctx.ctl["perevod"].translate(state["photos"], doc_type="auto")
    return [p for p in (r.pdf_path, getattr(r, "docx_path", None)) if p]


def _run_photo34(ctx: RunContext, state: dict) -> list[Path]:
    from src.config import paths

    result = ctx.ctl["photo"].process(state["photos"][0])
    out = paths.output_dir() / "photo" / f"remote_3x4_{uuid.uuid4().hex[:8]}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result.png)
    if result.note:
        ctx.note(result.note)
    return [out]


def _run_jpg2pdf(ctx: RunContext, state: dict) -> list[Path]:
    from src.config import paths
    from src.services.jpg2pdf_service import build_pdf

    out = paths.output_dir() / "jpg2pdf" / f"remote_{uuid.uuid4().hex[:8]}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_pdf(state["photos"]))
    return [out]


def _run_summa(ctx: RunContext, state: dict) -> list[Path]:
    from src.utils.rus_words import (
        amount_to_words, date_to_words, format_amount, parse_amount,
    )

    raw = str(state["answers"].get("value", "")).strip()
    as_date = parse_date(raw)
    if as_date is not None:
        ctx.note(date_to_words(as_date))
        return []
    try:
        rubles, kopecks = parse_amount(raw)
    except ValueError:
        ctx.note("Тушунмадим. Сана (25.07.2026) ёки сумма (27500,50) ёзинг.")
        return []
    ctx.note(f"{format_amount(rubles, kopecks)}\n{amount_to_words(rubles, kopecks)}")
    return []


# ---------------------------------------------------------------- catalogue

_TRIO_LABELS = ("Паспорт", "Патент (олд)", "Патент (орқа)")
_TRIO_PROMPT = ("Расмларни ТАРТИБ билан юборинг:\n"
                "1️⃣ Паспорт\n2️⃣ Патент (олд)\n3️⃣ Патент (орқа)")

MODULES: tuple[Module, ...] = (
    Module("patent", "🛂 Патент PDF", _run_patent,
           targets=lambda c: c["process"].companies(),
           target_prompt="Фирмани танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO_LABELS,
           asks=(Ask("form_date", "Ҳужжат санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
    Module("reg", "🏠 Регистрация", _run_reg,
           targets=lambda c: c["reg"].addresses(),
           target_prompt="Манзилни танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO_LABELS,
           asks=(Ask("expiry", "Рўйхатдан ўтиш ТУГАШ санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=90),)),
    Module("hostel", "🛏️ ХОСТЕЛ", _run_hostel,
           targets=lambda c: c["hostel"].addresses(),
           target_prompt="Хостелни танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO_LABELS,
           asks=(Ask("start", "Яшаш БОШЛАНИШ санаси (КК.ОО.ЙЙЙЙ):", default_days=0),
                 Ask("expiry", "Яшаш ТУГАШ санаси (КК.ОО.ЙЙЙЙ):", default_days=90))),
    Module("trud", "📑 Трудовой", _run_trud,
           targets=lambda c: c["trud"].firms(),
           target_prompt="Фирмани танланг:",
           photo_prompt=_TRIO_PROMPT, photo_labels=_TRIO_LABELS,
           asks=(Ask("form_date", "Ҳужжат санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
    Module("svera", "🎓 СФЕРА", _run_svera,
           targets=lambda c: c["svera"].professions(),
           target_prompt="Касбни танланг:",
           photo_prompt="Иккита расм: 1️⃣ Паспорт  2️⃣ Ишчининг расми",
           photo_labels=("Паспорт", "Ишчи расми"), min_photos=2,
           asks=(Ask("issue_date", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
    Module("perevod", "🌐 ПЕРЕВОД", _run_perevod,
           photo_prompt="Таржима қилинадиган ҳужжат расмларини юборинг."),
    Module("photo", "📷 Расм 3×4", _run_photo34,
           photo_prompt="Ишчи расмини юборинг — 3×4 тайёрлаб бераман.",
           photo_labels=("Расм",), needs_ai=False),
    Module("jpg2pdf", "🖼️ JPG→PDF", _run_jpg2pdf,
           photo_prompt="Расмларни тартиб билан юборинг.", needs_ai=False),
    Module("summa", "🔢 СУММА-ДАТА", _run_summa, text_only=True, needs_ai=False,
           asks=(Ask("value", "Сана (25.07.2026) ёки сумма (27500,50) ёзинг:",
                     kind="text"),)),
)

BY_KEY: dict[str, Module] = {m.key: m for m in MODULES}
BY_BUTTON: dict[str, Module] = {m.button: m for m in MODULES}


# ---------------------------------------------------------------- wiring


PEREVOD_NOTARY_KEY = "perevod.notary_name"
PEREVOD_TRANSLATOR_KEY = "perevod.translator_name"
PEREVOD_CITY_KEY = "perevod.notary_city"


def _perevod_cert(container):
    """A getter for the certification-page names, read from settings each run."""
    from src.config.settings_service import SettingsService

    settings = container.resolve(SettingsService)

    def cert() -> dict:
        return {
            "notary": str(settings.get(PEREVOD_NOTARY_KEY, "") or ""),
            "translator": str(settings.get(PEREVOD_TRANSLATOR_KEY, "") or ""),
            "city": str(settings.get(PEREVOD_CITY_KEY, "город Москва") or "город Москва"),
        }

    return cert


def build_controllers(container, key_getter: Callable[[], str]) -> dict:
    """Build every controller the modules need. Qt-free, so it works from a
    background thread (the bot poller) as well as the HTTP server."""
    from src.controllers.hostel_controller import HostelController
    from src.controllers.process_controller import ProcessController
    from src.controllers.registration_controller import RegistrationController
    from src.controllers.svera_controller import SveraController
    from src.controllers.trud_controller import TrudController
    from src.ocr.service import OcrService
    from src.services.company_service import CompanyService
    from src.services.generation_service import GenerationService
    from src.services.hostel_service import HostelService
    from src.services.perevod_service import PerevodService
    from src.services.photo_service import PhotoService
    from src.services.profession_service import ProfessionService
    from src.services.registration_address_service import RegistrationAddressService
    from src.services.registration_service import RegistrationService
    from src.services.svera_service import SveraService
    from src.services.trud_service import TrudFirmService, TrudService

    ocr = container.resolve(OcrService)
    return {
        "process": ProcessController(
            container.resolve(CompanyService), ocr,
            container.resolve(GenerationService)),
        "reg": RegistrationController(
            container.resolve(RegistrationAddressService), ocr,
            container.resolve(RegistrationService)),
        # HostelService is stateless and not container-registered (the desktop
        # view builds it the same way).
        "hostel": HostelController(
            container.resolve(RegistrationAddressService), ocr, HostelService()),
        "trud": TrudController(
            container.resolve(TrudFirmService), ocr, container.resolve(TrudService)),
        "svera": SveraController(
            container.resolve(ProfessionService), ocr,
            container.resolve(SveraService)),
        "perevod": PerevodService(
            key_getter=key_getter, cert_getter=_perevod_cert(container)),
        "photo": PhotoService(key_getter=key_getter),
        "ocr": ocr,
    }
