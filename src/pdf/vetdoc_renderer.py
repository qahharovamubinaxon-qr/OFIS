"""Дўкон маълумотномасининг бланкаси — бўш қоғоздан бошлаб чизилади.

Бошқа бўлимларда бланка тайёр PDF бўлиб юкланади ва унинг устига ёзилади. Бу
ерда эса дўконнинг ўз ҳужжати: тайёр бланка йўқ, шунинг учун варақ бошдан-оёқ
шу модулда чизилади — сарлавҳа, логотип, бўлимлар, жадваллар, QR, муҳр ва имзо
жойи. Фақат **тўлдирилган** майдон босилади: қоғоз тоза чиқсин, оператор
кераклисини тўлдириб кетаверсин.

Сайт саҳифаси (:mod:`src.services.vetdoc_page`) билан бир хил маълумотни
кўрсатади; фарқи — у ерда реестрдаги барча майдон кўринади, бу ерда эса бўш
қатор босилмайди.

QR мижозни дўкон саҳифасига олиб боради: қоғоздаги маълумот ўша ёзувга мос
келишини ўзи кўриб текширади.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.domain.vetdoc import Shop, VetRecord
from src.pdf.engine import _font_file
from src.pdf.qr import draw_qr

log = get_logger(__name__)

DOC_TITLE = "СПРАВКА О ПРОДАЖЕ И ВЕТЕРИНАРНОЙ ОБРАБОТКЕ ЖИВОТНОГО"
#: Ҳужжат давлат ВСД си эмаслиги — ҳар варақда, кичик ҳарфда, яширмасдан.
DISCLAIMER = ("Собственный документ магазина. Подтверждает сведения, внесённые "
              "продавцом, и не является ветеринарным сопроводительным "
              "документом (ВСД) государственной информационной системы.")

#: Дўкон ранги — саҳифадаги #12605b нинг айни ўзи.
BRAND = (0x12 / 255, 0x60 / 255, 0x5B / 255)
INK = (0.13, 0.16, 0.18)
GREY = (0.42, 0.48, 0.47)
RULE = (0.84, 0.88, 0.88)
BAND = (0.957, 0.973, 0.973)

_REG, _BOLD = "OfisArial", "OfisArialBold"
_IDS = {_REG: "vd_r", _BOLD: "vd_b"}

MARGIN = 36.0
#: Майдон номи учун ажратилган устун кенглиги (икки устунли тўрда — ярмида).
LABEL_W = 150.0
#: Майдон номи эгаллайдиган устун ва ундан кейинги бўшлиқ.
LABEL_COL = LABEL_W / 2 + 34
VALUE_GAP = 8.0
FOOT_H = 96.0            # имзо/муҳр ва огоҳлантириш учун пастдаги жой


def _value_limit(col: float) -> float:
    """Қиймат ёзиладиган кенглик.

    Қатор баландлигини ҳисоблаган жой ҳам, матнни ёзадиган жой ҳам АЙНИ шу
    ўлчовдан фойдаланиши шарт: акс ҳолда баландлик кам чиқиб, узун қиймат
    пастдаги қаторнинг устига тушади.
    """
    return col - LABEL_COL - VALUE_GAP


@dataclass(frozen=True)
class Section:
    """Бланкадаги бир бўлим: номи ва «ном — қиймат» жуфтликлари."""

    title: str
    rows: list[tuple[str, str]]

    def filled(self) -> list[tuple[str, str]]:
        return [(label, str(value).strip()) for label, value in self.rows
                if str(value or "").strip()]


def sections(record: VetRecord, shop: Shop) -> list[Section]:
    """Бланкада босиладиган бўлимлар — сайтдаги тартибнинг ўзи."""
    seller = shop.legal or shop.name
    issued = record.issued.strftime("%d.%m.%Y") if record.issued else ""
    return [
        Section("Общие сведения", [
            ("Номер справки", record.number or record.code),
            ("Дата оформления", issued),
            ("Код проверки", record.code),
            ("Учёт", record.accounting),
            ("Способ оформления", record.made_by),
            ("Номер бланка", record.blank_no),
            ("Выдал", seller),
        ]),
        Section("Информация о продукции", [
            ("Номер производственной партии", record.batch),
            ("Тип продукции", record.kind),
            ("Продукция", record.product),
            ("Вид продукции", record.species),
            ("Наименование продукции", record.title),
            ("Объём", record.volume),
            ("Дата рождения", record.birth),
            ("Благополучие местности", record.wellbeing),
            ("Направление", record.purpose),
            ("Животные содержались", record.held_since),
            ("Место для карантинирования", record.quarantine_place),
            ("Количество дней карантинирования", record.quarantine_days),
            ("Особые отметки", record.notes),
            ("Номер и дата входящего документа", record.incoming_doc),
            ("Номер и дата производственного документа", record.production_doc),
            ("Примечание", record.remark),
        ]),
        Section("Транспорт и происхождение", [
            ("Тип транзакции", record.transaction),
            ("Тип транспорта", record.transport),
            ("Способ хранения при перевозке", record.storage),
            ("Страна происхождения", record.origin_country),
            ("Выработана / выращены", record.produced_by),
            ("Наименование при производстве", record.production_name),
            ("Документ о происхождении", record.origin_doc),
        ]),
        Section("Отправитель", [
            ("Название предприятия", record.sender_company or seller),
            ("Хозяйствующий субъект", record.sender_subject),
            ("Адрес", shop.address),
            ("Телефон", shop.phone),
            ("ИНН", shop.inn),
        ]),
        Section("Получатель", [
            ("Название предприятия", record.receiver_company),
            ("Хозяйствующий субъект", record.receiver_subject),
            ("Покупатель", record.buyer),
        ]),
        Section("Оформление", [
            ("Учреждение", record.institution or seller),
            ("Ф.И.О. ветеринарного врача", record.vet_name),
            ("Должность", record.vet_post),
            ("Контактный телефон", record.vet_phone or shop.phone),
        ]),
    ]


class _Sheet:
    """Варақни кетма-кет тўлдириб борадиган ёзув ускунаси.

    Жой тугаса ўзи янги варақ очади ва юқорисига қисқа сарлавҳа ёзади — шунда
    узун рўйхат ҳам бир ҳужжат бўлиб кўринади.
    """

    def __init__(self, doc: fitz.Document, record: VetRecord, shop: Shop, *,
                 link: str = "", logo: Path | None = None) -> None:
        self._doc = doc
        self._record = record
        self._shop = shop
        self._link = link
        self._logo = logo
        self._faces = {name: fitz.Font(fontfile=str(_font_file(name)))
                       for name in _IDS}
        self.page: fitz.Page | None = None
        self.y = 0.0
        self._first = True
        self._new_page()

    # ------------------------------------------------------------ ўлчовлар
    @property
    def right(self) -> float:
        assert self.page is not None
        return self.page.rect.width - MARGIN

    @property
    def width(self) -> float:
        return self.right - MARGIN

    def _bottom(self) -> float:
        assert self.page is not None
        return self.page.rect.height - MARGIN - FOOT_H

    def text_width(self, text: str, *, bold: bool = False,
                   size: float = 9.0) -> float:
        face = self._faces[_BOLD if bold else _REG]
        return face.text_length(text, fontsize=size)

    def _fit(self, text: str, limit: float, *, bold: bool, size: float) -> float:
        """Матн устунга сиғадиган ўлчов — керак бўлса кичрайтирилади."""
        while size > 5.0 and self.text_width(text, bold=bold, size=size) > limit:
            size -= 0.25
        return size

    # ------------------------------------------------------------ чизиш
    def write(self, x: float, y: float, text: str, *, bold: bool = False,
              size: float = 9.0, colour: tuple[float, float, float] = INK,
              limit: float | None = None) -> None:
        if not text:
            return
        if limit:
            size = self._fit(text, limit, bold=bold, size=size)
        assert self.page is not None
        self.page.insert_text((x, y), text, fontsize=size,
                              fontname=_IDS[_BOLD if bold else _REG],
                              color=colour)

    def need(self, height: float) -> None:
        """Жой етмаса — янги варақ."""
        if self.y + height > self._bottom():
            self._new_page()

    def _new_page(self) -> None:
        self.page = self._doc.new_page(width=595.28, height=841.89)
        for name, pdf_id in _IDS.items():
            self.page.insert_font(fontname=pdf_id, fontfile=str(_font_file(name)))
        self.y = MARGIN
        if self._first:
            self._header()
            self._first = False
        else:
            self._continuation()
        self._note_strip()

    # ------------------------------------------------------------ сарлавҳа
    def _header(self) -> None:
        page = self.page
        assert page is not None
        page.draw_rect(fitz.Rect(MARGIN, self.y, self.right, self.y + 3),
                       color=None, fill=BRAND)
        top = self.y + 16
        box = fitz.Rect(MARGIN, top, MARGIN + 44, top + 44)
        drawn = False
        if self._logo and Path(self._logo).exists():
            try:
                page.insert_image(box, filename=str(self._logo),
                                  keep_proportion=True)
                drawn = True
            except (RuntimeError, ValueError):
                log.warning("vetdoc: логотип қўйилмади: %s", self._logo)
        if not drawn:
            page.draw_rect(box, color=None, fill=BRAND)
            letter = (self._shop.name or "В")[:1].upper()
            size = 24.0
            self.write(box.x0 + (box.width - self.text_width(
                letter, bold=True, size=size)) / 2,
                box.y1 - 13, letter, bold=True, size=size, colour=(1, 1, 1))

        left = box.x1 + 12
        self.write(left, top + 15, self._shop.name or "ВЕТ-МАГАЗИН",
                   bold=True, size=16, colour=BRAND, limit=260)
        self.write(left, top + 28, "ветеринарный магазин · аптека · ветврач",
                   size=8, colour=GREY, limit=260)
        tail = " · ".join(x for x in (self._shop.address, self._shop.phone) if x)
        self.write(left, top + 39, tail, size=8, colour=GREY, limit=300)

        # QR — ўнг юқори бурчакда, остида код
        self._qr(fitz.Rect(self.right - 62, top, self.right - 6, top + 56))

        self.y = top + 62
        self._rule()
        self.y += 18
        title_size = self._fit(DOC_TITLE, self.width, bold=True, size=11.5)
        self.write(MARGIN + (self.width - self.text_width(
            DOC_TITLE, bold=True, size=title_size)) / 2, self.y, DOC_TITLE,
            bold=True, size=title_size)
        self.y += 14
        issued = (self._record.issued.strftime("%d.%m.%Y")
                  if self._record.issued else "")
        line = f"№ {self._record.number or self._record.code}"
        if issued:
            line += f"   от {issued}"
        self.write(MARGIN + (self.width - self.text_width(line, size=10)) / 2,
                   self.y, line, size=10, colour=GREY)
        self.y += 16

    def _continuation(self) -> None:
        name = self._shop.name or "ВЕТ-МАГАЗИН"
        number = self._record.number or self._record.code
        head = f"{name} · справка № {number} · продолжение"
        self.write(MARGIN, self.y + 9, head, size=8.5, colour=GREY,
                   limit=self.width)
        self.y += 14
        self._rule()
        self.y += 12

    def _qr(self, box: fitz.Rect) -> None:
        payload = self._link or self._record.code
        try:
            draw_qr(self.page, payload, box)
        except Exception as exc:  # noqa: BLE001 - QR йўқлиги ҳужжатни тўхтатмайди
            log.warning("vetdoc: QR чизилмади: %s", exc)
            return
        caption = f"код: {self._record.code}"
        self.write(box.x1 - self.text_width(caption, size=7),
                   box.y1 + 9, caption, size=7, colour=GREY)
        self.write(box.x1 - self.text_width("проверка →", size=6.5),
                   box.y1 + 17, "проверка →", size=6.5, colour=GREY)

    def _rule(self) -> None:
        assert self.page is not None
        self.page.draw_line((MARGIN, self.y), (self.right, self.y),
                            color=RULE, width=0.7)

    # ------------------------------------------------------------ бўлимлар
    def section(self, title: str, rows: list[tuple[str, str]]) -> None:
        """Икки устунли «ном — қиймат» тўри."""
        if not rows:
            return
        self.need(34)
        self.heading(title)
        col = self.width / 2
        for index in range(0, len(rows), 2):
            pair = rows[index:index + 2]
            heights = [self._row_height(v, _value_limit(col)) for _, v in pair]
            step = max(heights)
            self.need(step + 2)
            for slot, (label, value) in enumerate(pair):
                x = MARGIN + slot * col
                self._row(x, label, value, col)
            self.y += step + 2

    def heading(self, title: str) -> None:
        self.need(22)
        self.y += 10
        self.write(MARGIN, self.y, title.upper(), bold=True, size=8.5,
                   colour=BRAND, limit=self.width)
        self.y += 4
        self._rule()
        self.y += 11

    def _row_height(self, value: str, limit: float) -> float:
        return 11.0 * max(1, len(self._wrap(value, limit, size=9.0)))

    def _row(self, x: float, label: str, value: str, col: float) -> None:
        """Битта «ном — қиймат». ``self.y`` га тегмайди: жуфтликнинг иккала
        устуни ҳам бир сатрдан бошланиши керак, қанча қаторга чўзилганидан
        қатъи назар — баландликни чақирувчи :meth:`_row_height` дан олади."""
        self.write(x, self.y, label, size=7.8, colour=GREY, limit=LABEL_COL - 6)
        limit = _value_limit(col)
        for index, line in enumerate(self._wrap(value, limit, size=9.0)):
            self.write(x + LABEL_COL, self.y + index * 11, line, size=9.0,
                       limit=limit)

    def _wrap(self, text: str, limit: float, *, size: float,
              bold: bool = False) -> list[str]:
        """Матнни устун кенглигига қараб қаторларга бўлиш."""
        text = (text or "").strip()
        if not text:
            return [""]
        if self.text_width(text, bold=bold, size=size) <= limit:
            return [text]
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if current and self.text_width(trial, bold=bold, size=size) > limit:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [text]

    # ------------------------------------------------------------ жадваллар
    def table(self, title: str, head: list[str], rows: list[list[str]],
              widths: list[float]) -> None:
        if not rows:
            return
        # бош қатор + камида иккита қатор сиғмаса, жадвални кейинги варақдан
        # бошлаган афзал: битта қатор қолиб «давоми» га ўтиши хунук кўринади
        self.need(24 + 14 * min(2, len(rows)))
        self.heading(title)
        total = sum(widths)
        widths = [w / total * self.width for w in widths]
        self._table_head(head, widths)
        for row in rows:
            if self.y + 14 > self._bottom():
                self._new_page()
                self.heading(f"{title} (продолжение)")
                self._table_head(head, widths)
            self._table_row(row, widths)

    def _table_head(self, head: list[str], widths: list[float]) -> None:
        assert self.page is not None
        self.page.draw_rect(fitz.Rect(MARGIN, self.y - 8, self.right, self.y + 4),
                            color=None, fill=BAND)
        x = MARGIN
        for text, w in zip(head, widths, strict=True):
            self.write(x + 3, self.y, text, bold=True, size=7.2, colour=GREY,
                       limit=w - 6)
            x += w
        self.y += 5
        self._rule()
        self.y += 10

    def _table_row(self, row: list[str], widths: list[float]) -> None:
        x = MARGIN
        for text, w in zip(row, widths, strict=True):
            self.write(x + 3, self.y, str(text or ""), size=8, limit=w - 6)
            x += w
        self.y += 3
        self._rule()
        self.y += 11

    # ------------------------------------------------------------ пастки қисм
    def _note_strip(self) -> None:
        """Ҳар варақнинг этаги: ҳужжат нималиги ва текшириш ҳаволаси."""
        page = self.page
        assert page is not None
        base = page.rect.height - MARGIN
        note_y = base - 30
        for line in self._wrap(DISCLAIMER, self.width - 110, size=6.8):
            self.write(MARGIN, note_y, line, size=6.8, colour=GREY)
            note_y += 8
        if self._link:
            self.write(MARGIN, note_y + 2, f"Проверка: {self._link}", size=6.8,
                       colour=BRAND, limit=self.width - 110)

    def finish(self) -> None:
        """Ҳужжатни ёпиш: имзо-муҳр охирги варақда, рақамлар — ҳаммасида.

        Имзо жойи ҳар варақда турса, биринчи варақ тугагандек кўринади — шунинг
        учун у фақат энг охирида чизилади.
        """
        self._signatures()
        total = self._doc.page_count
        if total < 2:
            return
        for index, page in enumerate(self._doc, 1):
            text = f"стр. {index} из {total}"
            page.insert_text(
                (page.rect.width - MARGIN - self.text_width(text, size=6.8),
                 page.rect.height - MARGIN - 2),
                text, fontsize=6.8, fontname=_IDS[_REG], color=GREY)

    def _signatures(self) -> None:
        page = self.page
        assert page is not None
        base = page.rect.height - MARGIN
        line_y = base - 52
        self.write(MARGIN, line_y - 4, "Ветеринарный врач", size=8, colour=GREY)
        page.draw_line((MARGIN + 92, line_y), (MARGIN + 230, line_y),
                       color=RULE, width=0.7)
        self.write(MARGIN + 240, line_y - 4, "Продавец", size=8, colour=GREY)
        page.draw_line((MARGIN + 288, line_y), (MARGIN + 400, line_y),
                       color=RULE, width=0.7)
        stamp = fitz.Rect(self.right - 96, base - 92, self.right, base - 20)
        page.draw_rect(stamp, color=RULE, width=0.7, dashes="[2 2] 0")
        self.write(stamp.x0 + (stamp.width - self.text_width("М.П.", size=8)) / 2,
                   stamp.y0 + stamp.height / 2 + 3, "М.П.", size=8, colour=GREY)


def _animal_rows(record: VetRecord) -> list[list[str]]:
    return [[str(i), a.group_no, a.mark, a.farm_no, a.nickname, a.sex,
             a.breed, a.age, a.weight, a.count, a.note]
            for i, a in enumerate(record.animals, 1)]


def render(record: VetRecord, shop: Shop, *, link: str = "",
           logo: Path | None = None) -> fitz.Document:
    """Маълумотномани тўлиқ PDF қилиб қайтаради (сақлаш — чақирувчида)."""
    doc = fitz.open()
    sheet = _Sheet(doc, record, shop, link=link, logo=logo)
    for block in sections(record, shop):
        sheet.section(block.title, block.filled())
    sheet.table(
        "Опись живых животных",
        ["№", "Номер группы", "Маркировка", "Внутрихоз. №", "Кличка", "Пол",
         "Порода", "Возраст", "Вес, кг", "Кол-во", "Примечание"],
        _animal_rows(record),
        [16, 52, 56, 52, 44, 32, 52, 40, 32, 30, 48],
    )
    sheet.table(
        "Иммунизация и обработка против паразитов",
        ["Тип", "Наименование", "Дата", "Препарат и производитель",
         "Серия", "Действует до"],
        [[t.kind, t.name, t.done, t.drug, t.series, t.until]
         for t in record.treatments],
        [44, 72, 44, 120, 38, 48],
    )
    sheet.table(
        "Сопроводительные документы",
        ["Серия", "Номер", "Дата выдачи", "Тип документа"],
        [[d.series, d.number, d.issued, d.kind] for d in record.docs],
        [44, 56, 56, 160],
    )
    sheet.finish()
    return doc


def output_name(record: VetRecord) -> str:
    """Файл номи: харидор фамилияси бўлса у, бўлмаса код."""
    buyer = (record.buyer or "").strip()
    if buyer:
        surname = buyer.split()[0].upper()
        return f"{surname}_{record.code}.pdf"
    number = (record.number or record.code).replace("/", "-").replace(" ", "")
    return f"{number}.pdf"
