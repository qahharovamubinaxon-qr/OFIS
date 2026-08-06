"""Per-document extraction prompts. Each asks for strict JSON with exactly the
keys the domain models need — never prose. Versioned so a prompt change is
traceable. Field keys match what :mod:`src.ocr.service` maps into the models.
"""

from __future__ import annotations

from src.ai.russian import RUSSIAN_RULES
from src.domain.enums import DocType

_COMMON = RUSSIAN_RULES + (
    "You are an OCR extraction engine for Russian migration documents. "
    "Read the image and return ONLY a JSON object, no explanation, no markdown. "
    "Use empty string for anything you cannot read. Dates as YYYY-MM-DD.\n"
)

_PASSPORT = _COMMON + (
    'THE PAGE YOU ARE READING, and where everything lives on it. A CIS '
    'passport data page is laid out the international way: the photograph '
    'at the LEFT; at the TOP the type (P), the country code (UZB/TJK/KGZ) '
    'and the passport number; then the holder\'s rows top to bottom — '
    'surname (Familiyasi/Surname), given name (Ismi/Given names), '
    'father\'s name (Otasining ismi/Father\'s name — Uzbek passports print '
    'it as a separate row), nationality (Fuqaroligi), birth date '
    '(Tug\'ilgan sanasi), sex (Jinsi: F/AYOL=female, M/ERKAK=male), birth '
    'place (Tug\'ilgan joyi), issue date (Berilgan sanasi), expiry date '
    '(Amal qilish muddati), authority (Kim tomonidan berilgan).\n'
    'THE STRIP AT THE FOOT OF THE PAGE — exactly what it is for. The two '
    '«<<<» lines carry the surname and the given names a SECOND time, in a '
    'machine font, which makes them the most reliable place on the whole '
    'page to read the LETTERS of a name. Use them for THAT and nothing '
    'else: to spell the name right. Line 1 reads '
    'P<UZBSURNAME<<GIVEN<NAMES<<<<< — the country code is the three letters '
    'after «P<», everything up to the «<<» is the SURNAME, everything after '
    'it is the given names, and a single «<» between words is a SPACE '
    '(«ABBOSBEK<JURAMUROD<UGLI» is ABBOSBEK, then JURAMUROD UGLI — two '
    'words, never run together). Always compare the printed name rows with '
    'the strip; where they disagree, the strip has the letters right. '
    'WHAT THE STRIP MUST NEVER TAKE AWAY: it is INCOMPLETE, and different '
    'in every country. Many passports put no father\'s name in it at all — '
    'a Tajik one never does — so when the printed page shows a father\'s '
    'name and the strip does not, the father\'s name IS there and comes '
    'from the printed row. The strip also has no issuing authority, no '
    'birth place and no issue date: all of those come from the printed '
    'rows. Never copy a «<», a check digit or the country code into any '
    'answer, and never say anything about the strip in your reply — it is '
    'a spelling aid, not a field.\n'
    'THE NUMBER STANDARDS — check what you read against them: an Uzbek '
    'passport is TWO Latin letters + SEVEN digits (FB 0701509 — series FB, '
    'number 0701509; the same figures repeat punched down the page edge). '
    'A Tajik passport is NINE digits beginning with 4 and has NO series. '
    'A Kyrgyz one is two letters (ID, AC, PE) + seven digits. If what you '
    'read does not fit the pattern, look again before answering.\n'
    'IMPORTANT — read the WHOLE data page. The father\'s name is printed as '
    'its own row — «Номи падар / Father\'s name» on a Tajik passport, '
    '«Otasining ismi» on an Uzbek one — and so are the issue date, the '
    'issuing authority and the birth place. '
    'Never leave "patronymic" empty when a father\'s name is printed anywhere '
    'on the page. '
    'BUT "patronymic" means ONLY a father\'s name field printed on the '
    'document — Отчество, Номи падар / Father\'s name, Otasining ismi. '
    'A "Middle name" (Philippine and Western passports print one — the '
    'mother\'s maiden name) is NOT a patronymic: leave "patronymic" EMPTY for '
    'such passports. Never derive a patronymic from the given name, the '
    'middle name or anything else. When the page has no father\'s-name row, '
    '"patronymic" MUST be "". '
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
    'IMPORTANT — THE NAME ROWS ARE COPIED TWICE. Beside the Russian spelling '
    'you also return the name EXACTLY as the page prints it in LATIN letters, '
    'character for character, in "surname_latin", "name_latin" and '
    '"patronymic_latin" — KAKHOROV, ABBOSBEK, JURAMUROD UGLI. Read those '
    'three off the printed rows AND off the strip at the foot of the page, '
    'and where the two disagree take the strip\'s letters: it is machine '
    'print and cannot be smudged. Copy what you read as it stands — do not '
    'translate it, do not simplify it, do not drop a letter. KAKHOROV is '
    'not KAKAROV and not KAKOROV: read the letters one by one, K-A-K-H-O-R-'
    'O-V. Keep the ʻ of Oʻ and Gʻ where the page prints one, and keep '
    '«UGLI», «OʻGʻLI» and «QIZI» as a SEPARATE word after the father\'s '
    'name — «JURAMUROD UGLI», never «JURAMURODUGLI». The program '
    'transliterates those Latin rows into Russian itself, by the office\'s '
    'own rules, so an exact copy matters more than your Cyrillic. If a row '
    'is genuinely not printed in Latin, leave that key "" — never invent '
    'one. '
    'IF THE PAGE IS NOT A PASSPORT PAGE but a Russian-language visa, '
    'миграционная карта or a Russian stamp carrying the holder\'s ФИО, read '
    'that ФИО as printed into "surname"/"name"/"patronymic" and leave the '
    'three "_latin" keys empty: a name already printed in Russian is the '
    'best source there is and must be copied, not transliterated. '
    'Keys: {"document_type":"passport","surname","name","patronymic",'
    '"surname_latin","name_latin","patronymic_latin",'
    '"nationality","birth_date","birth_place","gender","series","number",'
    '"issue_date","expiry_date","issued_by"}'
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
_INN_ONLY = RUSSIAN_RULES + (
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
_REGISTRATION = RUSSIAN_RULES + (
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


#: The ПИНФЛ (ЖШШИР) is nowhere on an Uzbek passport's face — it lives in the
#: strip at the foot, at the end of the second line. So this asks for the LINE
#: and not for the number: a line copied character for character can be taken
#: apart by arithmetic here (:mod:`src.domain.pinfl`), and arithmetic cannot
#: hallucinate. A number the reader «worked out» cannot be checked at all.
_PINFL_STRIP = (
    "You are an OCR extraction engine. This is the data page of a passport. "
    "Look ONLY at the machine-readable strip at the FOOT of the page — the two "
    "long lines set in a machine font and padded with «<» characters. Return "
    "ONLY a JSON object, no explanation, no markdown.\n"
    "Copy the SECOND of those two lines EXACTLY as printed, character for "
    "character, including every digit, every letter and every «<». Do not tidy "
    "it, do not remove the «<», do not add spaces, do not correct anything. It "
    "looks like this:\n"
    "  AA12345671UZB9505134M30051131301954050087<64\n"
    "Also copy the FIRST line the same way — it is asked for only so the "
    "program can tell the two apart if they arrive swapped.\n"
    "IMPORTANT — every character in the strip is meaningful and the program "
    "does the arithmetic itself. A single digit invented, dropped or "
    "«corrected» turns the number into another person's. If the strip is "
    "blurred, cut off or not visible in the image, return empty strings. An "
    "empty answer is right; a guessed one is not.\n"
    'Keys: {"line1":"P<UZBERGASHEV<<UMIDJON<<<<<<<<<<<<<<<<<<<<<<<",'
    '"line2":"AA12345671UZB9505134M30051131301954050087<64"}\n'
)


def pinfl_prompt() -> str:
    return _PINFL_STRIP
