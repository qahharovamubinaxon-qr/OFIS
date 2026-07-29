"""OCR service: read passport + patent images into validated domain models.

It orchestrates the provider (via AiManager) and normalization, and never knows
which provider ran. Output is a validated (Passport, Patent) pair the controller
assembles into an Employee with the operator-chosen company, date and должность.
"""

from __future__ import annotations

import re
from datetime import date

from src.ai.manager import AiManager
from src.ai.prompts import inn_prompt, patent_back_prompt, prompt_for
from src.common.logging import get_logger
from src.domain.documents import Passport, Patent
from src.domain.enums import DocType, Gender
from src.domain.passport_rules import series_in_latin
from src.domain.vehicle import DriverLicence, Sts
from src.ocr import mrz_reader
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


def _passport_from(f: dict[str, str]) -> Passport:
    """What the vision model said, before the MRZ gets a chance to correct it."""
    return Passport(
        surname=to_cyrillic(f.get("surname", "")),
        name=to_cyrillic(f.get("name", "")),
        patronymic=to_cyrillic(f.get("patronymic", "")) or None,
        nationality=to_cyrillic(f.get("nationality", "")) or None,
        gender=_parse_gender(f.get("gender", "")),
        series=f.get("series") or None,  # series/number stay as printed
        number=f.get("number", ""),
        birth_date=_parse_date(f.get("birth_date", "")),
        birth_place=to_cyrillic(f.get("birth_place", "")) or None,
        issue_date=_parse_date(f.get("issue_date", "")),
        expiry_date=_parse_date(f.get("expiry_date", "")),
        issued_by=to_cyrillic(translate_issuer(f.get("issued_by", ""))) or None,
    )


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
        image = prepare_image(image)
        answer = self._ai.extract(image, DocType.PASSPORT, prompt_for(DocType.PASSPORT))
        return self._with_mrz(_passport_from(answer.fields), answer)

    @staticmethod
    def _with_mrz(passport: Passport, answer) -> Passport:
        """Let the machine-readable zone correct the reading, when it proves itself.

        The zone's check digits are arithmetic: a misread character almost never
        adds up. So when they do add up its values win over the model's, and
        when they do not, nothing is changed and the passport carries a warning
        the operator can see — a quietly wrong passport number is far worse.
        """
        mrz = mrz_reader.read(answer.text,
                              line1=answer.fields.get("mrz_line1", ""),
                              line2=answer.fields.get("mrz_line2", ""))
        if not mrz.found:
            return passport
        if not mrz.valid:
            log.info("MRZ found but unverified: %s", "; ".join(mrz.problems))
            return passport.model_copy(update={
                "mrz_warning": "MRZ назорат рақами мос келмади ("
                               + ", ".join(mrz.problems) + ") — текшириб чиқинг"})

        update: dict[str, object] = {"mrz_checked": True}
        for key in ("surname", "name", "patronymic", "series", "number",
                    "nationality"):
            if mrz.fields.get(key):
                update[key] = mrz.fields[key]
        if mrz.fields.get("gender"):
            update["gender"] = _parse_gender(mrz.fields["gender"])
        for key in ("birth_date", "expiry_date"):
            parsed = _parse_date(mrz.fields.get(key, ""))
            if parsed:
                update[key] = parsed
        log.info("Passport verified by MRZ (%s)", mrz.fields.get("number", ""))
        # revalidated, not copied: model_copy skips the validators, and the
        # zone is exactly where a country code can come back as a серия
        return Passport.model_validate({**passport.model_dump(), **update})

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
        return Patent(
            series=f.get("series") or None,
            number=f.get("number", ""),
            blank_series=to_cyrillic(blank_series or "") or None,
            blank_number=blank_number,
            issue_date=issue_date,
            issued_by=to_cyrillic(issued_by or "") or None,
            profession=to_cyrillic(f.get("profession", "")) or "ПОДСОБНЫЙ РАБОЧИЙ",
            holder_surname=to_cyrillic(f.get("surname", "")) or None,
            holder_name=to_cyrillic(f.get("name", "")) or None,
            holder_patronymic=to_cyrillic(f.get("patronymic", "")) or None,
            holder_citizenship=to_cyrillic(f.get("citizenship", "")) or None,
        )

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
        if patent is not None and patent.holder_surname:
            passport = passport.model_copy(
                update={
                    "surname": patent.holder_surname,
                    "name": patent.holder_name or passport.name,
                    "patronymic": patent.holder_patronymic or passport.patronymic,
                    "nationality": patent.holder_citizenship or passport.nationality,
                }
            )
        return passport, patent
