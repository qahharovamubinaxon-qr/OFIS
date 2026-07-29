"""Where every value sits on the СЕРТИФИКАТ blank, and in what.

The blank is «Сертификат о владении русским языком, знании истории России и основ
законодательства Российской Федерации» — the certificate the office's own
учебный центр «СФЕРА» issues. It arrives as a two-page scan of the security
paper, so there is no text layer and nothing to line up against.

**Page 1 is never written on.** It is the reverse of the sheet — guilloche and
the hologram, no printing. Everything the operator types goes on **page 2**, the
printed side, and that is what these coordinates describe.

How the numbers were arrived at
-------------------------------
The blank's *own* printing was measured, not the filled sample: the barcode
bars, and the four labels «Город», «Регистрационный №», «Дата выдачи» and «Срок
действия до», and the six body lines of the right-hand column. Every value here
is then placed against one of those — centred on its label, or in the gap the
right-hand column leaves for the name. Measuring the blank rather than a
photograph of a filled one means the fit does not depend on how straight the
office's typist happened to have the sheet in the printer.

Coordinates are points on the 595.28 × 841.72 pt (A4) page the certificate was
scanned onto; ``baseline`` is the baseline, and ``centre`` is the middle of the
value, because every value on this blank is centred rather than ranged left.
"""

from __future__ import annotations

from typing import NamedTuple

#: The scan's page, and which of its two pages carries the values.
PAGE = (595.28, 841.72)
VALUE_PAGE = 1
BLANK_PAGE = 0

#: Liberation Sans is metric-compatible with the Arial the certificate's
#: typist uses; every typed value on this blank is bold.
SANS = "OfisArial"
SANS_BOLD = "OfisArialBold"

BLACK = (0.016, 0.016, 0.016)
#: Sampled off the barcode's own bars — the digits under them are printed in
#: the same ink, so they are set in the same colour rather than in black.
BARCODE_RED = (0.631, 0.067, 0.059)


class Slot(NamedTuple):
    """One value: the middle of it, its baseline, and what it is set in."""

    centre: float
    baseline: float
    size: float
    font: str = SANS_BOLD
    colour: tuple[float, float, float] = BLACK


# ----------------------------------------------------------- the right column
#
# «Настоящий сертификат удостоверяте, что» ends at baseline 96.25 and «сдал(а)
# экзамен» begins at 154.25; the holder's name goes in the gap between them, on
# two lines — Cyrillic as the passport spells it, Latin underneath, the way the
# passport itself carries both.

#: Every line of the right-hand column is centred on this axis. All six of the
#: blank's own printed lines agree on it to within half a point, so the name
#: hangs on the column the certificate itself is set to and not on an eye.
FIO_CENTRE = 437.6

FIO_CYRILLIC = Slot(FIO_CENTRE, 114.5, 12.0)
FIO_LATIN = Slot(FIO_CENTRE, 132.0, 11.0)

#: A name too long for the column is set smaller rather than run into the
#: border — the certificate is the holder's, so it is their whole name or none.
FIO_WIDTH = 248.0
FIO_MIN_SIZE = 7.5


# ------------------------------------------------------------ the left column

#: The barcode's bars, measured off the blank. The digits are laid out one to a
#: cell across exactly this width, which is how the printed ones read: a row of
#: separated figures, not a word.
BARCODE_BARS = (102.25, 272.00, 227.50, 290.25)
BARCODE_BASELINE = 300.90
BARCODE_SIZE = 7.5
BARCODE_DIGITS = 13

#: Centred under their own printed labels, both rows.
VALUES: dict[str, Slot] = {
    "city":         Slot(78.40, 332.00, 10.0),
    "reg_number":   Slot(213.90, 332.00, 10.0),
    "issued_on":    Slot(94.75, 370.80, 10.0),
    "valid_until":  Slot(205.25, 370.80, 10.0),
}

#: What the office's own certificate carried, so the very first run starts from
#: the office's block rather than from zero. Both numbers keep their leading
#: figures and re-roll only the last three — see
#: :func:`src.services.sertifikat_service.SertifikatService.roll`.
DEFAULT_REG_NUMBER = "002010264154"
DEFAULT_BARCODE = "0142400796702"
#: How many figures at the end are re-rolled for every certificate printed.
ROLL_DIGITS = 3
