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
from datetime import date, datetime, time
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
    """What to show for one item in a pick list.

    ``callable`` is checked because a plain string is a perfectly good target —
    the ПЕРЕВОД sheets are three of them — and ``"1 — ...".title`` is a METHOD,
    so without this the button read «built-in method title of str object».
    """
    for attr in ("name", "label", "title"):
        value = getattr(item, attr, None)
        if value and not callable(value):
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

    #: What a ``choice`` question accepts, when it is not the доверенность list.
    choices: tuple[str, ...] = ()

    def options(self) -> list[str]:
        """Values a ``choice`` question accepts (empty for other kinds)."""
        if self.kind != "choice":
            return []
        if self.choices:
            return list(self.choices)
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
    #: Takes ONE file that may be a PDF *or* a picture, either is fine — a blank
    #: sheet arrives as whichever the office happens to have.
    accepts_pdf: bool = False
    asks: tuple[Ask, ...] = ()
    text_only: bool = False          # no images — answers questions instead
    needs_ai: bool = True
    #: A module the operator can jump to from THIS module's pick list, offered as
    #: an extra «➕» row under the items. Регистрация uses it so a new address
    #: can be added on the phone instead of only on the computer.
    add_key: str | None = None
    add_prompt: str = "➕ Янги қўшиш"
    #: Checked the moment the section is opened: returns why it cannot run yet,
    #: or "" when it can. Without this a module that needs something set up on
    #: the computer asks every question first and only then refuses — and the
    #: refusal scrolls away behind the menu, so it reads as «it just does
    #: nothing». ЧЕК needs the company id.
    ready: Callable[[dict], str] | None = None

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
    """ТД + УВ off the firm's own mapped samples."""
    passport_img, patent_img, back = _trio(state)
    ctl = ctx.ctl["trud"]
    passport, patent = ctl.read_documents(passport_img, patent_img, back)
    ctx.note(f"Ҳужжатлар ўқилди: {passport.surname or ''} "
             f"{passport.name or ''}".strip())
    result = ctl.generate(
        firm=Path(state["target"]), passport=passport, patent=patent,
        profession=str(state["answers"].get("profession") or "").strip(),
        deal_date=state["answers"].get("form_date") or date.today(),
        want_pdf=True)
    for out in result.saved:
        if out.suffix.lower() == ".docx":
            ctx.note("Word ҳолида юборилди — PDF учун компютерда Word керак.")
            break
    return list(result.saved)


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


def _run_badge(ctx: RunContext, state: dict, which: str) -> list[Path]:
    """БЕЙДЖИК and ПАТЕНТ — the same card, printed on a different blank.

    The desktop keeps them one-to-one by inheritance; the remote front ends
    keep them one-to-one by sharing this runner.
    """
    from src.config import paths

    answers = state["answers"]
    photo = None
    if len(state["photos"]) > 1:
        photo = paths.output_dir() / which / f"remote_{uuid.uuid4().hex[:8]}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(state["photos"][1])
    region = str(answers.get("region") or "77").strip() or "77"
    # the remote front ends ask for должность on both regions; a dash means
    # "not applicable", which is how Москва badges are typed
    dolzhnost = str(answers.get("dolzhnost") or "").strip()
    if dolzhnost in {"-", "—", "–"}:
        dolzhnost = ""
    r = ctx.ctl[which].generate_from_image(
        state["photos"][0],
        region=region,
        personal_number=str(answers.get("personal_number") or ""),
        inn=str(answers.get("inn") or ""),
        issue_date=answers.get("issue_date") or date.today(),
        firm=str(answers.get("firm") or "") or None,
        dolzhnost=dolzhnost,
        territory=str(answers.get("territory") or "").strip(),
        photo_path=photo)
    ctx.note(f"{r.surname} — ПР {r.pr_number} ({r.region})")
    return [r.pdf_path]


def _run_beydjik(ctx: RunContext, state: dict) -> list[Path]:
    return _run_badge(ctx, state, "beydjik")


def _run_patent_card(ctx: RunContext, state: dict) -> list[Path]:
    return _run_badge(ctx, state, "patent")


def _run_razreshenie(ctx: RunContext, state: dict) -> list[Path]:
    """РАЗРЕШЕНИЯ — passport + portrait, the numbers allocated in order."""
    from src.config import paths

    answers = state["answers"]
    ctl = ctx.ctl["razreshenie"]
    fields = ctl.read_passport(state["photos"][0])
    birth = parse_date(fields.pop("birth_date", ""))

    firm_name = str(answers.get("firm_name") or "").strip()
    firm_inn = str(answers.get("firm_inn") or "").strip()
    if not firm_name:
        # the section keeps the last firm in the field until a new one is
        # typed; leaving it blank on the phone means "the same firm again"
        remembered = ctl.firm()
        firm_name = remembered.name
        firm_inn = firm_inn or remembered.inn

    result = ctl.generate(
        **fields, birth_date=birth,
        inn=str(answers.get("inn") or "").strip(),
        activity=str(answers.get("activity") or "").strip(),
        valid_from=answers.get("valid_from") or date.today(),
        firm_name=firm_name, firm_inn=firm_inn,
        photo=state["photos"][1])

    out = _free_path(paths.output_dir() / "razreshenie", result.filename)
    out.write_bytes(result.pdf)
    ctx.note(f"{result.seria} {result.number} · ВВ {result.back_number}\n"
             f"{result.valid_from:%d.%m.%Y} — {result.valid_to:%d.%m.%Y}")
    return [out]


