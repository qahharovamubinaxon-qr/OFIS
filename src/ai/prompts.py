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
    'IMPORTANT — read the WHOLE data page, not only the machine-readable zone '
    'at the bottom. The MRZ often has NO patronymic (a Tajik passport never '
    'prints it there), while the printed fields above DO — «Номи падар / '
    "Father's name» on a Tajik passport, «Otasining ismi» on an Uzbek one. "
    'Whatever the MRZ lacks must be taken from the printed part of the page: '
    'patronymic, issue date, issuing authority, birth place all live there. '
    'Never leave "patronymic" empty when a father\'s name is printed anywhere '
    'on the page. '
    'BUT "patronymic" means ONLY a father\'s name field printed on the '
    'document — Отчество, Номи падар / Father\'s name, Otasining ismi. '
    'A "Middle name" (Philippine and Western passports print one — the '
    'mother\'s maiden name) is NOT a patronymic: leave "patronymic" EMPTY for '
    'such passports. Never derive a patronymic from the given name, the '
    'middle name or anything else. When neither the MRZ nor the printed page '
    'has a father\'s-name field, "patronymic" MUST be "". '
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
    'IMPORTANT — "issued_by" is COPIED, not explained. Write EXACTLY what the '
    '«Кем выдан / Аз тарафи / Berilgan» line prints — the same short form, the '
    'same office number, in the same order — and only put it into Russian '
    'letters. NEVER expand an abbreviation into the office\'s full name and '
    'never replace it with a longer one you worked out yourself. '
    '«MIA 14505» is «МВД 14505» — not «ПРС», not «ПРС УМВД», not the passport '
    'service spelled out. The DIGITS of the office number are part of the '
    'answer: never drop them. '
    'The letter equivalents, and nothing more: MIA/MVD/ВКД/ХШБ→МВД, IIV→МВД, '
    'IIB→УВД, DIA→ОВД, TRIB→МРЭО, YHXB→УБДД, PSC→ЦГУ, ҶТ→РТ, ФР→РФ, дар→в; '
    'Kyrgyz МКК/SRS→ГРС, СӨМ/MDD→МЦР, SAIRT→ГАИРТ; Ukrainian СГІРФО→СГИРФО, '
    'ВГІРФО→ВГИРФО, МРЕВ→МРЭО, ВРЕР→ОРЭР; Moldovan ASP→АОУ. Keep any district '
    'or city name as printed. Never leave a non-Russian letter in the answer '
    '(ҳ→х, қ→к, ғ→г, ӣ→и, ӯ→у, ө→о, ү→у, і→и, and ҷ→дж: Тоҷикистон is '
    'ТАДЖИКИСТАН). If you do not know an abbreviation, copy it as printed '
    'rather than inventing one. '
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
    'Also copy the WHOLE line you read it from into "line", exactly as '
    'printed — "FB0717527 / 072501692992". If you are not sure which half is '
    'the ИНН, still give the line: the program can split it. An empty "inn" '
    'with a correct "line" is a good answer; a guessed "inn" is not.\n'
    'Keys: {"inn":"072501692992","line":"FB0717527 / 072501692992"}\n'
)


def inn_prompt() -> str:
    return _INN_ONLY


#: A регистрация — «Уведомление о прибытии иностранного гражданина» — read for
#: the ППУ pair. Everything the pair needs is already on it, including the day
#: the stay runs to, which is the one value the operator would otherwise have
#: to copy by hand and is therefore the one most worth reading.
_REGISTRATION = (
    "You are an OCR extraction engine. This is a Russian «Уведомление о "
    "прибытии иностранного гражданина в место пребывания» (регистрация). "
    "Return ONLY a JSON object, no explanation, no markdown.\n"
    "Read: the holder's ФАМИЛИЯ, ИМЯ, ОТЧЕСТВО; ДАТА РОЖДЕНИЯ; ПОЛ "
    '("Мужской" or "Женский"); ГРАЖДАНСТВО; the passport series and number; '
    "the ADDRESS of the place of stay; and the two dates of the stay, «Срок "
    "пребывания с … по …».\n"
    "IMPORTANT — the ADDRESS («Место пребывания» / адрес) must be the WHOLE "
    "address, every part that is printed, from the largest down to the "
    "smallest, joined into ONE line with commas: ОБЛАСТЬ, РАЙОН, ГОРОД or "
    "НАСЕЛЁННЫЙ ПУНКТ, УЛИЦА, ДОМ, КОРПУС, СТРОЕНИЕ, КВАРТИРА. Keep the "
    'labels the form uses — "обл.", "р-н", "г.", "ул.", "д.", "корп.", '
    '"стр.", "кв." — and keep every number. Do NOT return the house number on '
    "its own: «д. 33» is useless; «Московская обл., г. Балашиха, ул. Ленина, "
    "д. 33, корп. 2, кв. 15» is the answer. Leave out only the parts the form "
    "does not print — never a part it does.\n"
    "IMPORTANT — output names, the citizenship and the address in RUSSIAN "
    "CYRILLIC. But the passport series and number are IDENTIFIERS: copy them "
    "character for character as printed, in LATIN if they are printed in "
    "Latin. FA stays FA, never ФА.\n"
    "Dates as YYYY-MM-DD. Use an empty string for anything you cannot read "
    "cleanly — a guessed date or address is worse than a blank the operator "
    "fills in.\n"
    'Keys: {"surname","name","patronymic","birth_date","gender",'
    '"citizenship","series","number","address","stay_from","stay_to"}\n'
)


def registration_prompt() -> str:
    return _REGISTRATION
