"""How a foreign document must read once it is in Russian — the one rule.

Every section of the program asks a vision model to read a document and
give the answer in Russian: passports, patents, registrations, birth
certificates, contracts, чеки, translations. Each used to explain the
transcription in its own words — or not at all — and the readings drifted:
the same worker came back «ХУДЖАЕВ» from one screen and «ХОДЖАЕВ» from
another, «ОГЛИ» here and «УГЛИ» there, «СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ» once and
«СУРХАНДАРЬЯ» the next time.

So the rules live HERE, once, and every prompt in the program carries
them (``tests/unit/test_russian_rules.py`` refuses to let a prompt forget).
They are the practical transcription a Russian migration form uses — the
same one the патент itself is printed by, so a passport read here and a
патент read there give ONE name.

Nothing in this module is section-specific: it is about the Russian
language, not about any one form.
"""

from __future__ import annotations

#: Everything about turning a foreign document into Russian. Long on
#: purpose: a vision model follows an explicit table and invents when left
#: to itself.
RUSSIAN_RULES = (
    "ЯЗЫК ОТВЕТА — РУССКИЙ. Каждое ИМЯ, ФАМИЛИЯ, ОТЧЕСТВО, НАЗВАНИЕ МЕСТА "
    "и ОРГАНА пиши РУССКИМИ БУКВАМИ, ЗАГЛАВНЫМИ, какого бы языка и письма "
    "документ ни был — узбекская латиница, таджикская кириллица, киргизский, "
    "английский. Ответ всегда в той форме, в какой это печатают российские "
    "миграционные документы (патент, бланки МВД). Латинских букв в имени, "
    "месте или органе быть не должно.\n"
    "ПРАВИЛА ПЕРЕДАЧИ (узбекская латиница → русский), буква за буквой: "
    "KH→Х, X→Х, H→Х, Q→К, G'/Gʻ→Г, O'/Oʻ→У (никогда не О: O'G'LI→УГЛИ, "
    "O'KTAM→УКТАМ, YO'LDOSH→ЮЛДОШ), SH→Ш, CH→Ч, ZH→Ж, J→Ж (JASUR→ЖАСУР, "
    "JAMSHID→ЖАМШИД), YO→Ё, YU→Ю, YA→Я, TS→Ц, W→В, C→К. E в НАЧАЛЕ имени — "
    "Э (ERGASH→ЭРГАШ, ELMUROD→ЭЛМУРОД), внутри имени — Е (BEKZOD→БЕКЗОД). "
    "Апострофы отбрасывай. Окончания: -OV→-ОВ, -OVA→-ОВА, -YEV/-EV→-ЕВ, "
    "-YEVA/-EVA→-ЕВА, O'G'LI→УГЛИ, QIZI→КИЗИ, -JON→-ЖОН, -BEK→-БЕК. Пиши "
    "имя так, как его напечатал бы ПАТЕНТ этого же человека.\n"
    "ЭТИ ПРАВИЛА — ДЛЯ ЛЮБОГО ПАСПОРТА, не только узбекского. Ниже — "
    "буквы каждой республики.\n"
    "ТАДЖИКСКИЙ (кириллица): Ҷ/ҷ→ДЖ/дж — это ДВЕ русские буквы, а не Ч "
    "(Ҷамшед→ДЖАМШЕД, Ҷумъа→ДЖУМА, Хоҷа→ХОДЖА, Тоҷикистон→ТАДЖИКИСТАН); "
    "Ҳ→Х, Қ→К, Ғ→Г, Ӣ→И, Ӯ→У. В таджикской ЛАТИНИЦЕ та же буква "
    "пишется J: JAMSHED→ДЖАМШЕД, JURA→ДЖУРА (в узбекской латинице J — "
    "это Ж: JASUR→ЖАСУР). Смотри на гражданство и выбирай.\n"
    "КИРГИЗСКИЙ: Ө→О, Ү→У, Ң→Н (Өмүрбек→ОМУРБЕК, Жеңиш→ЖЕНИШ).\n"
    "КАЗАХСКИЙ: Ә→А, Ұ→У, Һ→Х, Қ→К, Ғ→Г, Ө→О, Ү→У, Ң→Н, І→И "
    "(Әбдіғаппар→АБДИГАППАР, Ұлан→УЛАН).\n"
    "АЗЕРБАЙДЖАНСКИЙ: латиница Ə→А, Ğ→Г, Ş→Ш, Ç→Ч, Ö→О, Ü→У, İ→И, "
    "C→ДЖ, J→Ж (Əliyev→АЛИЕВ, Cəfər→ДЖАФАР); старая кириллица Ҹ→ДЖ, "
    "Ҝ→Г.\n"
    "ТУРКМЕНСКИЙ (латиница): Ä→А, Ž→Ж, Ň→Н, Ý→Й, Ş→Ш, Ö→О, Ü→У "
    "(Şöhrat→ШОХРАТ, Ýazmyrat→ЯЗМЫРАТ).\n"
    "МОЛДАВСКИЙ (латиница): Ă/Â→А, Î→И, Ș→Ш, Ț→Ц (Ștefan→ШТЕФАН).\n"
    "БЕЛОРУССКИЙ: Ў→У, І→И (Ўладзімір→ВЛАДИМИР).\n"
    "УКРАИНСКИЙ: І→И, Ї→И, Є→Е, Ґ→Г.\n"
    "ГРАММАТИКА. Русский язык склоняется — пиши так, как требует строка "
    "документа, а не подстрочником: «выдан ОВД города Душанбе» (не «город "
    "Душанбе»), «место рождения: СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ» (именительный), "
    "«зарегистрирован по адресу: город Москва, улица Ленина, дом 5». "
    "Названия областей — прилагательные: не «СУРХАНДАРЬЯ ОБЛАСТЬ», а "
    "«СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ». Сокращения как на русских бланках: обл., "
    "р-н, г., пос., ул., д., корп., стр., кв.\n"
    "СТРАНЫ по-русски: UZBEKISTAN/O'ZBEKISTON→УЗБЕКИСТАН, "
    "TAJIKISTAN/ТОҶИКИСТОН→ТАДЖИКИСТАН, KYRGYZSTAN→КИРГИЗИЯ, "
    "KAZAKHSTAN→КАЗАХСТАН, TURKMENISTAN→ТУРКМЕНИСТАН, "
    "AZERBAIJAN→АЗЕРБАЙДЖАН, ARMENIA→АРМЕНИЯ, GEORGIA→ГРУЗИЯ, "
    "MOLDOVA→МОЛДОВА, UKRAINE→УКРАИНА, BELARUS→БЕЛАРУСЬ, RUSSIA→РОССИЯ.\n"
    "ОБЛАСТИ и РЕГИОНЫ — их принятые русские названия: SURKHANDARYA→"
    "СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ, FERGANA→ФЕРГАНСКАЯ ОБЛАСТЬ, TASHKENT→"
    "ТАШКЕНТСКАЯ ОБЛАСТЬ (город — Г. ТАШКЕНТ), KHOREZM→ХОРЕЗМСКАЯ ОБЛАСТЬ, "
    "ANDIJAN→АНДИЖАНСКАЯ ОБЛАСТЬ, NAMANGAN→НАМАНГАНСКАЯ ОБЛАСТЬ, "
    "SAMARKAND→САМАРКАНДСКАЯ ОБЛАСТЬ, BUKHARA→БУХАРСКАЯ ОБЛАСТЬ, "
    "KASHKADARYA→КАШКАДАРЬИНСКАЯ ОБЛАСТЬ, JIZZAKH→ДЖИЗАКСКАЯ ОБЛАСТЬ, "
    "SYRDARYA→СЫРДАРЬИНСКАЯ ОБЛАСТЬ, NAVOI→НАВОИЙСКАЯ ОБЛАСТЬ, "
    "KARAKALPAKSTAN→РЕСПУБЛИКА КАРАКАЛПАКСТАН, KHATLON→ХАТЛОНСКАЯ ОБЛАСТЬ, "
    "SUGHD→СОГДИЙСКАЯ ОБЛАСТЬ, DUSHANBE→Г. ДУШАНБЕ, OSH→ОШСКАЯ ОБЛАСТЬ. "
    "Не выдумывай написание: если принятая форма неизвестна, передай по "
    "буквам выше.\n"
    "ЧЕГО ДЕЛАТЬ НЕЛЬЗЯ: не переводи и не транслитерируй ИДЕНТИФИКАТОРЫ — "
    "серию и номер документа, VIN, госномер, ИНН, ОГРН, номер патента: "
    "копируй их символ в символ, как напечатано. Серия паспорта, "
    "напечатанная латиницей, латиницей и остаётся: FA — это FA, а не ФА.\n"
    "И НИКОГДА НЕ ДОГАДЫВАЙСЯ: если поле не читается — верни пустую "
    "строку. Пустое поле оператор заполнит сам, а придуманное попадёт в "
    "документ.\n"
)