def _run_ppu(ctx: RunContext, state: dict) -> list[Path]:
    """ППУ — everything comes off the регистрация the office already issued.

    The operator sends that регистрация and the worker's photograph; the only
    thing typed is the day the pair starts, and even the end date is taken off
    the регистрация unless it could not be read. The blank is the office's own,
    uploaded on the computer — there is nothing bundled to fall back on, which
    is why the template is picked first.
    """
    from src.config import paths

    answers = state["answers"]
    ctl = ctx.ctl["ppu"]
    fields = ctl.read_registration(state["photos"][0])

    valid_from = answers.get("valid_from") or parse_date(
        fields.get("stay_from", "")) or date.today()
    valid_to = parse_date(str(answers.get("valid_to_text") or "")) or parse_date(
        fields.get("stay_to", ""))

    result = ctl.generate(
        surname=fields.get("surname", ""), name=fields.get("name", ""),
        patronymic=fields.get("patronymic", ""),
        birth_date=parse_date(fields.get("birth_date", "")),
        gender=fields.get("gender", ""),
        citizenship=fields.get("citizenship", ""),
        document=fields.get("document", ""),
        address=fields.get("address", ""),
        valid_from=valid_from, valid_to=valid_to,
        photo=state["photos"][1] if len(state["photos"]) > 1 else None,
        template=state["target"])

    folder = paths.output_dir() / "ppu"
    out: list[Path] = []
    for index, png in enumerate(result.pages, 1):
        page = _free_path(folder, f"{_stem(fields.get('surname', ''))} ППУ "
                                  f"{index}.png")
        page.write_bytes(png)
        out.append(page)
    span = (f"{result.valid_from:%d.%m.%Y} — {result.valid_to:%d.%m.%Y}"
            if result.valid_to else f"{result.valid_from:%d.%m.%Y} — ?")
    ctx.note(f"{result.passport} · {span}")
    if not result.valid_to:
        ctx.note("⚠️ Тугаш санаси регистрациядан ўқилмади — жуфтликда бўш "
                 "қолди, керак бўлса қўлда ёзиб қўйинг.")
    return out


def _run_snils(ctx: RunContext, state: dict) -> list[Path]:
    """СНИЛС — the passport, the day it was registered, and the number."""
    from src.config import paths

    answers = state["answers"]
    ctl = ctx.ctl["snils"]
    fields = ctl.read_passport(state["photos"][0])
    birth = parse_date(fields.pop("birth_date", ""))

    result = ctl.generate(
        **fields, birth_date=birth,
        reg_date=answers.get("reg_date") or date.today(),
        snils=str(answers.get("snils") or "").strip(),
        template=state["target"])

    out = _free_path(paths.output_dir() / "snils", result.filename)
    out.write_bytes(result.pdf)
    ctx.note(f"СНИЛС {result.snils}"
             + (f" · {result.reg_date:%d.%m.%Y}" if result.reg_date else ""))
    return [out]


def _stem(surname: str) -> str:
    return "".join(c for c in (surname or "").strip()
                   if c.isalnum() or c in " _-").strip() or "ISHCHI"


def _run_sertifikat(ctx: RunContext, state: dict) -> list[Path]:
    """СЕРТИФИКАТ — the passport, the city, the day it was issued.

    Only the name comes off the passport, so one photograph is enough. Both
    numbers re-roll their tails inside the service, exactly as on the desktop.
    """
    from src.config import paths

    answers = state["answers"]
    ctl = ctx.ctl["sertifikat"]
    fields = ctl.read_passport(state["photos"][0])

    result = ctl.generate(
        **fields,
        city=str(answers.get("city") or "").strip(),
        issued_on=answers.get("issued_on") or date.today())

    out = _free_path(paths.output_dir() / "sertifikat", result.filename)
    out.write_bytes(result.pdf)
    ctx.note(f"Регистрационный № {result.reg_number} · штрих "
             f"{result.barcode_number}\n"
             f"{result.issued_on:%d.%m.%Y} — {result.valid_until:%d.%m.%Y}")
    return [out]


def _free_path(folder: Path, filename: str) -> Path:
    """``Сейтимов.pdf`` → ``Сейтимов (2).pdf`` — an earlier card is never lost."""
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / filename
    stem, suffix, index = candidate.stem, candidate.suffix, 2
    while candidate.exists():
        candidate = folder / f"{stem} ({index}){suffix}"
        index += 1
    return candidate


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


def _run_chek(ctx: RunContext, state: dict) -> list[Path]:
    """ЧЕК — the receipt for a premium the office actually paid.

    The two values that make it a record rather than a picture are not
    generated here or anywhere else: the код авторизации is copied off the
    bank's own confirmation by the operator, and the company id is the
    office's, recorded once in Sozlamalar. Without either, nothing prints.
    """
    from src.config import paths

    answers = state["answers"]
    ctl = ctx.ctl["chek"]
    if not ctl.company_id():
        raise OfisError("Компания коди йўқ — компютерда ЧЕК бўлимида бир "
                        "марта ёзиб қўйинг, кейин ботдан ишлатасиз.")

    fields = ctl.read_patent_fields(state["photos"][0])
    try:
        rub, kop = ctl.parse_amount(str(answers.get("summa") or ""))
    except ValueError:
        raise OfisError("Суммани тўғри ёзинг, масалан: 15000,50") from None

    when = datetime.combine(answers.get("when_date") or date.today(),
                            _clock(str(answers.get("when_time") or "")))
    pdf, name = ctl.generate(
        **fields,
        card4=str(answers.get("card4") or ""),
        when=when, rub=rub, kop=kop,
        avtoriz=str(answers.get("avtoriz") or ""))

    out = _free_path(paths.output_dir() / "chek", name)
    out.write_bytes(pdf)
    ctx.note(f"{fields['fam']} {fields['ism']} · {rub:,}".replace(",", " ")
             + f",{kop:02d} ₽ · {when:%d.%m.%Y %H:%M:%S}")
    return [out]


def _clock(text: str) -> time:
    """«14:30» / «14:30:05» / blank → the time on the receipt."""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text.strip(), fmt).time()
        except ValueError:
            continue
    return datetime.now().time().replace(microsecond=0)


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


def _run_insurance(ctx: RunContext, state: dict) -> list[Path]:
    """ОСАГО — the СТС decides the car, the licences decide who is covered."""
    photos, answers = state["photos"], state["answers"]
    result = ctx.ctl["insurance"].generate_from_images(
        template=Path(state["target"]), sts_front=photos[0],
        sts_back=photos[1] if len(photos) > 1 else None,
        licences=photos[2:6],
        start=answers.get("start") or date.today())
    cover = (f"{result.drivers} та ҳайдовчи (лица, допущенные)"
             if result.drivers else "без ограничения")
    ctx.note(f"{result.plate} · {cover}")
    return [result.saved]


def _run_shablon(ctx: RunContext, state: dict) -> list[Path]:
    """Fill one of the forms the operator already studied on the computer."""
    from src.config import paths

    target = state["target"]
    study, _known = ctx.ctl["template"].study(target.path)
    out = paths.output_dir() / "shablon" / (
        f"{target.path.stem}_{uuid.uuid4().hex[:8]}{target.path.suffix}")
    out.parent.mkdir(parents=True, exist_ok=True)
    photos = state["photos"]
    result = ctx.ctl["template"].fill_from_images(
        study, target.path, out, photos[0],
        photos[1] if len(photos) > 1 else None,
        form_date=state["answers"].get("form_date") or date.today(),
        profession=str(state["answers"].get("profession") or ""))
    ctx.note(f"{len(result.written)} та қиймат ёзилди")
    if result.problems:
        ctx.note("\n".join(f"⚠️ {problem}" for problem in result.problems))
    return [result.path]


