"""OCR service: read passport + patent images into validated domain models.

It orchestrates the provider (via AiManager) and normalization, and never knows
which provider ran. Output is a validated (Passport, Patent) pair the controller
assembles into an Employee with the operator-chosen company, date and должность.
"""

from __future__ import annotations

import re
from datetime import date

from src.ai.manager import AiManager
from src.ai.prompts import (
    inn_prompt,
    named_fields_prompt,
    patent_back_prompt,
    prompt_for,
)
from src.common.logging import get_logger
from src.domain.document_number import strip_document_check_digit
from src.domain.documents import Passport, Patent
from src.domain.enums import DocType, Gender
from src.domain.passport_rules import same_name, series_in_latin
from src.domain.vehicle import DriverLicence, Sts
from src.ocr.preprocess import prepare_image
from src.ocr.translit import to_cyrillic, translate_issuer

log = get_logger(__name__)


def _parse_gender(value: str) -> Gender | None:
    v = (value or "").strip().lower()
    if v in ("male", "m", "муж", "мужской", "erkak"):
        return Gender.MALE
    if v in ("female", "f", "жен", "женский", "ayol"):
        return Gender.FEMALE
    return None


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


#: A twelve-digit run standing on its own — not part of a longer number.
#:
#: The guards on both sides are the whole trick. A патент prints the passport
#: and the ИНН on one line, «FB0717527 / 072501692992», and a reader will often
#: hand that line back whole. Pulling every digit out of it and joining them
#: gives a nineteen-digit number that is nobody's. Matching a *bounded* run
#: instead finds the ИНН inside the line and leaves the passport's seven digits
#: alone — and a run of nineteen glued digits matches nothing at all, which is
#: the right answer for a reading that has already lost the boundary.
_TWELVE_DIGITS = re.compile(r"(?<!\d)(\d{12})(?!\d)")


#: Nothing but the number and its own label — «ИНН 77 23 65 21 54 25».
_LABEL_AND_DIGITS = re.compile(r"^(?:ИНН|INN)?[\s:№.-]*([\d\s-]{12,20})$",
                               re.IGNORECASE)


def twelve_digit_inn(text: str) -> str:
    """The one twelve-digit number in ``text``, or "" if it is not unambiguous.

    Leading zeros are kept: a Russian individual's ИНН very often starts with
    one, and «072501692992» is not «72501692992».
    """
    text = (text or "").strip()
    found = list(dict.fromkeys(_TWELVE_DIGITS.findall(text)))
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        log.info("ИНН аниқ эмас — %d та 12 хонали рақам топилди", len(found))
        return ""

    # A number typed in groups — «77 23 65 21 54 25» — has no bounded run of
    # twelve. Closing the gaps is only safe when the answer holds NOTHING else:
    # the moment a letter or a second number is in there, the gaps might be the
    # boundary between two different numbers, which is exactly how «FB0717527 /
    # 072501692992» turns into a nineteen-digit number belonging to nobody.
    grouped = _LABEL_AND_DIGITS.match(text)
    if grouped:
        digits = re.sub(r"\D", "", grouped.group(1))
        if len(digits) == 12:
            return digits
    return ""


def _clean_document(series: str, number: str) -> tuple[str, str]:
    """Series and number with the trailing check digit taken back off.

    The model very often reads them off the strip at the foot of the page,
    where the nine document characters are followed by their check digit —
    «FB2254876» comes back as «FB22548766», one digit too many, and that
    wrong number then goes onto a registration. Removed only when the
    arithmetic proves it (:func:`strip_document_check_digit`).
    """
    packed = "".join((series or "").split()) + "".join((number or "").split())
    cleaned = strip_document_check_digit(packed)
    if cleaned == packed.upper():
        return series, number          # nothing proven — leave as printed
    match = re.fullmatch(r"([A-Z]{1,3})(\d+)", cleaned)
    if match:
        return match.group(1), match.group(2)
    return "", cleaned


def _mangled_name(patronymic: str, name: str) -> bool:
    """An «отчество» that is really the given name, misread.

    The Philippine passport gave «ДЖЕЛИН» as the patronymic of «ДЖОСЕЛИН» —
    the model had mangled the given name into a second field, and the invented
    отчество went onto a registration. A real patronymic comes from the
    FATHER's name and never resembles the worker's own; near-duplicates are
    dropped.
    """
    a = "".join((patronymic or "").upper().split())
    b = "".join((name or "").upper().split())
    if not a or not b:
        return False
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio() >= 0.7


