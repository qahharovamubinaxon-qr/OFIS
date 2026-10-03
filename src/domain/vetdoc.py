"""Дўконнинг ўз ветеринария маълумотномаси — ҳайвон сотуви ва ишлови.

Бу ДАВЛАТ ҳужжати эмас. «Ветеринарное свидетельство. Форма № 1» ва «Защищенный
бланк ВСД» — Россельхознадзорнинг ваколатли врачи расмийлаштирадиган расмий
ҳужжат; уни дўкон ўзи чиқара олмайди. Бу ердаги нарса — дўконнинг **ўз**
маълумотномаси: нима сотилган, қандай ишлов/эмлаш қилинган, ким сотган.
Мижоз QR орқали дўкон сайтидан ўша ёзувни кўриб, ҳақиқийлигини текширади.

Майдонлар атайин кенг олинган: офис кейинчалик реестрга кириб, келиб чиқиш,
жўнатувчи-олувчи ва ташиш маълумотларини ҳам тўлдиради. Бўш майдон саҳифада
ҳам, бланкада ҳам кўринмайди — шунинг учун кераклисини тўлдириб кетаверса
бўлади.

Ҳар ёзув иккита белгига эга:
*code* — қисқа, QR ва ҳаволада турадиган очиқ код (A7K2M9 каби);
*uid*  — такрорланмас узун белги, ёзувни бир умрга ажратиб турадиган.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date

#: Кодда ишлатиладиган белгилар. Адашадиганлари (O/0, I/1) йўқ — мижоз кодни
#: қўлда теришга уринса ҳам янглишмасин.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 6


def new_code() -> str:
    """Янги очиқ код — QR ва ҳаволада турадигани."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LEN))


def new_uid() -> str:
    return str(uuid.uuid4()).upper()


@dataclass
class Shop:
    """Дўкон — бланкада ва саҳифанинг юқорисида турадигани.

    Созламада бир марта ёзилади; ҳар ёзувга қайта терилмайди.
    """

    name: str = ""                     # Меркурий
    legal: str = ""                    # тўлиқ номи / ИП
    address: str = ""
    phone: str = ""
    site: str = ""                     # саҳифалар турадиган манзил
    inn: str = ""


@dataclass
class Animal:
    """Рўйхатдаги битта ҳайвон ёки гуруҳ."""

    group_no: str = ""     # ҳайвон/гуруҳ рақами
    mark: str = ""         # белгилаш воситаси рақами
    farm_no: str = ""      # хўжалик ичидаги рақам
    nickname: str = ""     # лақаби
    sex: str = ""          # Самец / Самка
    breed: str = ""        # Петух
    age: str = ""          # 01.2026
    weight: str = ""       # 1
    count: str = ""        # бош сони
    note: str = ""         # б/н


@dataclass
class Treatment:
    """Эмлаш ёки паразитга қарши ишлов."""

    kind: str = ""         # обработка / вакцинация
    name: str = ""         # эндопаразиты
    done: str = ""         # 29.04.2026
    drug: str = ""         # Альбен — номи ва ишлаб чиқарувчиси
    series: str = ""       # препарат серияси
    until: str = ""        # амал қилиш муддати


@dataclass
class DocRef:
    """Ҳамроҳ ҳужжат — юк хати ва бошқалар."""

    series: str = ""
    number: str = ""
    issued: str = ""
    kind: str = ""


@dataclass
class VetRecord:
    """Битта сотув маълумотномаси — сайтда ҳам, бланкада ҳам шу."""

    # -- ҳужжатнинг ўзи
    code: str = field(default_factory=new_code)
    uid: str = field(default_factory=new_uid)
    number: str = ""                   # дўконнинг ўз рақами
    issued: date | None = None
    status: str = "оформлен"
    accounting: str = ""               # учёт: қоғоз бланкада
    made_by: str = ""                  # расмийлаштириш усули
    blank_no: str = ""                 # дўкон бланкасининг рақами

    # -- маҳсулот / ҳайвон
    batch: str = ""                    # ишлаб чиқариш партияси рақами
    kind: str = "Живые животные"
    product: str = ""                  # птица
    species: str = ""                  # курица (0105)
    title: str = ""                    # Петух
    volume: str = ""                   # 4 головы
    birth: str = ""                    # Январь 2026
    wellbeing: str = ""                # благополучие местности
    purpose: str = ""                  # направление: содержание
    held_since: str = ""               # қаердан бери сақланган
    quarantine_place: str = ""         # карантин жойи
    quarantine_days: str = ""          # карантин кунлари
    notes: str = ""                    # особые отметки
    incoming_doc: str = ""             # кирувчи ҳужжат (рақам, сана)
    production_doc: str = ""           # ишлаб чиқариш ҳужжати
    remark: str = ""                   # примечание

    # -- ташиш
    transaction: str = ""              # тип транзакции
    transport: str = ""                # тип транспорта
    storage: str = ""                  # сақлаш усули

    # -- келиб чиқиши
    origin_country: str = ""           # страна происхождения
    produced_by: str = ""              # ким/қаерда етиштирилган
    production_name: str = ""          # ишлаб чиқаришдаги номи
    origin_doc: str = ""               # келиб чиқишни тасдиқловчи ҳужжат

    # -- томонлар
    sender_company: str = ""           # жўнатувчи — корхона
    sender_subject: str = ""           # жўнатувчи — хўжалик юритувчи
    receiver_company: str = ""         # олувчи — корхона
    receiver_subject: str = ""         # олувчи — хўжалик юритувчи
    buyer: str = ""                    # харидор (мижоз)

    # -- расмийлаштирган
    institution: str = ""              # муассаса
    vet_name: str = ""                 # ветврач ФИО
    vet_post: str = ""                 # лавозими
    vet_phone: str = ""

    # -- жадваллар
    docs: list[DocRef] = field(default_factory=list)
    animals: list[Animal] = field(default_factory=list)
    treatments: list[Treatment] = field(default_factory=list)

    def head_count(self) -> int:
        """Рўйхатдаги ҳайвонлар сони."""
        return len(self.animals)