def _run_summa(ctx: RunContext, state: dict) -> list[Path]:
    from src.utils.rus_words import (
        amount_to_words,
        date_to_words,
        format_amount,
        parse_amount,
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


def _run_trud_ppu(ctx: RunContext, state: dict) -> list[Path]:
    """ТРУД ППУ — трудовой + уведомление (PDFs) + патент (photos).

    Sheet 1 goes on the ППУ front blank. The phone has one list to pick from and
    it picks the ТРУД ППУ pair, so the ППУ front is taken from the FIRST ППУ
    template the office uploaded — the office keeps one.
    """
    ctl = ctx.ctl["trud_ppu"]
    pdfs = state["pdfs"]
    photos = state["photos"]
    fields: dict[str, str] = {}
    fields.update(ctl.read_contract(pdfs[0]))
    fields.update({k: v for k, v in ctl.read_uved(pdfs[1]).items() if v})
    patent = ctl.read_patent(photos[0], photos[1] if len(photos) > 1 else None)
    fields.update({k: v for k, v in patent.items() if v})
    ctx.note(f"Ўқилди: {fields.get('surname', '')} · патент "
             f"{fields.get('patent_series', '')} {fields.get('patent_number', '')} · "
             f"{fields.get('firm', '')}".strip())

    ppu_templates = ctx.ctl["ppu"].templates()
    result = ctl.generate(
        surname=fields.get("surname", ""), name=fields.get("name", ""),
        patronymic=fields.get("patronymic", ""),
        birth_date=ctl.parse_date(fields.get("birth_date", "")),
        gender=fields.get("gender", ""),
        citizenship=fields.get("citizenship", ""),
        document=fields.get("document", ""),
        patent_series=fields.get("patent_series", ""),
        patent_number=fields.get("patent_number", ""),
        patent_issue=ctl.parse_date(fields.get("patent_issue", "")),
        contract_date=ctl.parse_date(fields.get("contract_date", "")),
        firm=fields.get("firm", ""),
        uved_number=fields.get("uved_number", ""),
        uved_fio=fields.get("uved_fio", ""),
        photo=photos[2] if len(photos) > 2 else None,
        ppu_template=ppu_templates[0] if ppu_templates else None,
        template=state["target"])
    return result.saved


def _run_perevod_blank(ctx: RunContext, state: dict) -> list[Path]:
    """Upload one of the ПЕРЕВОД sheets from the phone.

    The office prints its translations on its own three sheets. They used to be
    uploadable only at the computer; now a sheet can be replaced from the phone
    too — the same AppData folder, so the computer sees it at once.
    """
    from src.config import paths
    from src.services.perevod_service import BLANK_SUFFIXES, blanks, set_blank

    index = int(str(state["target"]).strip()[0])
    data = (state["pdfs"] or state["photos"])[0]
    suffix = ".pdf" if state["pdfs"] else ".png"
    if suffix not in BLANK_SUFFIXES:                     # pragma: no cover
        raise OfisError("Бланка PDF ёки расм бўлиши керак.")
    staging = paths.output_dir() / "perevod" / f"blank_{uuid.uuid4().hex[:8]}{suffix}"
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(data)
    try:
        set_blank(index, staging)
    finally:
        staging.unlink(missing_ok=True)
    loaded = [str(i) for i, blank in enumerate(blanks(), 1) if blank is not None]
    ctx.note(f"✅ {index}-бланка юкланди.\n"
             f"Юкланган бланкалар: {', '.join(loaded) or '—'} (3 та керак)")
    return []


#: What each ПЕРЕВОД sheet is for, in the order they are printed.
PEREVOD_SHEETS = ("1 — ҳужжат нусхаси қўйилади",
                  "2 — таржима матни ёзилади",
                  "3 — бўш қолади, нотариус тўлдиради")


def _run_reg_addr(ctx: RunContext, state: dict) -> list[Path]:
    """Register a new address from the phone — the computer's ten-field table.

    The template is built from the blank «Уведомление о прибытии» exactly as the
    computer's dialog does when no ready-made PDF is uploaded, because a phone
    cannot hand over a pre-filled template.
    """
    from src.domain.registration_address import RegistrationAddress

    answers = {k: str(v or "").strip() for k, v in state["answers"].items()}
    summary = ", ".join(part for part in (
        answers.get("oblast", ""), answers.get("raion", ""),
        answers.get("gorod", ""), answers.get("ulitsa", ""),
        f"д. {answers['dom']}" if answers.get("dom") else "",
        f"к. {answers['korpus']}" if answers.get("korpus") else "",
        f"стр. {answers['stroenie']}" if answers.get("stroenie") else "",
        f"кв. {answers['kvartira']}" if answers.get("kvartira") else "",
    ) if part)
    if not summary:
        raise OfisError("Манзил бўш — камида область, шаҳар ва кўчани ёзинг.")

    label = answers.get("label") or summary
    code = answers.get("internal_code") or _code_from(label)
    address = RegistrationAddress(
        label=label, internal_code=code, address_text=summary,
        host_fio=answers.get("host_fio") or "-",
        oblast=answers.get("oblast") or None, raion=answers.get("raion") or None,
        gorod=answers.get("gorod") or None, ulitsa=answers.get("ulitsa") or None,
        dom=answers.get("dom") or None, korpus=answers.get("korpus") or None,
        stroenie=answers.get("stroenie") or None,
        kvartira=answers.get("kvartira") or None,
        regional_number=answers.get("regional_number") or None,
        template_path=Path("missing.pdf"))
    ctx.ctl["reg_addr"].create(address, build_from_blank=True)
    ctx.note(f"✅ Манзил қўшилди: {address.label}\n{summary}\n\n"
             "Энди «🏠 Регистрация» босиб рўйхатдан танланг.")
    return []


def _code_from(label: str) -> str:
    """A folder-safe unique key from the name the operator typed."""
    latin = "".join(c if c.isalnum() else "_" for c in label.lower()).strip("_")
    return f"{latin[:24] or 'addr'}_{uuid.uuid4().hex[:6]}"


def _run_qrreg(ctx: RunContext, state: dict) -> list[Path]:
    """КРКОД РЕГ from the phone — the saved dormitory does the heavy lifting.

    The address, its code and its host come off the LAST SAVED dormitory (the
    computer is where they are typed once); the phone supplies the worker's
    two photographs and the dates.
    """
    ctl = ctx.ctl["qrreg"]
    known = ctl.addresses()
    if not known:
        raise OfisError("Адрес ҳали сақланмаган — компютерда КРКОД РЕГ "
                        "бўлимида бир марта тўлдириб «Тайёрлаш» қилинг.")
    photos = state["photos"]
    worker = ctl.read_documents(photos[0],
                                photos[1] if len(photos) > 1 else None)
    ctx.note(f"Ҳужжатлар ўқилди: {worker.surname or ''} "
             f"{worker.name or ''}".strip())
    answers = state["answers"]
    entry = known[0]
    result = ctl.generate(
        template=Path(state["target"]), passport=worker,
        valid_from=answers.get("valid_from") or date.today(),
        valid_to=answers.get("valid_to") or date.today(),
        address=entry, code=str(entry.get("code") or ""))
    ctx.note(f"🔗 {result.link}")
    return [result.saved]


def _run_spr3(ctx: RunContext, state: dict) -> list[Path]:
    """3-СПРАВКА from the phone: passport + the Russian-ФИО photo."""
    ctl = ctx.ctl["spr3"]
    photos = state["photos"]
    worker = ctl.read_documents(photos[0],
                                photos[1] if len(photos) > 1 else None)
    ctx.note(f"Ҳужжатлар ўқилди: {worker.surname or ''} "
             f"{worker.name or ''}".strip())
    answers = state["answers"]
    result = ctl.generate(
        template=Path(state["target"]), passport=worker,
        valid_from=answers.get("valid_from") or date.today(),
        address={"oblast": str(answers.get("oblast") or ""),
                 "gorod": str(answers.get("gorod") or ""),
                 "ulitsa": str(answers.get("ulitsa") or ""),
                 "dom": str(answers.get("dom") or ""),
                 "korpus": str(answers.get("korpus") or ""),
                 "kvartira": str(answers.get("kvartira") or "")},
        num3=str(answers.get("num3") or ""),
        ser3=str(answers.get("ser3") or ""),
        num5=str(answers.get("num5") or ""))
    return [result.saved]


def _run_alpinist(ctx: RunContext, state: dict) -> list[Path]:
    """АЛПИНИСТ from the phone.

    The mouse pad only exists in the program, so on the phone the worker
    signs on a white sheet of paper and photographs it — the paper is made
    transparent the same way the печать's is, and only the ink lands on
    the card. The blank number counts itself up, as on the computer.
    """
    ctl = ctx.ctl["alpinist"]
    photos = state["photos"]
    if len(photos) < 3:
        raise OfisError("Учта расм керак: паспорт, ишчи расми, имзо.")
    worker = ctl.read_documents(photos[0],
                                photos[3] if len(photos) > 3 else None)
    ctx.note(f"Ҳужжатлар ўқилди: {worker.surname or ''} "
             f"{worker.name or ''}".strip())
    from src.services.alpinist_service import ink_only

    answers = state["answers"]
    result = ctl.generate(
        template=Path(state["target"]), passport=worker,
        issue_date=answers.get("issue_date") or date.today(),
        ud_number=str(answers.get("ud_number") or "").strip(),
        blank_number=str(ctl.next_number()),
        photo=photos[1], signature=ink_only(photos[2]))
    return [result.saved]


def _run_imgbb(ctx: RunContext, state: dict) -> list[Path]:
    """IMGBB from the phone: the picture up, the direct link and its QR back."""
    from src.config import paths

    ctl = ctx.ctl["imgbb"]
    link = ctl.upload(state["photos"][0], name="imgbb")
    ctx.note(f"🔗 {link}")
    out = paths.output_dir() / "imgbb" / f"qr_{uuid.uuid4().hex[:8]}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(ctl.qr(link))
    return [out]


def _run_mvd_trud(ctx: RunContext, state: dict) -> list[Path]:
    """МВД ТРУДАВОЙ from the phone: three photographs, a date, a должность."""
    ctl = ctx.ctl["mvd_trud"]
    photos = state["photos"]
    passport, patent = ctl.read_documents(
        photos[0], photos[1], photos[2] if len(photos) > 2 else None)
    ctx.note(f"Ҳужжатлар ўқилди: {passport.surname or ''} "
             f"{passport.name or ''}".strip())
    answers = state["answers"]
    result = ctl.generate(
        template=Path(state["target"]), passport=passport, patent=patent,
        profession=str(answers.get("profession") or "").strip()
        or (patent.profession or ""),
        deal_date=answers.get("deal_date") or date.today(),
        uved_no=str(answers.get("uved_no") or "").strip(),
        spravka_no=str(answers.get("spravka_no") or "").strip(),
        # the place of work is the firm's own — what the computer remembered
        work_address=ctl.work_address())
    return [result.saved]


def _run_rusreg(ctx: RunContext, state: dict) -> list[Path]:
    """РУС РЕГ from the phone.

    One photograph — a Russian internal passport or a birth certificate; the
    first question says which, and the sheet's «вид» line follows it. The
    address, the firm and the running number fall back to what the office
    last used on the computer, so on the phone they can simply be skipped.
    """
    ctl = ctx.ctl["rusreg"]
    answers = state["answers"]
    is_passport = "МЕТРКА" not in str(answers.get("doc_kind") or "").upper()

    fields = ctl.read_document(state["photos"][0], is_passport=is_passport)
    ctx.note(f"Ҳужжат ўқилди: {fields.get('surname', '')} "
             f"{fields.get('name', '')}".strip())

    kept = ctl.remembered()
    result = ctl.generate(
        template=Path(state["target"]),
        reg_number=str(answers.get("reg_number") or "").strip() or kept["reg_number"],
        surname=fields.get("surname", ""), name=fields.get("name", ""),
        patronymic=fields.get("patronymic", ""),
        birth_date=ctl.parse_date(fields.get("birth_date", "")),
        birth_place=fields.get("birth_place", ""),
        address=str(answers.get("address") or "").strip() or kept["address"],
        valid_from=answers.get("valid_from"), valid_to=answers.get("valid_to"),
        is_passport=is_passport,
        doc_series=fields.get("series", ""), doc_number=fields.get("number", ""),
        doc_issued=ctl.parse_date(fields.get("issue_date", "")),
        doc_issued_by=fields.get("issued_by", ""),
        firm=str(answers.get("firm") or "").strip() or kept["firm"],
        signer=kept["signer"])
    return [result.saved]


def _run_mig(ctx: RunContext, state: dict) -> list[Path]:
    """МИГ ИШЧИ КАРТАСИ from the phone.

    The blank is picked from the list; the firm's stamp is the one saved under
    the SAME name, already placed where the office dragged it on the computer.
    A phone cannot drag a stamp into position, so it never has to.
    """
    from src.pdf.mig_spec import JOBS

    ctl = ctx.ctl["mig"]
    template = Path(state["target"])
    stamp = next((s for s in ctl.stamps() if s.name == template.stem), None)
    fields = ctl.read_passport(state["photos"][0])
    ctx.note(f"Паспорт ўқилди: {fields.get('surname', '')} "
             f"{fields.get('name', '')}".strip())

    answers = state["answers"]
    wanted = str(answers.get("job") or "").strip().lower()
    jobs = tuple(key for key, label, _rule in JOBS
                 if wanted and wanted in label.lower())
    result = ctl.generate(
        template=template, stamp=stamp,
        series=str(answers.get("series") or ""),
        number=str(answers.get("number") or ""),
        visa=str(answers.get("visa") or ""),
        jobs=jobs,
        valid_from=answers.get("valid_from"),
        valid_to=answers.get("valid_to"),
        issued=str(answers.get("issued") or ""),
        code=str(answers.get("code") or ""),
        surname=fields.get("surname", ""), name=fields.get("name", ""),
        patronymic=fields.get("patronymic", ""),
        birth_date=ctl.parse_date(fields.get("birth_date", "")),
        citizenship=fields.get("citizenship", ""),
        passport=fields.get("passport", ""),
        gender=fields.get("gender", ""))
    if stamp is None:
        ctx.note("⚠️ Бу бланка номи билан печат йўқ — карта печатсиз чиқди.")
    return [result.saved]


# ---------------------------------------------------------------- catalogue

_TRIO_LABELS = ("Паспорт", "Патент (олд)", "Патент (орқа)")
_TRIO_PROMPT = ("Расмларни ТАРТИБ билан юборинг:\n"
                "1️⃣ Паспорт\n2️⃣ Патент (олд)\n3️⃣ Патент (орқа)")

#: The cards that carry the worker's own photograph.
_PORTRAIT_LABELS = ("Паспорт", "Ишчи расми")
_PORTRAIT_PROMPT = "Иккита расм: 1️⃣ Паспорт  2️⃣ Ишчининг расми"

#: БЕЙДЖИК and ПАТЕНТ are one and the same card, so they ask the same things.
_BADGE_ASKS: tuple[Ask, ...] = (
    Ask("region", "Шаблон/регион (77 — Москва, 50 — область):", kind="text"),
    Ask("personal_number", "Шахсий номер:", kind="text"),
    Ask("inn", "ИНН рақами:", kind="text"),
    Ask("firm", "Фирма (кем выдано):", kind="text"),
    Ask("dolzhnost", "Должность (фақат 50 учун, керак бўлмаса «-»):", kind="text"),
    Ask("territory", "Территория действия патента (бўш — регионники):",
        kind="text"),
    Ask("issue_date", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0),
)

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
                     default_days=90),),
           add_key="reg_addr", add_prompt="➕ Янги манзил қўшиш"),
    # Reached from «🏠 Регистрация» («➕ Янги манзил қўшиш»), and offered on its
    # own too. Ten questions — the same table the computer's dialog asks for —
    # and the template is built from the blank, as it is there.
    Module("reg_addr", "🏠➕ Янги манзил", _run_reg_addr,
           text_only=True, needs_ai=False,
           asks=(Ask("label", "Номи (рўйхатда кўринади, масалан ПАРКОВАЯ 55):",
                     kind="text"),
                 Ask("oblast", "1 · Область (масалан Г МОСКВА):", kind="text"),
                 Ask("raion", "2 · Район (керак бўлмаса ўтказинг):", kind="text"),
                 Ask("gorod", "3 · Город (населенный пункт):", kind="text"),
                 Ask("ulitsa", "4 · Улица:", kind="text"),
                 Ask("dom", "5 · Дом:", kind="text"),
                 Ask("korpus", "6 · Корпус (бўш бўлса ўтказинг):", kind="text"),
                 Ask("stroenie", "7 · Строение (бўш бўлса ўтказинг):", kind="text"),
                 Ask("kvartira", "8 · Квартира:", kind="text"),
                 Ask("host_fio", "9 · Хозяин / Владелец (ФИО):", kind="text"),
                 Ask("regional_number", "10 · Региональный номер (02/770-…):",
                     kind="text"))),
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
           asks=(Ask("form_date", "Ҳужжат санаси (КК.ОО.ЙЙЙЙ):", default_days=0),
                 Ask("profession", "Должность (бўш — патентдагиси):",
                     kind="text"))),
    Module("dms", "🏥 ДМС", _run_dms,
           photo_prompt="Ишчининг паспорт расмини юборинг.",
           photo_labels=("Паспорт",),
           asks=(Ask("start_date", "Полис БОШЛАНИШ санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("phone", "Телефон рақами:", kind="text"),
                 Ask("address", "Рўйхатдан ўтиш манзили:", kind="text"),
                 Ask("region", "Патент ҳудуди (бўш — Москва):", kind="text"))),
    Module("insurance", "🚗 СТРАХОВКА", _run_insurance,
           targets=lambda c: c["insurance"].templates(),
           target_prompt="Страховая компания шаблонини танланг:",
           photo_prompt=("Расмларни ТАРТИБ билан юборинг:\n"
                         "1️⃣ СТС (олд)\n2️⃣ СТС (орқа)\n"
                         "3️⃣…6️⃣ Права — 4 тагача (ихтиёрий)\n\n"
                         "Права юборилмаса «без ограничения», юборилса "
                         "«лица, допущенные к управлению» белгиланади."),
           photo_labels=("СТС (олд)", "СТС (орқа)", "Права 1", "Права 2",
                         "Права 3", "Права 4"),
           asks=(Ask("start", "Страховка БОШЛАНИШ санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=0),)),
    Module("shablon", "📐 ЎЗ ШАБЛОНИМ", _run_shablon,
           targets=lambda c: c["template"].saved_templates(),
           target_prompt="Шаблонни танланг:",
           photo_prompt=("Расмларни ТАРТИБ билан юборинг:\n"
                         "1️⃣ Паспорт\n2️⃣ Патент (ихтиёрий)"),
           photo_labels=("Паспорт", "Патент"),
           asks=(Ask("form_date", "Ҳужжат санаси (КК.ОО.ЙЙЙЙ):", default_days=0),
                 Ask("profession", "Профессия (ихтиёрий):", kind="text"))),
    Module("chek", "🧾 ЧЕК", _run_chek,
           ready=lambda c: "" if c["chek"].company_id() else (
               "ЧЕК учун компания коди керак — у ҳар сафар ўйлаб "
               "топилмайди. Компютерда ЧЕК бўлимига кириб бир марта "
               "ёзиб қўйинг, кейин ботдан ишлатаверасиз."),
           photo_prompt="Ишчининг ПАТЕНТИ расмини юборинг.",
           photo_labels=("Патент",),
           asks=(Ask("summa", "Сумма (₽) — масалан 15000,50:", kind="text"),
                 Ask("card4", "Карта рақамининг охирги 4 таси:", kind="text"),
                 Ask("avtoriz", "Код авторизации — банк квитанциясидан "
                     "кўчириб ёзинг (6 та рақам):", kind="text"),
                 Ask("when_date", "Тўлов куни (КК.ОО.ЙЙЙЙ):", default_days=0),
                 Ask("when_time", "Тўлов соати (СС:ДД:СС, бўш — ҳозир):",
                     kind="text"))),
    Module("inn", "🔢 ИНН", _run_inn,
           photo_prompt="Ишчининг паспорти ёки патенти расмини юборинг.",
           photo_labels=("Паспорт/патент",),
           asks=(Ask("inn", "ИНН рақами (12 та рақам):", kind="text"),
                 Ask("form_date", "Кун (КК.ОО.ЙЙЙЙ):", default_days=0))),
    Module("beydjik", "🪪 БЕЙДЖИК", _run_beydjik,
           photo_prompt=_PORTRAIT_PROMPT, photo_labels=_PORTRAIT_LABELS,
           min_photos=2, asks=_BADGE_ASKS),
    # NB: the key «patent» already belongs to «🛂 Патент PDF» (Process Employee)
    Module("patent_card", "🩷 ПАТЕНТ", _run_patent_card,
           photo_prompt=_PORTRAIT_PROMPT, photo_labels=_PORTRAIT_LABELS,
           min_photos=2, asks=_BADGE_ASKS),
    Module("razreshenie", "🟩 РАЗРЕШЕНИЯ", _run_razreshenie,
           photo_prompt=_PORTRAIT_PROMPT, photo_labels=_PORTRAIT_LABELS,
           min_photos=2,
           asks=(Ask("activity", "Должность (вид деятельности):", kind="text"),
                 Ask("valid_from", "Бошланиш санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("inn", "Ишчининг ИННси (бўш — фақат паспорт рақами):",
                     kind="text"),
                 Ask("firm_name", "Фирма номи (бўш — охиргиси):", kind="text"),
                 Ask("firm_inn", "Фирма ИННси (бўш — охиргиси):", kind="text"))),
    Module("ppu", "🧾 ППУ", _run_ppu,
           targets=lambda c: c["ppu"].templates(),
           target_prompt="ППУ бланкасини танланг:",
           photo_prompt=("Иккита расм: 1️⃣ Ишчининг РЕГИСТРАЦИЯСИ "
                         "2️⃣ Ишчининг расми\n\nҚолган ҳамма нарса "
                         "регистрациядан ўқилади."),
           photo_labels=("Регистрация", "Ишчи расми"), min_photos=2,
           asks=(Ask("valid_from", "ППУ БОШЛАНИШ санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("valid_to_text", "Тугаш санаси (бўш — регистрациядан "
                     "олинади):", kind="text"))),
    Module("snils", "🔖 СНИЛС", _run_snils,
           targets=lambda c: c["snils"].templates(),
           target_prompt="СНИЛС бланкасини танланг:",
           photo_prompt="Ишчининг ПАСПОРТИ расмини юборинг.",
           photo_labels=("Паспорт",),
           asks=(Ask("reg_date", "Рўйхатга олинган сана (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("snils", "СНИЛС рақами (бўш — охиргиси):", kind="text"))),
    Module("sertifikat", "📜 СЕРТИФИКАТ", _run_sertifikat,
           photo_prompt="Ўқувчининг ПАСПОРТИ расмини юборинг.",
           photo_labels=("Паспорт",),
           asks=(Ask("city", "Город (Москва / Московская область):", kind="text"),
                 Ask("issued_on", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0))),
    Module("svera", "🎓 СФЕРА", _run_svera,
           targets=lambda c: c["svera"].professions(),
           target_prompt="Касбни танланг:",
           photo_prompt="Иккита расм: 1️⃣ Паспорт  2️⃣ Ишчининг расми",
           photo_labels=("Паспорт", "Ишчи расми"), min_photos=2,
           asks=(Ask("issue_date", "Бериш санаси (КК.ОО.ЙЙЙЙ):", default_days=0),)),
    Module("qrreg", "🔳 КРКОД РЕГ", _run_qrreg,
           targets=lambda c: c["qrreg"].templates(),
           target_prompt="Бланкани танланг:",
           photo_prompt="Иккита расм: паспорт, кейин патент (русча ФИО).",
           photo_labels=("Паспорт", "Патент"),
           asks=(Ask("valid_from", "Бошланиш санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("valid_to", "Тугаш санаси (КК.ОО.ЙЙЙЙ):",
                     default_days=90))),
    Module("alpinist", "🧗 АЛПИНИСТ", _run_alpinist,
           targets=lambda c: c["alpinist"].templates(),
           target_prompt="Бланкани танланг:",
           photo_prompt="Расмлар: 1️⃣ Паспорт  2️⃣ Ишчи расми  3️⃣ Имзо (оқ "
                        "қоғозга қўйилиб, расмга олинган)  4️⃣ Патент "
                        "(ихтиёрий, русча ФИО учун)",
           photo_labels=("Паспорт", "Ишчи расми", "Имзо", "Патент"),
           min_photos=3,
           asks=(Ask("issue_date", "Берилган сана (КК.ОО.ЙЙЙЙ) — тугаши "
                     "ўзи +3 йил:", default_days=0),
                 Ask("ud_number", "УДОСТОВЕРЕНИЕ № (1-саҳифа):",
                     kind="text"))),
    Module("imgbb", "🖼 IMGBB", _run_imgbb,
           photo_prompt="Расмни юборинг — прямой ҳавола ва QR қайтади.",
           photo_labels=("Расм",),
           needs_ai=False,
           ready=lambda c: (
               "" if c["imgbb"].key()
               else "imgbb API калити йўқ — компютерда Sozlamalar'даги "
                    "«🔳 КРКОД РЕГ — imgbb» картасига киритинг.")),
    Module("spr3", "📄 3-СПРАВКА", _run_spr3,
           targets=lambda c: c["spr3"].templates(),
           target_prompt="Фирманинг бланкасини танланг:",
           photo_prompt="Иккита расм: паспорт, кейин русча ФИО ҳужжати "
                        "(патент ёки миг карта).",
           photo_labels=("Паспорт", "Русча ФИО ҳужжати"),
           asks=(Ask("valid_from", "Бошланиш санаси (КК.ОО.ЙЙЙЙ) — тугаши "
                     "ўзи 1 йил -1 кун ҳисобланади:", default_days=0),
                 Ask("num3", "3-саҳифа № (бўлмаса «Тайёрла»):", kind="text"),
                 Ask("ser3", "3-саҳифа серия:", kind="text"),
                 Ask("num5", "5-саҳифа №:", kind="text"),
                 Ask("oblast", "Область:", kind="text"),
                 Ask("gorod", "Город:", kind="text"),
                 Ask("ulitsa", "Улица:", kind="text"),
                 Ask("dom", "Дом:", kind="text"),
                 Ask("korpus", "Корпус:", kind="text"),
                 Ask("kvartira", "Квартира:", kind="text"))),
    Module("mvd_trud", "📮 МВД ТРУДАВОЙ", _run_mvd_trud,
           # both regions' blanks in one list; the runner tells them apart by
           # where the picked one lives
           targets=lambda c: c["mvd_trud"].all_templates(),
           target_prompt="Фирманинг бланкасини танланг:",
           photo_prompt="Учта расм: паспорт, патент олди, патент орқаси.",
           photo_labels=("Паспорт", "Патент олди", "Патент орқаси"),
           min_photos=2,
           asks=(Ask("deal_date", "Сана (КК.ОО.ЙЙЙЙ):", default_days=0),
                 Ask("profession", "Должность (бўш — патентдагиси):",
                     kind="text"),
                 Ask("uved_no", "Уведомление № (бўлмаса «Тайёрла»):",
                     kind="text"),
                 Ask("spravka_no", "Справка № (бўлмаса «Тайёрла»):",
                     kind="text"))),
    Module("rusreg", "🇷🇺 РУС РЕГ", _run_rusreg,
           targets=lambda c: c["rusreg"].templates(),
           target_prompt="Фирманинг бланкасини танланг:",
           photo_prompt="Паспорт РФ ёки метрка (свидетельство о рождении) "
                        "расмини юборинг.",
           photo_labels=("Ҳужжат",),
           asks=(Ask("doc_kind", "Ҳужжат тури:", kind="choice",
                     choices=("ПАСПОРТ РФ", "МЕТРКА")),
                 Ask("valid_from", "Срок БОШЛАНИШИ (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("valid_to", "Срок ТУГАШИ (КК.ОО.ЙЙЙЙ):", default_days=90),
                 Ask("reg_number", "Регистрация № (бўш — охиргиси):",
                     kind="text"),
                 Ask("address", "Адрес (бўш — охиргиси):", kind="text"),
                 Ask("firm", "Фирма (бўш — охиргиси):", kind="text"))),
    Module("mig", "🪪 МИГ — ИШЧИ КАРТАСИ", _run_mig,
           targets=lambda c: c["mig"].templates(),
           target_prompt="Фирманинг бланкасини танланг:",
           photo_prompt="Ишчининг ПАСПОРТ расмини юборинг.",
           photo_labels=("Паспорт",),
           asks=(Ask("series", "Карта СЕРИЯ (масалан 46 26):", kind="text"),
                 Ask("number", "Карта НОМЕР (масалан 0367598):", kind="text"),
                 Ask("visa", "ВИЗА № (бўлмаса «Тайёрла» босинг):", kind="text"),
                 Ask("job", "Иш ўрни — рақамини ёзинг:", kind="choice",
                     choices=("КОМ АДМИНИСТРАТОР", "УЧЕНИК", "РАЗНОРАБОЧИЙ",
                              "ЧАСТНЫЙ ИШЧИ.")),
                 Ask("valid_from", "Карта амал қилиш БОШЛАНИШИ (КК.ОО.ЙЙЙЙ):",
                     default_days=0),
                 Ask("valid_to", "Карта амал қилиш ТУГАШИ (КК.ОО.ЙЙЙЙ):",
                     default_days=90),
                 Ask("issued", "Карта берилган сана — нуқтасиз, «15  03  26»:",
                     kind="text"),
                 Ask("code", "КОД — сананинг 4 бурчагига ёзиладиган 3–4 хонали "
                     "рақам (бўлмаса «Тайёрла»):", kind="text"))),
    Module("perevod", "🌐 ПЕРЕВОД", _run_perevod,
           photo_prompt=("Таржима қилинадиган ҳужжат расмларини юборинг.\n"
                         "(олди-орқаси бўлса иккисини — битта варақга "
                         "устма-уст, ҳақиқий ўлчамида қўйилади)"),
           add_key="perevod_blank", add_prompt="➕ Бланка юклаш (1/2/3)"),
    # The three sheets the office prints its translations on. Uploadable from
    # the phone as well as the computer — the same AppData folder, so whichever
    # one it is done on, the other sees it at once.
    Module("perevod_blank", "🌐➕ ПЕРЕВОД бланкаси", _run_perevod_blank,
           needs_ai=False,
           targets=lambda _c: list(PEREVOD_SHEETS),
           target_prompt="Қайси саҳифанинг бланкаси?",
           photo_prompt=("Бўш бланкани юборинг — PDF ёки расм.\n"
                         "Битта файл, шу саҳифанинг ўрнига қўйилади."),
           photo_labels=("Бланка",), min_photos=0, accepts_pdf=True),
    Module("trud_ppu", "🧷 ТРУД ППУ", _run_trud_ppu,
           targets=lambda c: c["trud_ppu"].templates(),
           target_prompt="ТРУД ППУ бланкасини танланг (2–3 саҳифа):",
           photo_prompt=("Аввал ИККИТА PDF, тартиб билан:\n"
                         "1️⃣ ТРУДОВОЙ договор\n2️⃣ УВЕДОМЛЕНИЯ\n\n"
                         "Кейин расмлар:\n1️⃣ Патент (олд)\n2️⃣ Патент (орқа)\n"
                         "3️⃣ Ишчининг расми (ихтиёрий)\n\n"
                         "1-саҳифа ППУ бўлимидаги биринчи олд бланкага босилади."),
           photo_labels=("Патент (олд)", "Патент (орқа)", "Ишчи расми"),
           min_photos=2, wants_pdf=2),
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
    from src.config.settings_service import SettingsService
    from src.controllers.alpinist_controller import AlpinistController
    from src.controllers.beydjik_controller import BeydjikController
    from src.controllers.chek_controller import ChekController
    from src.controllers.dms_controller import DmsController
    from src.controllers.hostel_controller import HostelController
    from src.controllers.imgbb_controller import ImgbbController
    from src.controllers.inn_controller import InnController
    from src.controllers.mig_controller import MigController
    from src.controllers.mvd_trud_controller import MvdTrudController
    from src.controllers.osago_controller import OsagoController
    from src.controllers.patent_controller import PatentController
    from src.controllers.ppu_controller import PpuController
    from src.controllers.process_controller import ProcessController
    from src.controllers.qrreg_controller import QrRegController
    from src.controllers.razreshenie_controller import RazreshenieController
    from src.controllers.registration_controller import RegistrationController
    from src.controllers.rusreg_controller import RusRegController
    from src.controllers.sertifikat_controller import SertifikatController
    from src.controllers.snils_controller import SnilsController
    from src.controllers.spr3_controller import Spr3Controller
    from src.controllers.svera_controller import SveraController
    from src.controllers.template_controller import TemplateController
    from src.controllers.trud8_controller import Trud8Controller
    from src.controllers.trud_ppu_controller import TrudPpuController
    from src.database.repositories.template_profile_repo import (
        TemplateProfileRepository,
    )
    from src.ocr.service import OcrService
    from src.services.alpinist_service import AlpinistService
    from src.services.beydjik_service import BeydjikService
    from src.services.company_service import CompanyService
    from src.services.dms_service import DmsService
    from src.services.dover_service import DoverService
    from src.services.generation_service import GenerationService
    from src.services.hostel_service import HostelService
    from src.services.inn_service import InnService
    from src.services.mig_service import MigService
    from src.services.mvd_trud_service import MvdTrudService
    from src.services.osago_service import OsagoService
    from src.services.patent_service import PatentService
    from src.services.perevod_service import PerevodService
    from src.services.photo_service import PhotoService
    from src.services.ppu_service import PpuService
    from src.services.profession_service import ProfessionService
    from src.services.qrreg_service import QrRegService
    from src.services.razreshenie_service import RazreshenieService
    from src.services.registration_address_service import RegistrationAddressService
    from src.services.registration_service import RegistrationService
    from src.services.rusreg_service import RusRegService
    from src.services.sertifikat_service import SertifikatService
    from src.services.snils_service import SnilsService
    from src.services.spr3_service import Spr3Service
    from src.services.svera_service import SveraService
    from src.services.trud8_service import Trud8Service
    from src.services.trud_ppu_service import TrudPpuService
    from src.services.umumiy_service import UmumiyService

    ocr = container.resolve(OcrService)
    return {
        "process": ProcessController(
            container.resolve(CompanyService), ocr,
            container.resolve(GenerationService)),
        "reg": RegistrationController(
            container.resolve(RegistrationAddressService), ocr,
            container.resolve(RegistrationService)),
        # the address book itself, so a new address can be added from the phone
        "reg_addr": container.resolve(RegistrationAddressService),
        # ТРУД ППУ prints sheet 1 on the ППУ front blank, so it needs the ППУ
        # template list even though ППУ itself is not offered on the phone
        "qrreg": QrRegController(
            ocr, QrRegService(container.resolve(SettingsService))),
        "alpinist": AlpinistController(
            ocr, AlpinistService(container.resolve(SettingsService))),
        "imgbb": ImgbbController(container.resolve(SettingsService)),
        "spr3": Spr3Controller(
            ocr, Spr3Service(container.resolve(SettingsService))),
        "mvd_trud": MvdTrudController(
            ocr, MvdTrudService(container.resolve(SettingsService))),
        "rusreg": RusRegController(
            ocr, RusRegService(container.resolve(SettingsService))),
        "mig": MigController(
            ocr, MigService(container.resolve(SettingsService))),
        "ppu": PpuController(
            ocr, PpuService(container.resolve(SettingsService))),
        "trud_ppu": TrudPpuController(
            ocr, TrudPpuService(container.resolve(SettingsService)),
            key_getter=key_getter),
        # HostelService is stateless and not container-registered (the desktop
        # view builds it the same way).
        "hostel": HostelController(
            container.resolve(RegistrationAddressService), ocr, HostelService()),
        "trud": Trud8Controller(
            ocr, Trud8Service(container.resolve(SettingsService))),
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
        "chek": ChekController(ocr, container.resolve(SettingsService)),
        # ПАТЕНТ is the badge on a different blank — same controller family.
        "patent": PatentController(
            ocr, PatentService(container.resolve(SettingsService))),
        "razreshenie": RazreshenieController(
            ocr, RazreshenieService(container.resolve(SettingsService))),
        "sertifikat": SertifikatController(
            ocr, SertifikatService(container.resolve(SettingsService))),
        "snils": SnilsController(
            ocr, SnilsService(container.resolve(SettingsService))),
        # СТРАХОВКА and ЎЗ ШАБЛОНИМ own their services the same way the desktop
        # views do.
        "insurance": OsagoController(
            ocr, OsagoService(container.resolve(SettingsService))),
        "template": TemplateController(
            container.resolve(TemplateProfileRepository), ocr),
        "umumiy": UmumiyService(key_getter=key_getter),
        "dover": DoverService(key_getter=key_getter,
                              settings=container.resolve(SettingsService)),
        "photo": PhotoService(key_getter=key_getter),
        "ocr": ocr,
    }
