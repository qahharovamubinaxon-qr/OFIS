"""Where every value sits on the МИГ «ИШЧИ КАРТАСИ», as fractions of the page.

The card is a typewritten A4 form the office prints for each firm it works for.
Everything on it is set in **Courier New** — monospaced — which is what lets the
spaced-out letters of a surname line up the way the office types them.

Fractions rather than points, because each firm hands over its own scan of the
blank and no two are exactly the same size. A fraction lands correctly on
whatever comes in.

MEASURED, not judged. The office handed over its own card twice — empty and
filled — framed identically, so subtracting one from the other left exactly the
ink of each value. Every size below was then solved numerically: the text the
program prints was rendered at a trial size, its ink box measured the same way,
and the size adjusted until the two matched. The four name rows all came out at
the same size on their own, which is the check that the method worked.

ЎЗГАРТИРИШ ЙЎРИҚНОМАСИ (эга ўзи учун)
======================================

Ҳар сатр шундай кўринади::

    "surname":  Slot(0.3141, 0.2601, 0.0226, BLACK, width=0.66, spaced=True)
                     ^^^^^^  ^^^^^^  ^^^^^^
                       x    baseline  ўлчам

* **x** — ЧАПДАН қанча узоқда. Каттароқ = **ЎНГГА** суради,
  кичикроқ = **ЧАПГА**. 0.0 — варақнинг чап чети, 1.0 — ўнг чети.
* **baseline** — ТЕПАДАН қанча пастда, ёзувнинг ПАСТКИ чизиғи.
  Каттароқ = **ПАСТГА** суради, кичикроқ = **ТЕПАГА**.
  0.0 — варақнинг тепаси, 1.0 — паст чети.
* **ўлчам** — ҳарфнинг катталиги. Каттароқ = **йирикроқ ёзув**.

Қанчага суриш керак? A4 варақда **0.001 ≈ бир текис миллиметр**:

* 1 мм ўнгга — **x** га ``0.0017`` қўш
* 1 мм пастга — **baseline** га ``0.0012`` қўш
* ёзувни бир оз йириклаштириш — **ўлчам** ни ``0.001`` га ошир
  (тахминан 1 нуқта)

Мисол — фамилия 2 мм пастга ва бир оз ўнгга керак бўлса::

    "surname":  Slot(0.3175, 0.2625, 0.0226, ...)
                     +0.0034  +0.0024

``width=`` — фақат ЧЕГАРА: ёзув шундан кенг чиқса ўзи кичраяди.
Ёзув кичрайиб қолса — ``width`` ни оширинг, ўлчамни эмас.

``JOBS`` даги ``Rule(x0, x1, y)`` — иш ўрни тагидаги чизиқ:
``x0`` чап учи, ``x1`` ўнг учи, ``y`` баландлиги.

**МУҲИМ**: бу файлни ўзгартиргандан кейин EXE ни ҲАР САФАР қайта
йиғиш керак::

    cd "C:\\Users\\NEXT NOUT\\Desktop\\OFIS" ; .\\update.bat
"""

from __future__ import annotations

from typing import NamedTuple

#: Courier New. Monospaced, so a line's width is its length times one advance.
MONO = "OfisMono"
#: Akshar Regular — the face the office stamps the issue date in.
AKSHAR = "OfisAkshar"
#: Times New Roman italic — the code the office writes round that date.
TIMES = "OfisSerifItalic"

BLACK = (0.05, 0.05, 0.05)
#: The blue the office asked for the issue date in — #4856dd.
BLUE = (0x48 / 255, 0x56 / 255, 0xDD / 255)

#: Everything is set a shade heavier than the plain face, the way a typewriter
#: strikes: the outline is stroked as well as filled. Not a bold face — the
#: office asked for «бироз жирний», and Courier Bold is a different, wider
#: design that would not line up with the boxes.
#:
#: PyMuPDF takes this as a SHARE OF THE TYPE SIZE, not as points. Passed in
#: points it strokes each glyph so thickly the letters run into one another and
#: the card comes out as blots — which is exactly what happened once.
STROKE_SHARE = 0.030


class Slot(NamedTuple):
    """One value: where it starts, its baseline, its size, and what colour."""

    x: float
    baseline: float
    size: float
    colour: tuple[float, float, float] = BLACK
    #: widest the value may be before it is set smaller, as a share of the page
    width: float = 0.40
    #: letters set apart, «Ж А Х О Н...», the way the card is typed
    spaced: bool = False
    #: which face to set it in — the card is Courier, its issue date Akshar
    font: str = MONO


