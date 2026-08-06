"""МЕД КНИЖКА — where every mark sits, measured off the office's own pages.

The office sent four finished pages it makes by hand today. Nothing here
was guessed: each page was split by colour — blue for the dates, red for
the book number, grey for the typed block — and every cluster of ink was
boxed, so the program writes where the office already writes.

The sheet is the office's own 2160 × 3840 pt, so what comes out of the
printer lands on the booklet exactly as its own pages do. Everything is
kept as a SHARE of the page, so «📐 Созлаш» can nudge any of it and a
different printer is a drag, not a code change.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The office's own page. Kept to the point so a print lines up 1:1.
PAGE_W, PAGE_H = 2160.0, 3840.0
PAGES = 4

#: The three inks, taken from the darkest core of the office's own marks.
BLUE = (0.000, 0.055, 0.740)
RED = (0.733, 0.005, 0.132)
GREY = (0.482, 0.435, 0.428)

#: The two faces its pages are set in — both installed on the office's
#: machine, both looked up by the name the font picker shows.
TYPEWRITER = "Courier New"
HANDWRITING = "Adobe Handwriting Ernie"


@dataclass(frozen=True)
class Slot:
    """One printed mark: which page, where, how big, and how it is turned."""

    page: int
    x: float
    baseline: float
    size: float
    colour: tuple[float, float, float] = BLUE
    family: str = TYPEWRITER
    bold: bool = True
    #: 0 upright, 90 reading upwards, 270 reading downwards
    rotate: int = 0
    #: "left" | "centre" — the office's marks are set from their left edge
    align: str = "left"
    sample: str = ""
    label: str = ""


#: ---- 1-бет: the holder's own page ------------------------------------
#: The photo box, as the office pastes it.
PHOTO = (0.5440, 0.2437, 0.7342, 0.3860)

PAGE1: dict[str, Slot] = {
    "exam_date": Slot(1, 0.2573, 0.4850, 0.0173, BLUE, TYPEWRITER, True, 0,
                      "left", "05 АВГ 2026", "1-бет — кўрик санаси (кўк)"),
    "surname": Slot(1, 0.3556, 0.5844, 0.0124, GREY, TYPEWRITER, False, 0,
                    "left", "Расулов", "1-бет — фамилия"),
    "given": Slot(1, 0.3538, 0.6084, 0.0124, GREY, TYPEWRITER, False, 0,
                  "left", "Азиз Расулжон Угли", "1-бет — исм ва отчество"),
    "birth_year": Slot(1, 0.3556, 0.6346, 0.0124, GREY, TYPEWRITER, False, 0,
                       "left", "1992", "1-бет — туғилган йил"),
    "city": Slot(1, 0.3542, 0.6607, 0.0124, GREY, TYPEWRITER, False, 0,
                 "left", "Москва", "1-бет — адрес"),
    "position": Slot(1, 0.3640, 0.7177, 0.0124, GREY, TYPEWRITER, False, 0,
                     "left", "Помощник повара", "1-бет — лавозими"),
    "hash1": Slot(1, 0.1244, 0.6101, 0.0155, RED, TYPEWRITER, True, 270,
                  "left", "№", "1-бет — «№» белгиси (қизил)"),
    "number1": Slot(1, 0.1287, 0.6360, 0.0155, RED, TYPEWRITER, True, 270,
                    "left", "8832888", "1-бет — китоб рақами (қизил)"),
}

#: ---- 2-бет: the hygiene-training page ---------------------------------
PAGE2: dict[str, Slot] = {
    "trained_from": Slot(2, 0.6333, 0.2198, 0.0138, BLUE, TYPEWRITER, True, 0,
                         "left", "05. 08. 2026", "2-бет — бошланиш санаси"),
    "trained_to": Slot(2, 0.6896, 0.3247, 0.0138, BLUE, TYPEWRITER, True, 270,
                       "left", "05. 08. 2027", "2-бет — тугаш санаси (тик)"),
    "position_hand": Slot(2, 0.6684, 0.3060, 0.0169, BLUE, HANDWRITING, False,
                          270, "left", "помощник повара",
                          "2-бет — лавозими (қўлёзма)"),
}

#: ---- 3-бет: the examination page --------------------------------------
PAGE3: dict[str, Slot] = {
    "exam_date3": Slot(3, 0.3196, 0.6567, 0.0173, BLUE, TYPEWRITER, True, 270,
                       "left", "05 АВГ 2026", "3-бет — кўрик санаси"),
    "hash3": Slot(3, 0.1102, 0.6084, 0.0155, RED, TYPEWRITER, True, 270,
                  "left", "№", "3-бет — «№» белгиси"),
    "number3": Slot(3, 0.1120, 0.6378, 0.0155, RED, TYPEWRITER, True, 270,
                    "left", "8832888", "3-бет — китоб рақами"),
}

#: ---- 4-бет: the doctors' page -----------------------------------------
#: Thirteen dated lines, each measured off the office's own page. They all
#: carry the SAME date, so the office types it once.
PAGE4_ROWS: tuple[tuple[float, float], ...] = (
    (0.6240, 0.3123), (0.3884, 0.3135), (0.1991, 0.3226),
    (0.4658, 0.6620), (0.5824, 0.6623), (0.6222, 0.6695),
    (0.5444, 0.6699), (0.3884, 0.6701), (0.4291, 0.6704),
    (0.5029, 0.6724), (0.3158, 0.6726), (0.3518, 0.6730),
    (0.2800, 0.6733),
)
PAGE4: dict[str, Slot] = {
    f"visit{i + 1}": Slot(4, x, y, 0.0166, BLUE, TYPEWRITER, True, 270,
                          "left", "05 АВГ 2026", f"4-бет — {i + 1}-шифокор")
    for i, (x, y) in enumerate(PAGE4_ROWS)
}
PAGE4.update({
    "hash4": Slot(4, 0.1102, 0.6084, 0.0155, RED, TYPEWRITER, True, 270,
                  "left", "№", "4-бет — «№» белгиси"),
    "number4": Slot(4, 0.1120, 0.6378, 0.0155, RED, TYPEWRITER, True, 270,
                    "left", "8832888", "4-бет — китоб рақами"),
})

ALL_SLOTS: dict[str, Slot] = {**PAGE1, **PAGE2, **PAGE3, **PAGE4}

#: Every mark that shows the book's own number — one value, many places.
NUMBER_KEYS = ("number1", "number3", "number4")
HASH_KEYS = ("hash1", "hash3", "hash4")
#: Every mark that shows the examination date.
EXAM_KEYS = ("exam_date", "exam_date3", *(f"visit{i}" for i in range(1, 14)))

#: «05 АВГ 2026» — the three letters the booklet's own stamps use.
MONTHS_SHORT = ("ЯНВ", "ФЕВ", "МАР", "АПР", "МАЙ", "ИЮН",
                "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК")
