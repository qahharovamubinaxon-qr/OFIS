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
    kind: str = "date"               # date | text | choice
    default_days: int | None = None  # date default = today + N days

    def options(self) -> list[str]:
        """Values a ``choice`` question accepts (empty for other kinds)."""
        if self.kind != "choice":
            return []
        from src.services.dover_service import DOVER_TYPES

        return list(DOVER_TYPES) if self.field == "doc_type" else []


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
    wants_pdf: int = 0               # PDF documents required as well (УМУМИЙ: 1)
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
    return {"mode": None, "step": None, "photos": [], "pdfs": [], "answers": {},
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


def _run_dms(ctx: RunContext, state: dict) -> list[Path]:
    answers = state["answers"]
    r = ctx.ctl["dms"].generate_from_images(
        state["photos"][0],
        start_date=answers.get("start_date") or date.today(),
        phone=str(answers.get("phone") or ""),
        address=str(answers.get("address") or ""),
        region=str(answers.get("region") or "") or None)
    ctx.note(f"Полис № {r.policy_number} · "
             f"{r.start_date:%d.%m.%Y} — {r.end_date:%d.%m.%Y}")
    return [r.pdf_path]


def _run_inn(ctx: RunContext, state: dict) -> list[Path]:
    answers = state["answers"]
    r = ctx.ctl["inn"].generate_from_image(
        state["photos"][0],
        inn=str(answers.get("inn") or ""),
        form_date=answers.get("form_date") or date.today())
    ctx.note(f"{r.surname} — ИНН {r.inn}")
    return [r.pdf_path]


def _run_beydjik(ctx: RunContext, state: dict) -> list[Path]:
    from src.config import paths

    answers = state["answers"]
    photo = None
    if len(state["photos"]) > 1:
        photo = paths.output_dir() / "beydjik" / f"remote_{uuid.uuid4().hex[:8]}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(state["photos"][1])
    region = str(answers.get("region") or "77").strip() or "77"
    # the remote front ends ask for должность on both regions; a dash means
    # "not applicable", which is how Москва badges are typed
    dolzhnost = str(answers.get("dolzhnost") or "").strip()
    if dolzhnost in {"-", "—", "–"}:
        dolzhnost = ""
    r = ctx.ctl["beydjik"].generate_from_image(
        state["photos"][0],
        region=region,
        personal_number=str(answers.get("personal_number") or ""),
        inn=str(answers.get("inn") or ""),
        issue_date=answers.get("issue_date") or date.today(),
        firm=str(answers.get("firm") or "") or None,
        dolzhnost=dolzhnost,
        photo_path=photo)
    ctx.note(f"{r.surname} — ПР {r.pr_number} ({r.region})")
    return [r.pdf_path]


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


def _run_umumiy(ctx: RunContext, state: dict) -> list[Path]:
    """Re-type an existing office PDF for a new worker."""
    from src.config import paths

    pdfs = state.get("pdfs") or []
    if not pdfs:
        raise OfisError("Аввал қайта ишланадиган ҳужжатни (PDF) юборинг.")
    if not state["photos"]:
        raise OfisError("Ишчининг камида битта ҳужжат расмини юборинг.")

    source = paths.output_dir() / "umumiy" / f"src_{uuid.uuid4().hex[:8]}.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(pdfs[0])

    images = state["photos"]
    passport, patent = ctx.ctl["ocr"].read_documents(
        images[0],
        images[1] if len(images) > 1 else None,
        images[2] if len(images) > 2 else None,
    )
    r = ctx.ctl["umumiy"].generate(
        source, passport, patent,
        form_date=state["answers"].get("form_date") or date.today())
    ctx.note(f"{r.replacements} та жой алмаштирилди")
    return [r.pdf_path]


def _run_dover(ctx: RunContext, state: dict) -> list[Path]:
    """Notarial draft composed from the dropped document photos."""
    r = ctx.ctl["dover"].generate_from_images(
        state["photos"],
        doc_type=str(state["answers"].get("doc_type") or "Авто"),
        description=str(state["answers"].get("description") or ""),
        form_date=state["answers"].get("form_date") or date.today())
    if r.series or r.reestr:
        ctx.note(f"Серия {r.series} · реестр № {r.reestr}")
    return [p for p in (r.pdf_path, r.docx_path) if p]


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
    Module("dms", "🏥 ДМС", _run_dms,
           photo_prompt="Ишчининг паспорт расмини юборинг.",
           photo_labels=("Паспорт",),
           asks=(Ask("start_date", "Полис БОШЛАНИШ санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("phone", "Телефон рақами:", kind="text"),
                 Ask("address", "Рўйхатдан ўтиш манзили:", kind="text"),
                 Ask("region", "Патент ҳудуди (бўш — Москва):", kind="text"))),
    Module("inn", "🔢 ИНН", _run_inn,
           photo_prompt="Ишчининг паспорти ёки патенти расмини юборинг.",
           photo_labels=("Паспорт/патент",),
           asks=(Ask("inn", "ИНН рақами (12 та рақам):", kind="text"),
                 Ask("form_date", "Кун (КК.ОО.ЙЙЙЙ):", default_days=0))),
    Module("beydjik", "🪪 БЕЙДЖИК", _run_beydjik,
           photo_prompt="Иккита расм: 1️⃣ Паспорт  2️⃣ Ишчининг расми",
           photo_labels=("Паспорт", "Ишчи расми"), min_photos=2,
           asks=(Ask("region", "Шаблон/регион (77 — Москва, 50 — область):",
                     kind="text"),
                 Ask("personal_number", "Шахсий номер:", kind="text"),
                 Ask("inn", "ИНН рақами:", kind="text"),
                 Ask("firm", "Фирма (кем выдано):", kind="text"),
                 Ask("dolzhnost", "Должность (фақат 50 учун, керак бўлмаса «-»):",
                     kind="text"),
                 Ask("issue_date", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0))),
    Module("svera", "🎓 СФЕРА", _run_svera,
           targets=lambda c: c["svera"].professions(),
           target_prompt="Касбни танланг:",
           photo_prompt="Иккита расм: 1️⃣ Паспорт  2️⃣ Ишчининг расми",
           photo_labels=("Паспорт", "Ишчи расми"), min_photos=2,
           asks=(Ask("issue_date", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
    Module("perevod", "🌐 ПЕРЕВОД", _run_perevod,
           photo_prompt="Таржима қилинадиган ҳужжат расмларини юборинг."),
    Module("dover", "📜 Доверенность", _run_dover,
           photo_prompt=("Томонларнинг ҳужжат расмларини юборинг "
                         "(паспортлар, СТС ва ҳ.к.)."),
           asks=(Ask("doc_type", "Ҳужжат тури (рақамини ёзинг):", kind="choice"),
                 Ask("description", "Ким, кимга, нима учун — қисқача ёзинг:",
                     kind="text"),
                 Ask("form_date", "Тузилган санаси (КК.ОО.ЙЙЙЙ):", default_days=0))),
    Module("umumiy", "♻️ УМУМИЙ", _run_umumiy,
           photo_prompt=("1️⃣ Аввал қайта ишланадиган ҳужжатни **PDF** қилиб "
                         "юборинг.\n2️⃣ Кейин янги ишчининг ҳужжат расмларини "
                         "(паспорт / патент)."),
           wants_pdf=1,
           asks=(Ask("form_date", "Ҳужжат санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
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
    from src.controllers.beydjik_controller import BeydjikController
    from src.controllers.dms_controller import DmsController
    from src.controllers.hostel_controller import HostelController
    from src.controllers.inn_controller import InnController
    from src.controllers.process_controller import ProcessController
    from src.controllers.registration_controller import RegistrationController
    from src.controllers.svera_controller import SveraController
    from src.controllers.trud_controller import TrudController
    from src.config.settings_service import SettingsService
    from src.ocr.service import OcrService
    from src.services.company_service import CompanyService
    from src.services.beydjik_service import BeydjikService
    from src.services.dms_service import DmsService
    from src.services.dover_service import DoverService
    from src.services.generation_service import GenerationService
    from src.services.hostel_service import HostelService
    from src.services.inn_service import InnService
    from src.services.perevod_service import PerevodService
    from src.services.photo_service import PhotoService
    from src.services.profession_service import ProfessionService
    from src.services.registration_address_service import RegistrationAddressService
    from src.services.registration_service import RegistrationService
    from src.services.svera_service import SveraService
    from src.services.trud_service import TrudFirmService, TrudService
    from src.services.umumiy_service import UmumiyService

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
        # Both are stateless services the desktop views build the same way.
        "dms": DmsController(ocr, DmsService(container.resolve(SettingsService))),
        "inn": InnController(ocr, InnService()),
        "beydjik": BeydjikController(
            ocr, BeydjikService(container.resolve(SettingsService))),
        "umumiy": UmumiyService(key_getter=key_getter),
        "dover": DoverService(key_getter=key_getter,
                              settings=container.resolve(SettingsService)),
        "photo": PhotoService(key_getter=key_getter),
        "ocr": ocr,
    }