#: Sizes, each solved from the office's own filled card.
_CARD_NO = 0.0362      # СЕРИЯ and НОМЕР — the big line
_BODY = 0.0226         # the four name rows
_BIRTH = 0.0246
_PASSPORT = 0.0172
_VISA = 0.0168
_TERM = 0.0180
_ISSUED = 0.0270
_SEX = 0.0338
_CODE = 0.0227

FIELDS: dict[str, Slot] = {
    # the card's own series and number — the office types these
    "series":      Slot(0.4922, 0.1712, _CARD_NO, BLACK, width=0.30),
    "number":      Slot(0.4922, 0.2187, _CARD_NO, BLACK, width=0.36),
    # off the passport, every letter standing apart
    "surname":     Slot(0.3141, 0.2601, _BODY, BLACK, width=0.66, spaced=True),
    "surname_lat": Slot(0.3140, 0.2913, _BODY, BLACK, width=0.66, spaced=True),
    "name":        Slot(0.3136, 0.3224, _BODY, BLACK, width=0.68, spaced=True),
    "patronymic":  Slot(0.3136, 0.3535, _BODY, BLACK, width=0.68, spaced=True),
    "birth_date":  Slot(0.0674, 0.4774, _BIRTH, BLACK, width=0.40, spaced=True),
    "citizenship": Slot(0.4720, 0.4774, _BIRTH, BLACK, width=0.52, spaced=True),
    "passport":    Slot(0.0611, 0.5655, _PASSPORT, BLACK, width=0.42, spaced=True),
    # the office types these
    "visa":        Slot(0.4877, 0.5490, _VISA, BLACK, width=0.30),
    "valid_from":  Slot(0.1751, 0.7634, _TERM, BLACK, width=0.24),
    "valid_to":    Slot(0.4722, 0.7634, _TERM, BLACK, width=0.24),
    #: the day the card was issued — «15 03 26», in blue. NOT letter-spaced:
    #: the office writes the pairs together.
    "issued":      Slot(0.1938, 0.8696, _ISSUED, BLUE, width=0.34,
                        font=AKSHAR),
    #: The office's own code — the same 3 or 4 digits at all FOUR corners
    #: round the issue date, in Times New Roman italic.
    "code_tl":     Slot(0.1390, 0.7890, _CODE, BLUE, width=0.14, font=TIMES),
    "code_tr":     Slot(0.4940, 0.7890, _CODE, BLUE, width=0.14, font=TIMES),
    "code_bl":     Slot(0.1390, 0.9380, _CODE, BLUE, width=0.14, font=TIMES),
    "code_br":     Slot(0.4940, 0.9380, _CODE, BLUE, width=0.14, font=TIMES),
}

#: The four places that code is printed, in reading order.
CODE_SLOTS = ("code_tl", "code_tr", "code_bl", "code_br")

#: The «МУЖ» and «ЖЕН» boxes. One «X» goes in whichever the passport says.
SEX_X = {
    "male":   Slot(0.6204, 0.4143, _SEX),
    "female": Slot(0.8800, 0.4131, _SEX),
}


class Rule(NamedTuple):
    """A line drawn under one of the four jobs, corner to corner of the word."""

    x0: float
    x1: float
    y: float


#: The four places a worker can hold, in the order they are printed on the card.
#: Ticking one draws a line under that word — that is how the office marks it.
JOBS: tuple[tuple[str, str, Rule], ...] = (
    ("kom", "КОМ АДМИНИСТРАТОР", Rule(0.0551, 0.2746, 0.6524)),
    ("uchenik", "УЧЕНИК", Rule(0.0543, 0.1560, 0.6720)),
    ("raznorabochiy", "РАЗНОРАБОЧИЙ", Rule(0.2260, 0.4032, 0.6720)),
    ("chastniy", "ЧАСТНЫЙ ИШЧИ.", Rule(0.0559, 0.2070, 0.6952)),
)

#: How thick that line is, as a share of the page height.
RULE_WIDTH = 0.0014

#: Laid on just under full strength, so the type sits IN the paper rather than
#: on top of it — the rest of the program prints this way and a solid black
#: overprint gives a program-filled sheet away at a glance.
TEXT_OPACITY = 0.88

#: Where a firm's stamp goes when it has never been placed: middle-left, over
#: «М.П.», at about a third of the page across. (left, top, right, bottom).
DEFAULT_STAMP = (0.10, 0.80, 0.34, 0.97)
#: A stamp is drawn as it comes. PyMuPDF has no opacity for an image, so a
#: stamp that must let the card's type show through has to be a PNG with a
#: transparent background — which is what a scanned stamp is cut out to be, and
#: what the screen tells the operator to upload.
