"""КУК ПАТЕНТ — where each value goes on the card's two sides.

The office sent both sides filled in and drew a RED RULE under every value
that changes from worker to worker. Those rules were found by colour on a
400-dpi render and measured, and what is below is where each value sits: the
text stands ON its rule, so a value's baseline is the rule's own line.

Two maps, because the two sides say different things. The front names the
worker and carries his photograph; the back says where he is from, what
document he holds, which firm issued the card and on what day, and carries
the card's own number.

Everything is a share of the sheet, so the office's own scan prints right
whatever size it comes in — and every one of them can be dragged, resized,
recoloured and re-weighted in «📐 Созлаш», because a measurement off a scan
is a starting point and the office's own eye is the judge.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The blanks the office sent: a card on a landscape sheet.
PAGE_W, PAGE_H = 595.2, 411.1

INK = (0.0, 0.0, 0.0)
#: The card is printed in a bold serif — the office's own sample is Times.
FAMILY = "Times New Roman"
#: One size for the whole face of the card. Every value on it measured
#: between 0.0144 and 0.0169 of the sheet, which is one printed size read
#: through the noise of a scan.
SIZE = 0.0165
#: The card's own number, at the foot of the back, is set far larger.
CARD_SIZE = 0.0382
#: «Документ выдан» carries a firm's whole legal name and has one card's
#: width to do it in. The office's own sample sets it in a narrower face
#: than any installed here, so it is set smaller instead — measured against
#: its own rule, «…ответственностью ООО» must end at 0.659 and not past it.
FIRM_SIZE = 0.0146

#: «текстлар ва расм бироз хира қилинади, 85% ли бўлсин» — the office's own
#: words. Ink laid on at full strength sits ON the scan; at 85 % it sits IN
#: it, which is what a real card looks like.
OPACITY = 0.85

FRONT, BACK = "front", "back"
SIDES = (FRONT, BACK)
SIDE_NAMES = {FRONT: "Олди", BACK: "Орқаси"}


@dataclass(frozen=True)
class Slot:
    """One printed value: where it starts, how big, and how it sits."""

    x: float
    baseline: float
    size: float = SIZE
    bold: bool = True
    colour: tuple[float, float, float] = INK
    family: str = FAMILY
    sample: str = ""
    label: str = ""


#: ---- the front: who the worker is ------------------------------------
FRONT_SLOTS: dict[str, Slot] = {
    "series": Slot(0.5283, 0.4527, SIZE, True, INK, FAMILY,
                   "88", "Серия"),
    "number": Slot(0.5646, 0.4527, SIZE, True, INK, FAMILY,
                   "3259366", "Номер"),
    "surname": Slot(0.5289, 0.4895, SIZE, True, INK, FAMILY,
                    "Эргешов", "Фамилия"),
    "name": Slot(0.5310, 0.5670, SIZE, True, INK, FAMILY,
                 "Омурбек", "Имя"),
    "patronymic": Slot(0.5319, 0.6322, SIZE, True, INK, FAMILY,
                       "Куштарович", "Отчество"),
    "birth_date": Slot(0.5573, 0.6913, SIZE, True, INK, FAMILY,
                       "16.06.1998", "Дата рождения"),
    "gender": Slot(0.6320, 0.6913, SIZE, True, INK, FAMILY,
                   "М", "Пол"),
}

#: ---- the back: where he is from and who issued the card --------------
#: «Документ выдан» runs to TWO lines, because the firm's full name does
#: not fit on one — the office wrote it that way on its own sample.
BACK_SLOTS: dict[str, Slot] = {
    "citizenship": Slot(0.4109, 0.3368, SIZE, True, INK, FAMILY,
                        "Киргизия", "Гражданство"),
    "document": Slot(0.4989, 0.4039, SIZE, True, INK, FAMILY,
                     "Иностранный паспорт ID3956001",
                     "Документ, удостоверяющий личность"),
    "firm1": Slot(0.4249, 0.4972, FIRM_SIZE, True, INK, FAMILY,
                  "Общество с ограниченной ответственностью ООО",
                  "Документ выдан — 1-қатор"),
    "firm2": Slot(0.4294, 0.5164, FIRM_SIZE, True, INK, FAMILY,
                  '"Сфера" отдел кадров', "Документ выдан — 2-қатор"),
    "issued": Slot(0.4037, 0.5475, SIZE, True, INK, FAMILY,
                   "03.09.2024", "Дата выдачи"),
    "card_no": Slot(0.5225, 0.6145, CARD_SIZE, False, INK, FAMILY,
                    "АА3915699", "Картанинг рақами"),
}

SLOTS: dict[str, dict[str, Slot]] = {FRONT: FRONT_SLOTS, BACK: BACK_SLOTS}

#: How far the second «Документ выдан» line sits under the first.
FIRM_LINE_GAP = 0.0192

#: The white 3×4 window on the front, as «left, top, width, height».
#: Measured off the blank itself: 67.3 × 92.2 pt, which is 3:4 to within a
#: scan's accuracy.
PHOTO_DEFAULT = (0.3694, 0.4413, 0.1131, 0.2242)
PHOTO_KEY = "img_photo"
PHOTO_LABEL = "🖼 ИШЧИНИНГ РАСМИ"


def slots_of(side: str) -> dict[str, Slot]:
    return SLOTS.get(side, FRONT_SLOTS)
