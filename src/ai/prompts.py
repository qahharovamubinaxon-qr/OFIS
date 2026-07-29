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
    "IMPORTANT: output every NAME, PLACE and AUTHORITY in RUSSIAN CYRILLIC, "
    "uppercased. If the document is printed in Latin (e.g. KHUDAYBERDIEV JASUR), "
    "TRANSLITERATE to Cyrillic (ХУДАЙБЕРДИЕВ ЖАСУР; UZBEKISTAN→УЗБЕКИСТАН, KH→Х, "
    "ZH/J→Ж, SH→Ш, CH→Ч, YU→Ю, YA→Я). Never output Latin letters in a name, a "
    "place or an authority field.\n"
    "IMPORTANT — this NEVER applies to identifiers. A document series, a "
    "number, a VIN, a plate code, an ИНН: COPY THEM CHARACTER FOR CHARACTER AS "
    "PRINTED and never transliterate them. A passport series printed in Latin "
    "stays Latin — FA is FA, never ФА; FB is FB; C is C.\n"
)

_PASSPORT = _COMMON + (
    'Also read gender ("male" or "female"), the passport expiry date and the '
    'birth place. IMPORTANT: "birth_place" must be the COUNTRY the birth place '
    'is in, never a city/region (ФЕРГАНСКАЯ ОБЛАСТЬ→УЗБЕКИСТАН, ДУШАНБЕ→'
    'ТАДЖИКИСТАН, ОШ→КИРГИЗИЯ). '
    'IMPORTANT — "series" is ONLY a letter series actually printed as the '
    'passport series (e.g. Uzbek "AA" in "AA 1234567", "FA" in "FA 1234567"). '
    'It is printed in LATIN and must be copied in LATIN, exactly as printed — '
    'FA stays FA and must NEVER come back as ФА, FB as ФВ, or C as С. Do not '
    'transliterate the series under any circumstance. The country code '
    '(TJK, UZB, KGZ...) is NOT a series: never put it in "series" and never '
    'glue it to "number". A TAJIKISTAN passport has NO series at all — leave '
    '"series" EMPTY and put only its nine digits beginning with 4 in "number" '
    '(e.g. 406576690, never TJK406576690). '
    'IMPORTANT — "issued_by" must be in RUSSIAN, written the way a Russian form '
    'writes an authority: BY ITS INITIALS, IN CAPITALS. Every abbreviation must '
    'be RESOLVED, not copied: work out what it stands for and give the Russian '
    'equivalent abbreviation. You know these documents — expand it yourself. '
    'Tajik: ХШБ ВКД→ПРС МВД, ХШБ РВКД→ПРС УМВД, ХШБ→ПРС, ШВКД→ОМВД, ВКД→МВД, '
    'ҶТ→РТ, ФР→РФ, дар→в. Uzbek: IIV→МВД, IIB→УВД, TRIB→МРЭО, YHXB→УБДД, '
    'PSC→ЦГУ. Kyrgyz: МКК/SRS→ГРС, СӨМ/MDD→МЦР, SAIRT→ГАИРТ. Ukrainian: '
    'СГІРФО→СГИРФО, ВГІРФО→ВГИРФО, МРЕВ→МРЭО, ВРЕР→ОРЭР. Moldovan: ASP→АОУ. '
    'DIA→ОВД. Keep any office number, district or city name as printed. Never '
    'leave a non-Russian letter in the answer (ҳ→х, қ→к, ғ→г, ӣ→и, ӯ→у, ө→о, '
    'ү→у, і→и, and ҷ→дж: Тоҷикистон is ТАДЖИКИСТАН). If you genuinely do not '
    'know an abbreviation, copy it as printed rather than inventing one. '
    'Keys: {"document_type":"passport","surname","name","patronymic",'
    '"nationality","birth_date","birth_place","gender","series","number","issue_date",'
    '"expiry_date","issued_by","mrz_line1","mrz_line2"}\n'
    'IMPORTANT — the two lines of the machine-readable zone at the very bottom of the passport (they are 44 characters each and full of «<»). Copy them into mrz_line1 and mrz_line2 EXACTLY as printed, character for character, keeping every «<» and changing nothing. They are checked arithmetically, so a guess is worse than an empty string — leave them empty if you cannot read them cleanly.'
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


#: The worker's ИНН, off whatever document happens to carry it.
#:
#: Asked for on its own rather than folded into the patent prompt, because the
#: ИНН screen is given "a passport or a patent" and the operator should not
#: have to care which they dropped. The one thing this must never do is hand
#: back somebody else's number: a patent is covered in figures — its own
#: series and number, the issuing office's ИНН and ОГРН — and only the
#: twelve-digit one belongs to the person.
_INN_ONLY = (
    "You are an OCR extraction engine. Look at this Russian migration document "
    "(a патент, an ИНН certificate, or another form) and find the INDIVIDUAL'S "
    "ИНН — идентификационный номер налогоплательщика. Return ONLY a JSON "
    "object, no explanation, no markdown.\n"
    "WHERE IT IS ON A ПАТЕНТ — this is the important case. The card has a line "
    'labelled "Документ удост. личность/ИНН". Under that label are TWO values '
    'separated by a slash: the PASSPORT on the left and the ИНН on the right, '
    'like "FB0717527 / 072501692992". Return ONLY the right-hand part — the 12 '
    "digits after the slash. NEVER return the passport (it has letters in it), "
    "and NEVER glue the two numbers together into one long number.\n"
    "IMPORTANT — an individual's ИНН is EXACTLY 12 digits and OFTEN STARTS "
    'WITH ZERO ("072501692992"). Return it as a quoted JSON STRING and keep '
    "every leading zero — dropping one turns it into somebody else's number.\n"
    "IMPORTANT — a 10-digit number is an ORGANISATION's ИНН (the issuing "
    "office, the employer) and must NOT be returned. A 13- or 15-digit number "
    'is an ОГРН/ОГРНИП and must NOT be returned. The patent\'s own "Серия 77 '
    '№2500523150" is NOT an ИНН.\n'
    "Copy the digits exactly as printed, character for character. Do not "
    "calculate, correct or invent a single digit — if you cannot read all 12 "
    "cleanly, return an empty string instead. A wrong ИНН on a form is worse "
    "than an empty box the operator fills in.\n"
    'Keys: {"inn":"072501692992"}  (empty string if there is none)\n'
)


def inn_prompt() -> str:
    return _INN_ONLY
