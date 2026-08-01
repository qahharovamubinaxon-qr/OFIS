"""Where every value sits on the МВД ТРУДАВОЙ packet — ten pages, measured.

The packet the office posts to the МВД for its long-term workers: two справки,
the Прил. №1 уведомление (2 pages of letter-cells), the трудовой договор
(2 pages), and the Прил. №7 уведомление (4 pages of letter-cells). The firm's
own constants — its name, ИНН, addresses, the орган МВД, the pre-ticked X'es —
are already printed on the firm's blank; comparing the office's filled packet
against its empty one showed **only the worker's values** as new ink, and
this file is those values' measured positions.

Positions are shares of the page (x, baseline, size-of-page-height), the same
convention every other section uses, so a re-scanned blank at any size still
comes out right and the layout editor's numbers keep meaning something.

Two kinds of value:

* ``text`` — written once at its spot (the договор pages, the справки).
* ``cells`` — one character per printed box, at ``x + i * pitch``. The form's
  cell pitch was measured off the letter grid: 0.0273 of the page width on the
  Прил. №1 grid, slightly narrower elsewhere; each row records its own.

To nudge anything: «📐 Матнларни жойлаш» in the section, page by page — or
edit the three (four) numbers here.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The office prints the packet in Times, BOLD — the owner asked for the
#: values to stand off the form («ТЕКСТЛАРНИ ЖИРНИЙ КИЛ»).
FONT = "OfisSerifBold"

#: One text size for the whole packet, as the owner asked («РАЗМЕРЛАРИНИ
#: БИРХИЛ КИЛ»): ~10pt on A4. Cells take CELL_SIZE so a character fills its
#: box without touching the walls.
TEXT_SIZE = 0.0122
CELL_SIZE = 0.0125

TEXT_OPACITY = 0.9

#: How far a wrapped cell row sits below its first row, in page height.
ROW_STEP = 0.0345


@dataclass(frozen=True)
class Slot:
    """One value on one page."""

    page: int                 # 1-based
    x: float
    baseline: float
    size: float = TEXT_SIZE
    #: 0 → plain text; positive → letter-cells with this pitch (page width)
    pitch: float = 0.0
    #: cells only: how many boxes a row has before wrapping to the next
    per_row: int = 0
    #: cells only: total rows available (first + continuations below)
    rows: int = 1
    #: continuation rows often start back at the page margin, full width —
    #: their own x, cell count and pitch; -1 keeps the first row's
    wrap_x: float = -1.0
    wrap_per_row: int = 0
    wrap_pitch: float = -1.0
    #: how far each continuation row sits below the previous (page height)
    row_step: float = ROW_STEP


#: Every worker value, measured off the office's own filled packet.
SLOTS: dict[str, Slot] = {
    # -- 1: Справка о приеме уведомления (Прил. N3, приказ 536) -----------
    "p1_accept_date":  Slot(1, 0.2660, 0.5925),
    "p1_uved_no":      Slot(1, 0.6830, 0.6377),
    "p1_uved_date":    Slot(1, 0.7830, 0.6377),
    "p1_republic":     Slot(1, 0.5380, 0.6971),
    "p1_fio":          Slot(1, 0.2460, 0.7125),
    "p1_passport":     Slot(1, 0.2245, 0.7280),
    "p1_birth":        Slot(1, 0.6440, 0.7280),

    # -- 2: Справка (Прил. N3, приказ 655) --------------------------------
    "p2_spravka_no":   Slot(2, 0.4040, 0.3525),
    "p2_fio":          Slot(2, 0.2490, 0.4365),

    # -- 3: Прил. №1 — letter-cells ---------------------------------------
    "p3_surname":      Slot(3, 0.2450, 0.3594, CELL_SIZE, pitch=0.0273, per_row=19),
    "p3_name":         Slot(3, 0.2450, 0.3903, CELL_SIZE, pitch=0.0273, per_row=19),
    "p3_patronymic":   Slot(3, 0.2450, 0.4217, CELL_SIZE, pitch=0.0273, per_row=19),
    "p3_citizenship":  Slot(3, 0.2712, 0.4554, CELL_SIZE, pitch=0.0273, per_row=18),
    "p3_birth_day":    Slot(3, 0.3105, 0.4874, CELL_SIZE, pitch=0.0252),
    "p3_birth_month":  Slot(3, 0.4120, 0.4874, CELL_SIZE, pitch=0.0264),
    "p3_birth_year":   Slot(3, 0.5135, 0.4874, CELL_SIZE, pitch=0.0273),
    "p3_pass_series":  Slot(3, 0.1580, 0.5765, CELL_SIZE, pitch=0.0273, per_row=6),
    "p3_pass_number":  Slot(3, 0.3840, 0.5765, CELL_SIZE, pitch=0.0274, per_row=10),
    "p3_issue_day":    Slot(3, 0.2365, 0.6223, CELL_SIZE, pitch=0.0282),
    "p3_issue_month":  Slot(3, 0.3185, 0.6223, CELL_SIZE, pitch=0.0298),
    "p3_issue_year":   Slot(3, 0.4030, 0.6223, CELL_SIZE, pitch=0.0287),
    "p3_issued_by":    Slot(3, 0.2418, 0.6714, CELL_SIZE, pitch=0.0273,
                            per_row=19, rows=2, wrap_x=0.0820, wrap_per_row=33),
    "p3_pat_series":   Slot(3, 0.1523, 0.7868, CELL_SIZE, pitch=0.0243, per_row=6),
    "p3_pat_number":   Slot(3, 0.3418, 0.7868, CELL_SIZE, pitch=0.0274, per_row=10),
    "p3_pat_day":      Slot(3, 0.6848, 0.7868, CELL_SIZE, pitch=0.0250),
    "p3_pat_month":    Slot(3, 0.7525, 0.7868, CELL_SIZE, pitch=0.0250),
    "p3_pat_year":     Slot(3, 0.8218, 0.7868, CELL_SIZE, pitch=0.0250),
    "p3_profession":   Slot(3, 0.0820, 0.8709, CELL_SIZE, pitch=0.0273,
                            per_row=33, rows=3),

    # -- 4: Прил. №1, оборот ----------------------------------------------
    "p4_fio":          Slot(4, 0.3010, 0.8660, 0.0135),
    "p4_day":          Slot(4, 0.1180, 0.9085),
    "p4_month":        Slot(4, 0.1840, 0.9105),
    "p4_year":         Slot(4, 0.3018, 0.9110),

    # -- 5: Трудовой договор, 1-бет ---------------------------------------
    "p5_date":         Slot(5, 0.7880, 0.0898),
    "p5_rep_fio_1":    Slot(5, 0.5890, 0.1478),
    "p5_rep_fio_2":    Slot(5, 0.0460, 0.1648),
    "p5_pat_series":   Slot(5, 0.4590, 0.2600),
    "p5_pat_number":   Slot(5, 0.5060, 0.2600),
    "p5_pat_date":     Slot(5, 0.5560, 0.2788),
    "p5_from":         Slot(5, 0.2440, 0.3518),
    "p5_to":           Slot(5, 0.4132, 0.3518),

    # -- 6: Трудовой договор, реквизиты -----------------------------------
    "p6_fio":          Slot(6, 0.2235, 0.8640),
    "p6_birth":        Slot(6, 0.2258, 0.8792),
    "p6_pass_no":      Slot(6, 0.2226, 0.8946),
    "p6_pass_issued":  Slot(6, 0.4420, 0.8940),
    "p6_organ":        Slot(6, 0.2226, 0.9105),
    "p6_initials":     Slot(6, 0.5185, 0.9412),

    # -- 7: Прил. №7, 1-бет — фирма доимийлари бланкада, ёзиладигани йўқ --

    # -- 8: Прил. №7 — ишчи катаклари -------------------------------------
    "p8_surname":      Slot(8, 0.2303, 0.3735, CELL_SIZE, pitch=0.0250, per_row=21),
    "p8_name":         Slot(8, 0.2303, 0.4045, CELL_SIZE, pitch=0.0250, per_row=21),
    "p8_patronymic":   Slot(8, 0.2303, 0.4353, CELL_SIZE, pitch=0.0250, per_row=21),
    "p8_citizenship":  Slot(8, 0.2560, 0.4722, CELL_SIZE, pitch=0.0250, per_row=20),
    "p8_birth_place":  Slot(8, 0.3320, 0.5062, CELL_SIZE, pitch=0.0250, per_row=17),
    # «ПАСПОРТ» in 2.7 is pre-printed on this blank — nothing to write there.
    # The 2.6 birth-date cells and the серия/№/дата row were measured off the
    # blank's own cell walls.
    "p8_birth_day":    Slot(8, 0.3115, 0.5825, CELL_SIZE, pitch=0.0250),
    "p8_birth_month":  Slot(8, 0.3865, 0.5825, CELL_SIZE, pitch=0.0250),
    "p8_birth_year":   Slot(8, 0.4610, 0.5825, CELL_SIZE, pitch=0.0252),
    "p8_pass_series":  Slot(8, 0.1625, 0.6788, CELL_SIZE, pitch=0.0242, per_row=4),
    "p8_pass_number":  Slot(8, 0.3600, 0.6788, CELL_SIZE, pitch=0.0250, per_row=10),
    "p8_issue_day":    Slot(8, 0.6832, 0.6788, CELL_SIZE, pitch=0.0250),
    "p8_issue_month":  Slot(8, 0.7578, 0.6788, CELL_SIZE, pitch=0.0250),
    "p8_issue_year":   Slot(8, 0.8318, 0.6788, CELL_SIZE, pitch=0.0248),
    "p8_issued_by":    Slot(8, 0.2303, 0.7395, CELL_SIZE, pitch=0.0250,
                            per_row=21, rows=2, row_step=0.0310),

    # -- 9: Прил. №7 — патент ----------------------------------------------
    "p9_pat_series":   Slot(9, 0.1505, 0.0880, CELL_SIZE, pitch=0.0250, per_row=6),
    "p9_pat_number":   Slot(9, 0.3543, 0.0885, CELL_SIZE, pitch=0.0250, per_row=10),
    "p9_pat_day":      Slot(9, 0.6848, 0.0880, CELL_SIZE, pitch=0.0250),
    "p9_pat_month":    Slot(9, 0.7565, 0.0880, CELL_SIZE, pitch=0.0250),
    "p9_pat_year":     Slot(9, 0.8298, 0.0880, CELL_SIZE, pitch=0.0258),
    "p9_pat_issuer":   Slot(9, 0.2488, 0.1338, CELL_SIZE, pitch=0.0233,
                            per_row=29, rows=2, wrap_x=0.0763,
                            wrap_per_row=34, wrap_pitch=0.0250,
                            row_step=0.0250),
    "p9_valid_day":    Slot(9, 0.2560, 0.2000, CELL_SIZE, pitch=0.0258),
    "p9_valid_month":  Slot(9, 0.3294, 0.2000, CELL_SIZE, pitch=0.0258),
    "p9_valid_year":   Slot(9, 0.4043, 0.2000, CELL_SIZE, pitch=0.0258),
    "p9_until_day":    Slot(9, 0.5550, 0.2000, CELL_SIZE, pitch=0.0258),
    "p9_until_month":  Slot(9, 0.6275, 0.2000, CELL_SIZE, pitch=0.0258),
    "p9_until_year":   Slot(9, 0.7041, 0.2000, CELL_SIZE, pitch=0.0266),
    # 3.2 профессия is pre-printed on the firm's blank, like all of page 7
    "p9_deal_day":     Slot(9, 0.5800, 0.7028, CELL_SIZE, pitch=0.0258),
    "p9_deal_month":   Slot(9, 0.6549, 0.7028, CELL_SIZE, pitch=0.0266),
    "p9_deal_year":    Slot(9, 0.7307, 0.7028, CELL_SIZE, pitch=0.0266),

    # -- 10: Прил. №7, охирги — сана --------------------------------------
    "p10_day":         Slot(10, 0.1010, 0.2645),
    "p10_month":       Slot(10, 0.2090, 0.2628),
    "p10_year":        Slot(10, 0.3870, 0.2634),
}

#: How many pages a full packet has. A template with fewer is refused with a
#: sentence rather than an IndexError.
PAGE_COUNT = 10

#: The professions the office actually hires for — the combo's starting list;
#: the operator can type any other.
PROFESSIONS: tuple[str, ...] = (
    "ПОДСОБНЫЙ РАБОЧИЙ",
    "РАЗНОРАБОЧИЙ",
    "УБОРЩИК ПРОИЗВОДСТВЕННЫХ И СЛУЖЕБНЫХ ПОМЕЩЕНИЙ",
    "ГРУЗЧИК",
    "ШТУКАТУР",
    "МАЛЯР",
)

#: Russian months in the genitive — «28 ИЮЛЯ 2026».
MONTHS_RU: tuple[str, ...] = (
    "ЯНВАРЯ", "ФЕВРАЛЯ", "МАРТА", "АПРЕЛЯ", "МАЯ", "ИЮНЯ",
    "ИЮЛЯ", "АВГУСТА", "СЕНТЯБРЯ", "ОКТЯБРЯ", "НОЯБРЯ", "ДЕКАБРЯ",
)

#: On page 5 the citizenship + ФИО run into the paragraph's designed gap: what
#: fits stays on the line, the rest starts the next line. Measured budget.
P5_LINE_BUDGET = 34
