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
    #: plain text only: never run past this page-x — the value shrinks and
    #: squeezes to fit, so a long ФИО stops colliding with the form's own
    #: words printed right after the gap (0 → no limit)
    right_edge: float = 0.0


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

#: The section serves TWO МВД packets now: the Moscow one (the original ten
#: pages) and the Московская область one — same worker fields, same look, but
#: an eleven-page packet in a different order, so it carries its own slot map.
REGIONS: tuple[str, ...] = ("moscow", "oblast")
REGION_TITLES: dict[str, str] = {"moscow": "МОСКВА",
                                 "oblast": "МОСКОВСКАЯ ОБЛАСТЬ"}
PAGE_COUNTS: dict[str, int] = {"moscow": 10, "oblast": 11}

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


#: The Московская область packet, measured off the office's filled sample.
#:
#: FIRST-PASS positions: there was no empty twin to pixel-diff against, so
#: these anchors were read off the filled pages by hand and by the bold-ink
#: bands. The office uploads its own blank and drags everything true with
#: «📐 Матнларни жойлаш» — which is exactly what the owner said he will do.
#: Page order: Прил.№7 (стр.1 фирма — nothing ours; стр.2 worker cells;
#: стр.3 patent; стр.4 sign date), 5 empty, Прил.№1 (стр.6 cells, стр.7
#: dates + confirm), договор (8, 9), справка №3 (10), справка о приеме (11).
OBLAST_SLOTS: dict[str, Slot] = {
    # -- 2: Прил.№7 — ишчи катаклари --------------------------------------
    "o2_surname":      Slot(2, 0.2280, 0.3845, CELL_SIZE, pitch=0.0242, per_row=22),
    "o2_name":         Slot(2, 0.2280, 0.4130, CELL_SIZE, pitch=0.0242, per_row=22),
    "o2_patronymic":   Slot(2, 0.2280, 0.4415, CELL_SIZE, pitch=0.0242, per_row=22),
    "o2_citizenship":  Slot(2, 0.1830, 0.4805, CELL_SIZE, pitch=0.0242, per_row=24),
    "o2_birth_place":  Slot(2, 0.3270, 0.5115, CELL_SIZE, pitch=0.0242, per_row=20),
    "o2_birth_day":    Slot(2, 0.3060, 0.5830, CELL_SIZE, pitch=0.0250),
    "o2_birth_month":  Slot(2, 0.3790, 0.5830, CELL_SIZE, pitch=0.0250),
    "o2_birth_year":   Slot(2, 0.4470, 0.5830, CELL_SIZE, pitch=0.0250),
    "o2_doc_kind":     Slot(2, 0.4470, 0.6300, CELL_SIZE, pitch=0.0242, per_row=9),
    "o2_pass_series":  Slot(2, 0.1000, 0.6740, CELL_SIZE, pitch=0.0242, per_row=5),
    "o2_pass_number":  Slot(2, 0.3310, 0.6740, CELL_SIZE, pitch=0.0250, per_row=10),
    "o2_issue_day":    Slot(2, 0.7260, 0.6740, CELL_SIZE, pitch=0.0250),
    "o2_issue_month":  Slot(2, 0.8020, 0.6740, CELL_SIZE, pitch=0.0250),
    "o2_issue_year":   Slot(2, 0.8600, 0.6740, CELL_SIZE, pitch=0.0250),
    "o2_issued_by":    Slot(2, 0.1660, 0.7340, CELL_SIZE, pitch=0.0242,
                            per_row=26, rows=2, wrap_x=0.1000,
                            wrap_per_row=30, row_step=0.0300),

    # -- 3: Прил.№7 — патент ----------------------------------------------
    "o3_pat_kind":     Slot(3, 0.3020, 0.1615, CELL_SIZE, pitch=0.0242, per_row=7),
    "o3_pat_series":   Slot(3, 0.1000, 0.1970, CELL_SIZE, pitch=0.0242, per_row=6),
    "o3_pat_number":   Slot(3, 0.2570, 0.1970, CELL_SIZE, pitch=0.0242, per_row=10),
    "o3_pat_day":      Slot(3, 0.6670, 0.1970, CELL_SIZE, pitch=0.0250),
    "o3_pat_month":    Slot(3, 0.7270, 0.1970, CELL_SIZE, pitch=0.0250),
    "o3_pat_year":     Slot(3, 0.8000, 0.1970, CELL_SIZE, pitch=0.0250),
    "o3_pat_issuer":   Slot(3, 0.2600, 0.2405, CELL_SIZE, pitch=0.0242,
                            per_row=22, rows=2, wrap_x=0.0940,
                            wrap_per_row=30, wrap_pitch=0.0250,
                            row_step=0.0235),
    "o3_valid_day":    Slot(3, 0.1500, 0.3000, CELL_SIZE, pitch=0.0258),
    "o3_valid_month":  Slot(3, 0.2130, 0.3000, CELL_SIZE, pitch=0.0258),
    "o3_valid_year":   Slot(3, 0.2760, 0.3000, CELL_SIZE, pitch=0.0258),
    "o3_until_day":    Slot(3, 0.4620, 0.3000, CELL_SIZE, pitch=0.0258),
    "o3_until_month":  Slot(3, 0.5250, 0.3000, CELL_SIZE, pitch=0.0258),
    "o3_until_year":   Slot(3, 0.5880, 0.3000, CELL_SIZE, pitch=0.0258),
    "o3_profession":   Slot(3, 0.0890, 0.6020, CELL_SIZE, pitch=0.0242,
                            per_row=33, rows=3, row_step=0.0260),
    "o3_deal_day":     Slot(3, 0.5800, 0.8000, CELL_SIZE, pitch=0.0258),
    "o3_deal_month":   Slot(3, 0.6400, 0.8000, CELL_SIZE, pitch=0.0258),
    "o3_deal_year":    Slot(3, 0.7000, 0.8000, CELL_SIZE, pitch=0.0258),

    # -- 4: Прил.№7 — имзо санаси -----------------------------------------
    "o4_day":          Slot(4, 0.1000, 0.2470),
    "o4_month":        Slot(4, 0.1550, 0.2470),
    "o4_year":         Slot(4, 0.3250, 0.2470),

    # -- 6: Прил.№1 — ишчи катаклари --------------------------------------
    # page 6's grid was measured box-by-box off the owner's own ПОДОЛЬСК
    # blank — its cells run a 0.0274 pitch, not the первый черновик's 0.0242,
    # which is why long values drifted onto the borders
    "o6_surname":      Slot(6, 0.1715, 0.3927, CELL_SIZE, pitch=0.0274, per_row=27),
    "o6_name":         Slot(6, 0.1715, 0.4195, CELL_SIZE, pitch=0.0274, per_row=27),
    "o6_patronymic":   Slot(6, 0.2538, 0.4469, CELL_SIZE, pitch=0.0274, per_row=24),
    "o6_citizenship":  Slot(6, 0.2247, 0.4834, CELL_SIZE, pitch=0.0274, per_row=25),
    "o6_birth_day":    Slot(6, 0.2804, 0.5290, CELL_SIZE, pitch=0.0282),
    "o6_birth_month":  Slot(6, 0.3917, 0.5290, CELL_SIZE, pitch=0.0274),
    "o6_birth_year":   Slot(6, 0.4739, 0.5290, CELL_SIZE, pitch=0.0277),
    "o6_doc_kind":     Slot(6, 0.4739, 0.5672, CELL_SIZE, pitch=0.0274, per_row=16),
    "o6_pass_series":  Slot(6, 0.1699, 0.6015, CELL_SIZE, pitch=0.0277, per_row=7),
    "o6_pass_number":  Slot(6, 0.3917, 0.6015, CELL_SIZE, pitch=0.0275, per_row=9),
    # this form runs the issue date as ONE row of eight boxes — ДДММГГГГ
    "o6_issue_all":    Slot(6, 0.6956, 0.6015, CELL_SIZE, pitch=0.0275, per_row=8),
    "o6_issued_by":    Slot(6, 0.1699, 0.6362, CELL_SIZE, pitch=0.0274,
                            per_row=27, rows=2, row_step=0.0319),
    "o6_pat_series":   Slot(6, 0.1699, 0.7343, CELL_SIZE, pitch=0.0277, per_row=5),
    "o6_pat_number":   Slot(6, 0.3368, 0.7343, CELL_SIZE, pitch=0.0275, per_row=10),
    "o6_pat_issue_all": Slot(6, 0.6956, 0.7343, CELL_SIZE, pitch=0.0275, per_row=8),
    "o6_profession":   Slot(6, 0.0909, 0.8073, CELL_SIZE, pitch=0.0274,
                            per_row=30, rows=3, row_step=0.0273),
    # section 4 — место осуществления трудовой деятельности; the blank
    # leaves it empty, the owner types the work address once and it stays
    "o6_address":      Slot(6, 0.0909, 0.9282, CELL_SIZE, pitch=0.0274,
                            per_row=30, rows=2, row_step=0.0382),

    # -- 7: Прил.№1 — саналар ва тасдиқ -----------------------------------
    "o7_deal_day":     Slot(7, 0.6250, 0.1000, CELL_SIZE, pitch=0.0242),
    "o7_deal_month":   Slot(7, 0.6850, 0.1000, CELL_SIZE, pitch=0.0242),
    "o7_deal_year":    Slot(7, 0.7450, 0.1000, CELL_SIZE, pitch=0.0242),
    "o7_fio":          Slot(7, 0.2900, 0.9370, 0.0128),
    "o7_day":          Slot(7, 0.0750, 0.9750),
    "o7_month":        Slot(7, 0.1500, 0.9750),
    "o7_year":         Slot(7, 0.2800, 0.9750),

    # -- 8: Трудовой договор, 1-бет ---------------------------------------
    "o8_date":         Slot(8, 0.7900, 0.1520),
    # the blank prints «, именуемый в дальнейшем» right after the gap — a
    # long ФИО shrinks into the gap instead of running over those words
    "o8_rep_fio_1":    Slot(8, 0.3100, 0.2620, right_edge=0.7750),
    "o8_rep_fio_2":    Slot(8, 0.0480, 0.2790),
    "o8_pat_series":   Slot(8, 0.4470, 0.3600),
    "o8_pat_number":   Slot(8, 0.4900, 0.3600),
    "o8_pat_issuer_1": Slot(8, 0.7400, 0.3600),
    "o8_pat_issuer_2": Slot(8, 0.1180, 0.3840),
    "o8_pat_date":     Slot(8, 0.4150, 0.3840),
    "o8_from":         Slot(8, 0.2400, 0.4460),
    "o8_to":           Slot(8, 0.3960, 0.4460),

    # -- 9: Трудовой договор, реквизиты -----------------------------------
    "o9_fio":          Slot(9, 0.2080, 0.7760),
    "o9_birth":        Slot(9, 0.2080, 0.7920),
    "o9_pass_no":      Slot(9, 0.2080, 0.8090),
    "o9_pass_issued":  Slot(9, 0.4780, 0.8090),
    "o9_organ":        Slot(9, 0.2080, 0.8250),
    "o9_initials":     Slot(9, 0.4870, 0.8600),

    # -- 10: Справка (655) -------------------------------------------------
    "o10_spravka_no":  Slot(10, 0.3500, 0.3280),
    "o10_fio":         Slot(10, 0.2980, 0.3960),
    # «Дата приема уведомления» — the label stood alone with no date after it
    "o10_accept_date": Slot(10, 0.4200, 0.5150),

    # -- 11: Справка о приеме (Прил. N2) ----------------------------------
    "o11_uved_no":     Slot(11, 0.3300, 0.3330),
    "o11_uved_ref":    Slot(11, 0.6000, 0.5560),
    "o11_accept_date": Slot(11, 0.2700, 0.6000),
    "o11_republic":    Slot(11, 0.5400, 0.6180),
    "o11_fio":         Slot(11, 0.1850, 0.6330),
    "o11_passport":    Slot(11, 0.2160, 0.6520),
    "o11_birth":       Slot(11, 0.5600, 0.6520),
}

SLOTS_BY_REGION: dict[str, dict[str, Slot]] = {
    "moscow": SLOTS,
    "oblast": OBLAST_SLOTS,
}