#: A name as a passport prints it in Latin — letters (including the
#: republics' own Ə Ğ Ş Ç Ž Ö Ü İ), the okina and the hyphen of a double
#: surname, nothing else. Anything carrying a digit, a «<» of the machine
#: strip or a stray mark is a misreading and is not used.
_LATIN_LETTER = "A-Za-zÀ-ÖØ-öø-ſ"
_PRINTED_LATIN = re.compile(f"[{_LATIN_LETTER}][{_LATIN_LETTER}'ʻʼ‘’`´\\- ]*")


def _russian_name(said: str, printed: str, country: str) -> str:
    """The worker's name in Russian letters, by the rules and not by guess.

    A passport does not print a Russian spelling: it prints the name in
    Latin, and the Russian one has to be TRANSLITERATED from it. The model
    is asked for both, and when the Latin row came back cleanly it is the
    Latin that decides — the table in :mod:`src.ocr.translit` is the same
    practical transcription the patents are typed by, so «KAKHOROV» is
    КАХОРОВ every time. A model writing the Cyrillic freehand is a guess,
    and a guess dropped the Х out of that very name.

    Only when there is no usable Latin does the model's own Cyrillic stand.
    """
    printed = (printed or "").strip()
    if printed and _PRINTED_LATIN.fullmatch(printed):
        by_rule = to_cyrillic(printed, country)
        said_now = to_cyrillic(said or "", country)
        if by_rule and by_rule != said_now:
            log.info("исм қоида бўйича ёзилди: «%s» → «%s» (AI «%s» деган эди)",
                     printed, by_rule, said_now)
        return by_rule
    return to_cyrillic(said or "", country)


def _passport_from(f: dict[str, str]) -> Passport:
    """The passport as the page prints it, in the letters a Russian form needs."""
    series, number = _clean_document(f.get("series", ""), f.get("number", ""))
    # the citizenship decides one letter — a Tajik Jamshed is ДЖАМШЕД
    # where an Uzbek Jasur is ЖАСУР — so it is read first and passed on
    country = to_cyrillic(f.get("nationality", ""))
    surname = _russian_name(f.get("surname", ""), f.get("surname_latin", ""),
                            country)
    name = _russian_name(f.get("name", ""), f.get("name_latin", ""), country)
    patronymic = _russian_name(f.get("patronymic", ""),
                               f.get("patronymic_latin", ""), country)
    if _mangled_name(patronymic, name):
        log.info("отчество «%s» исмнинг ўзи — ташлаб юборилди", patronymic)
        patronymic = ""
    return Passport(
        surname=surname,
        name=name,
        patronymic=patronymic or None,
        nationality=country or None,
        gender=_parse_gender(f.get("gender", "")),
        series=series or None,  # series/number stay as printed otherwise
        number=number,
        birth_date=_parse_date(f.get("birth_date", "")),
        birth_place=to_cyrillic(f.get("birth_place", ""), country) or None,
        issue_date=_parse_date(f.get("issue_date", "")),
        expiry_date=_parse_date(f.get("expiry_date", "")),
        issued_by=to_cyrillic(translate_issuer(f.get("issued_by", ""))) or None,
        surname_latin=_latin(f.get("surname_latin", "")),
        name_latin=_latin(f.get("name_latin", "")),
        patronymic_latin=_latin(f.get("patronymic_latin", "")),
    )


def _latin(value: str) -> str:
    """The printed Latin row, kept only when it read as one."""
    text = (value or "").strip()
    return text if text and _PRINTED_LATIN.fullmatch(text) else ""