#: The shortest form, for prompts that are already long and only handle
#: names in passing (layout probes, чек, addresses).
RUSSIAN_SHORT = (
    "Пиши всё по-русски, русскими заглавными буквами: KH/X/H→Х, Q→К, "
    "G'→Г, O'→У (O'G'LI→УГЛИ), SH→Ш, CH→Ч, J/ZH→Ж, YU→Ю, YA→Я, YO→Ё; "
    "E в начале имени→Э. Буквы других республик: Ҷ/Ҹ→ДЖ (Ҷамшед→ДЖАМШЕД), "
    "Ҳ→Х, Қ→К, Ғ→Г, Ӣ→И, Ӯ→У, Ә→А, Ұ→У, Һ→Х, Ө→О, Ү→У, Ң→Н, Ў→У, І→И; "
    "латиница Ə→А, Ğ→Г, Ş→Ш, Ç→Ч, Ö→О, Ü→У, Ä→А, Ž→Ж, Ň→Н, Ș→Ш, Ț→Ц. "
    "Области — прилагательными (СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ). Серии, номера, "
    "ИНН и VIN копируй символ в символ и НЕ переводи.\n"
)


def with_rules(prompt: str, *, short: bool = False) -> str:
    """The prompt, carrying the program's Russian rules.

    Placed FIRST: a model reads the standing rules, then the job.
    """
    return (RUSSIAN_SHORT if short else RUSSIAN_RULES) + prompt
