"""Per-document extraction prompts. Each asks for strict JSON with exactly the
keys the domain models need — never prose. Versioned so a prompt change is
traceable. Field keys match what :mod:`src.ocr.service` maps into the models.
"""

from __future__ import annotations

from src.domain.enums import DocType

_COMMON = (
    "You are an OCR extraction engine for Russian migration documents. "
    "Read the image and return ONLY a JSON object, no explanation, no markdown. "
    "Use empty string for anything you cannot read. Dates as YYYY-MM-DD. "
    "IMPORTANT: output all names and words in RUSSIAN CYRILLIC, uppercased. If the "
    "document is printed in Latin (e.g. KHUDAYBERDIEV JASUR), TRANSLITERATE to "
    "Cyrillic (ХУДАЙБЕРДИЕВ ЖАСУР; UZBEKISTAN→УЗБЕКИСТАН, KH→Х, ZH/J→Ж, SH→Ш, "
    "CH→Ч, YU→Ю, YA→Я). Never output Latin letters in name/place fields.\n"
)

_PASSPORT = _COMMON + (
    'Also read gender ("male" or "female"), the passport expiry date and the '
    'birth place. IMPORTANT: "birth_place" must be the COUNTRY the birth place '
    'is in, never a city/region (ФЕРГАНСКАЯ ОБЛАСТЬ→УЗБЕКИСТАН, ДУШАНБЕ→'
    'ТАДЖИКИСТАН, ОШ→КИРГИЗИЯ). '
    'Keys: {"document_type":"passport","surname","name","patronymic",'
    '"nationality","birth_date","birth_place","gender","series","number","issue_date",'
    '"expiry_date","issued_by"}'
)

# Patent FRONT: the worker's ФИО (in Russian on the patent — the reliable name
# source), plus series, number, profession. Issue date + issuing org are on the BACK.
_PATENT = _COMMON + (
    'This is the FRONT of a Russian work patent (патент). The holder full name '
    '(Фамилия, Имя, Отчество) and citizenship (Гражданство) are printed here in '
    'Russian — read them exactly. '
    'Also read the blank series/number printed at the card bottom (e.g. ПР 6164274). '
    'Keys: {"document_type":"patent","surname","name","patronymic","citizenship",'
    '"series","number","profession","blank_series","blank_number"}'
)

# Patent BACK: the issuing organization ("Кем выдан") and the issue date.
_PATENT_BACK = _COMMON + (
    'This is the BACK of a Russian work patent (патент). Read the issuing '
    'organization ("Кем выдано", e.g. "ГУ МВД РОССИИ ПО МОСКОВСКОЙ ОБЛАСТИ"), '
    'the issue date ("Дата выдачи"), and the blank series+number printed at the '
    'card bottom (e.g. "ПР 8074980" → blank_series "ПР", blank_number "8074980"). '
    'Keys: {"issued_by","issue_date","blank_series","blank_number"}'
)

_STS = _COMMON + (
    'This is a Russian СТС (свидетельство о регистрации транспортного '
    'средства) — the small plastic vehicle registration card. Read the series '
    'and number printed on it (e.g. "50 ОЕ" + "202246"), the state plate '
    '(государственный регистрационный знак, e.g. Т566ВЕ40), the VIN '
    '(идентификационный номер, 17 characters — keep it in LATIN exactly as '
    'printed, do NOT transliterate it), the make and model (марка / модель — '
    'keep the manufacturer name in LATIN as printed, e.g. Hyundai Elantra), '
    'the year of manufacture, the category, and, if this is the back of the '
    'card, the owner (собственник) and their address. '
    'Keys: {"document_type":"sts","series","number","plate","vin","mark",'
    '"model","year","category","owner_fio","owner_address","issue_date"}'
)

_DRIVER_LICENCE = _COMMON + (
    'This is a driving licence (водительское удостоверение) — Russian or a '
    'foreign one. Read the holder surname, name and patronymic, the licence '
    'series and number (field 5, e.g. "AF 2970819" or "5036 634917" — keep the '
    'digits and letters exactly as printed), the birth date (field 3), the '
    'issue date (4a), the expiry date (4b) and the categories (field 9). '
    'Keys: {"document_type":"driver_licence","surname","name","patronymic",'
    '"series","number","birth_date","issue_date","expiry_date","categories"}'
)

_PROMPTS: dict[DocType, str] = {
    DocType.PASSPORT: _PASSPORT,
    DocType.PATENT: _PATENT,
    DocType.STS: _STS,
    DocType.DRIVER_LICENCE: _DRIVER_LICENCE,
}


def prompt_for(doc_type: DocType) -> str:
    return _PROMPTS.get(doc_type, _COMMON)


def patent_back_prompt() -> str:
    return _PATENT_BACK