class OcrService:
    def __init__(self, ai: AiManager) -> None:
        self._ai = ai

    @property
    def ai(self) -> AiManager:
        """The provider stack, for callers that read something other than a
        passport — the уведомление blank study, for instance."""
        return self._ai

    def available(self) -> bool:
        return self._ai.available()

    def read_passport(self, image: bytes) -> Passport:
        """The passport's printed page, read as printed.

        The strip of «<<<» at the foot of the page is NOT used. It used to
        be: its check digits are arithmetic, so when they added up its
        values were taken over the model's. But it carries no patronymic,
        no issuing office and no birth place, its own reading is what the
        model made of two crowded lines, and when the arithmetic failed the
        operator got a warning about a document that was perfectly fine.
        The office asked for it to go, and it is gone — the printed rows
        are the source, and the Latin row rules the Russian spelling.
        """
        image = prepare_image(image)
        answer = self._ai.extract(image, DocType.PASSPORT, prompt_for(DocType.PASSPORT))
        return _passport_from(answer.fields)

    def read_patent(self, front: bytes, back: bytes | None = None) -> Patent:
        """Read the patent. The FRONT gives серия/номер/профессия; the BACK (if
        supplied) gives дата выдачи + кем выдан — which is where they are printed.
        """
        front = prepare_image(front)
        f = self._ai.extract(front, DocType.PATENT, prompt_for(DocType.PATENT)).fields
        issue_date = _parse_date(f.get("issue_date", ""))
        issued_by = f.get("issued_by") or None
        blank_series = f.get("blank_series") or None
        blank_number = f.get("blank_number") or None
        if back is not None:
            b = self._ai.extract(prepare_image(back), DocType.PATENT, patent_back_prompt()).fields
            issue_date = _parse_date(b.get("issue_date", "")) or issue_date
            issued_by = (b.get("issued_by") or "").strip() or issued_by
            # the blank «ПР 8074980» is printed on the back bottom — prefer it
            blank_series = (b.get("blank_series") or "").strip() or blank_series
            blank_number = (b.get("blank_number") or "").strip() or blank_number
        country = to_cyrillic(f.get("citizenship", ""))
        return Patent(
            series=f.get("series") or None,
            number=f.get("number", ""),
            blank_series=to_cyrillic(blank_series or "") or None,
            blank_number=blank_number,
            issue_date=issue_date,
            issued_by=to_cyrillic(issued_by or "") or None,
            profession=to_cyrillic(f.get("profession", "")) or "ПОДСОБНЫЙ РАБОЧИЙ",
            holder_surname=to_cyrillic(f.get("surname", ""), country) or None,
            holder_name=to_cyrillic(f.get("name", ""), country) or None,
            holder_patronymic=to_cyrillic(f.get("patronymic", ""), country)
            or None,
            holder_citizenship=country or None,
        )

    def read_named(self, images: list[bytes],
                   names: list[str]) -> dict[str, str]:
        """Whatever the office asked for, by the name it gave it.

        The УНИВЕРСАЛ section lets the office invent its own boxes — «Патентни
        ИНН рақами», «Виза №», «Номер зачисления» — and no prompt can be
        written in advance for names nobody has thought of yet. So the names
        ARE the request, and every page dropped is asked the same question.

        The first page that answers a name wins; the rest are only asked what
        is still missing, which keeps a passport from being asked about a visa
        it has never heard of. Nothing found stays empty for the office to
        type, and an unreadable page costs nothing but its turn.
        """
        wanted = [" ".join(str(n).split()) for n in names if str(n).strip()]
        found: dict[str, str] = {name: "" for name in wanted}
        if not wanted or not images:
            return found

        for image in images:
            missing = [name for name in wanted if not found[name]]
            if not missing:
                break
            try:
                # UNKNOWN maps to the free-form schema: the answer's keys are
                # the office's own words, which no document schema knows.
                answer = self._ai.extract(prepare_image(image),
                                          DocType.UNKNOWN,
                                          named_fields_prompt(missing))
            except Exception as exc:        # noqa: BLE001 - reading is optional
                log.info("УНИВЕРСАЛ: майдонлар ўқилмади — %s", exc)
                continue
            for name in missing:
                said = " ".join(str(answer.fields.get(name, "") or "").split())
                if said:
                    found[name] = said
        log.info("УНИВЕРСАЛ: %d сўралди, %d топилди",
                 len(wanted), sum(1 for v in found.values() if v))
        return found

    def read_inn(self, image: bytes) -> str:
        """The individual's twelve-digit ИНН off a патент — or "" if it is not there.

        Twelve digits and nothing else is accepted. A patent is covered in
        numbers — its own серия and номер, the issuing office's ten-digit ИНН,
        its thirteen-digit ОГРН — and a reader having a bad day will happily
        offer one of those. Anything that is not exactly twelve digits is
        dropped on the floor and the operator types the number themselves,
        which is the right way round: a blank box is a question, a wrong ИНН is
        a form filed against the wrong person.
        """
        try:
            # UNKNOWN, deliberately: every answer is validated against the
            # schema for its DocType, and PATENT demands the card's own fields
            # — номер, фамилия, бланк. This request asks for one number and
            # gets one number back, so under PATENT the answer was thrown away
            # as «жавобда керакли майдонлар йўқ» before it was ever read.
            # UNKNOWN maps to the free-form schema, which requires nothing.
            answer = self._ai.extract(prepare_image(image), DocType.UNKNOWN,
                                      inn_prompt())
        except Exception as exc:            # noqa: BLE001 - reading is optional here
            log.info("ИНН ўқилмади: %s", exc)
            return ""
        fields = answer.fields
        # In order: the reader's own answer, then the whole «Документ удост.
        # личность/ИНН» line it was asked to copy, then anything else it
        # returned, then its transcript. Every one of them goes through the
        # same bounded rule, so a stray passport, ОГРН or patent number cannot
        # get through at any step — only a clean, unambiguous twelve.
        sources = (str(fields.get("inn", "")), str(fields.get("line", "")),
                   " | ".join(str(v) for k, v in fields.items()
                              if k not in ("inn", "line")),
                   str(getattr(answer, "text", "") or ""))
        for source in sources:
            found = twelve_digit_inn(source)
            if found:
                return found
        log.info("ИНН топилмади. Ўқувчи қайтарган: %s",
                 {k: str(v)[:60] for k, v in fields.items()} or "—")
        return ""

    def read_pinfl(self, image: bytes, born: date | None = None) -> str:
        """The ПИНФЛ off the strip at the foot of an Uzbek passport, or "".

        The Uzbek certificates the office sends home name the worker by this
        number, and the passport prints it nowhere on its face — only in the
        machine-readable strip. So the reader is asked for the STRIP'S LINE,
        not for the number: the fourteen digits are cut out of it here, by
        arithmetic (:mod:`src.domain.pinfl`), and checked against the birth
        date the passport prints above it. Nothing comes back unless the two
        agree — a wrong ПИНФЛ on a certificate filed with the agency is far
        worse than an empty box the operator fills in from the passport.

        Free-form, like :meth:`read_inn`: this asks for two lines no document
        model has, so it must not be judged against one.
        """
        from src.ai.prompts import pinfl_prompt
        from src.domain.pinfl import pinfl_from_mrz

        try:
            answer = self._ai.extract(prepare_image(image), DocType.UNKNOWN,
                                      pinfl_prompt())
        except Exception as exc:          # noqa: BLE001 - reading is optional
            log.info("ПИНФЛ ўқилмади: %s", exc)
            return ""
        fields = answer.fields
        # the second line first, then the first — a reader that swapped them
        # still gets the number out, and a line that is not one cannot pass
        # the century-and-birth-date arithmetic
        for key in ("line2", "line1"):
            found = pinfl_from_mrz(str(fields.get(key, "")), born)
            if found:
                return found
        log.info("ПИНФЛ топилмади. Ўқувчи қайтарган: %s",
                 {k: str(v)[:60] for k, v in fields.items()} or "—")
        return ""

    def read_registration(self, image: bytes) -> dict[str, str]:
        """A регистрация read for the ППУ pair — plain strings, nothing invented.

        Free-form, like :meth:`read_inn`: this asks for a set of keys no
        document model has, so it must not be judged against one. Whatever
        cannot be read comes back empty and the operator types it — a guessed
        address or a guessed end date is worse than a blank box.
        """
        from src.ai.prompts import registration_prompt

        answer = self._ai.extract(prepare_image(image), DocType.UNKNOWN,
                                  registration_prompt())
        f = answer.fields
        series = series_in_latin(str(f.get("series", "")))
        number = str(f.get("number", "")).strip()
        return {
            "surname": to_cyrillic(str(f.get("surname", ""))).strip(),
            "name": to_cyrillic(str(f.get("name", ""))).strip(),
            "patronymic": to_cyrillic(str(f.get("patronymic", ""))).strip(),
            "birth_date": str(f.get("birth_date", "")).strip(),
            "gender": to_cyrillic(str(f.get("gender", ""))).strip(),
            "citizenship": to_cyrillic(str(f.get("citizenship", ""))).strip(),
            # the passport is an identifier: Latin as printed, never translated
            "document": " ".join(p for p in (series, number) if p),
            "address": str(f.get("address", "")).strip(),
            "stay_from": str(f.get("stay_from", "")).strip(),
            "stay_to": str(f.get("stay_to", "")).strip(),
        }

    def read_sts(self, front: bytes, back: bytes | None = None) -> Sts:
        """Read the vehicle registration card.

        The FRONT carries the plate, VIN, make and model; the BACK carries the
        owner and their address, so the two are merged with the back winning
        wherever it has something to say.
        """
        f = self._ai.extract(prepare_image(front), DocType.STS,
                             prompt_for(DocType.STS)).fields
        if back is not None:
            b = self._ai.extract(prepare_image(back), DocType.STS,
                                 prompt_for(DocType.STS)).fields
            f = {**f, **{k: v for k, v in b.items() if (v or "").strip()}}
        return Sts(
            series=f.get("series", ""), number=f.get("number", ""),
            # a plate is Cyrillic; a VIN and a make stay in Latin as printed
            plate=to_cyrillic(f.get("plate", "")),
            vin=(f.get("vin", "") or "").upper().replace(" ", ""),
            mark=f.get("mark", ""), model=f.get("model", ""),
            year=f.get("year", ""), category=f.get("category", ""),
            owner_fio=to_cyrillic(f.get("owner_fio", "")),
            owner_address=f.get("owner_address", ""),
            issue_date=_parse_date(f.get("issue_date", "")),
        )

    def read_licence(self, image: bytes) -> DriverLicence:
        """Read one driving licence — a person who will be allowed to drive."""
        f = self._ai.extract(prepare_image(image), DocType.DRIVER_LICENCE,
                             prompt_for(DocType.DRIVER_LICENCE)).fields
        return DriverLicence(
            surname=to_cyrillic(f.get("surname", "")),
            name=to_cyrillic(f.get("name", "")),
            patronymic=to_cyrillic(f.get("patronymic", "")),
            series=(f.get("series", "") or "").upper(),
            number=f.get("number", ""),
            birth_date=_parse_date(f.get("birth_date", "")),
            issue_date=_parse_date(f.get("issue_date", "")),
            expiry_date=_parse_date(f.get("expiry_date", "")),
            categories=(f.get("categories", "") or "").upper(),
        )

    def read_documents(
        self, passport_image: bytes, patent_front: bytes | None = None, patent_back: bytes | None = None
    ) -> tuple[Passport, Patent | None]:
        """Read passport + patent and return a consistent (Passport, Patent).

        Names come from the PATENT when it carries them (it prints ФИО in Russian,
        so it is reliable even for non-Cyrillic passports); the passport still
        supplies citizenship, birth date, series, number, issue date and issuer.
        """
        passport = self.read_passport(passport_image)
        patent = self.read_patent(patent_front, patent_back) if patent_front else None
        # written down every time: when a ФИО comes out wrong the office's
        # log has to say WHICH document it came off, and whether the two
        # documents agreed — otherwise the reading cannot be argued with
        log.info("ФИО — паспорт: «%s %s %s» | патент: «%s %s %s»",
                 passport.surname, passport.name, passport.patronymic or "—",
                 getattr(patent, "holder_surname", None) or "—",
                 getattr(patent, "holder_name", None) or "—",
                 getattr(patent, "holder_patronymic", None) or "—")
        if patent is not None and patent.holder_surname:
            passport = passport.model_copy(
                update={
                    "surname": _agreed(passport, "surname",
                                       patent.holder_surname),
                    "name": _agreed(passport, "name", patent.holder_name)
                    or passport.name,
                    # taken AS the patent says, absence included: the patent
                    # prints the full ФИО in Russian, so a patent with no
                    # patronymic means the worker HAS none — while the
                    # passport's value may be an invented one (a Philippine
                    # «middle name» is not an отчество, but models return it
                    # as one). Falling back re-introduced exactly that.
                    #
                    # Nor is it compared with the passport's, the way the
                    # surname is: a father's name is written one way on an
                    # Uzbek passport and another on a Russian patent —
                    # «ANVAROVICH» there, «Анвар угли» here — and both are
                    # the same father. Only the patent's form belongs on a
                    # Russian document.
                    "patronymic": patent.holder_patronymic or None,
                    "nationality": patent.holder_citizenship or passport.nationality,
                }
            )
        return passport, patent


def _agreed(passport: Passport, field: str, from_patent: str | None) -> str:
    """The patent's spelling of one name — unless it was plainly misread.

    The office's rule stands: the patent prints the ФИО in Russian and it
    is the name. But a patent is a small laminated card, often photographed
    badly, and «Кахоров» came back as «Какаров» from one such photograph
    while the passport's own Latin row read KAKHOROV perfectly.

    So the two are compared by :func:`same_name`: a vowel apart is two
    offices spelling one man and the PATENT wins, a consonant apart is a
    misreading and the passport's spelling — transliterated from machine
    print by a fixed table — wins. Without a Latin row there is nothing to
    prove, and the patent wins as before.
    """
    patent_says = (from_patent or "").strip()
    ours = (getattr(passport, field) or "").strip()
    if not patent_says or not ours:
        return patent_says
    if getattr(passport, f"{field}_latin", "") and \
            not same_name(ours, patent_says):
        log.info("«%s»: патент «%s» деб ўқилди, паспортда «%s» (лотинча "
                 "«%s») — паспортники олинди", field, patent_says, ours,
                 getattr(passport, f"{field}_latin"))
        return ours
    return patent_says
