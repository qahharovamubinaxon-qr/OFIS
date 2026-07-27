"""Code 128 barcode rendering — no third-party dependency.

The ДМС policy carries its number as a Code 128 barcode with the digits printed
underneath. Rather than pull in a barcode package, the ~100 standard patterns
live here and the bars are drawn straight into the PDF as filled rectangles, so
they stay crisp at any print resolution (a raster image would not).
"""

from __future__ import annotations

# Width patterns for Code 128 values 0…106 (bar, space, bar, space, bar, space).
# The last entry is the stop pattern and carries an extra final bar.
_PATTERNS = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()

_START_B = 104
_STOP = 106


def code128_values(text: str) -> list[int]:
    """Code 128-B values for ``text`` (printable ASCII), with the checksum."""
    if not text or any(not 32 <= ord(c) <= 126 for c in text):
        raise ValueError("Code 128-B accepts printable ASCII only")
    values = [_START_B] + [ord(c) - 32 for c in text]
    checksum = values[0]
    for i, v in enumerate(values[1:], start=1):
        checksum += i * v
    values.append(checksum % 103)
    values.append(_STOP)
    return values


def code128_modules(text: str) -> list[int]:
    """Bar/space run lengths in modules, starting with a bar."""
    runs: list[int] = []
    for value in code128_values(text):
        runs.extend(int(c) for c in _PATTERNS[value])
    return runs


def draw_code128(page, text: str, rect, *, quiet_zone: int = 10) -> None:
    """Draw ``text`` as a Code 128-B barcode filling ``rect`` on ``page``.

    ``rect`` is a fitz.Rect; the bars span its full height. A quiet zone of
    ``quiet_zone`` modules is kept on each side, as the symbology requires.
    """
    runs = code128_modules(text)
    total = sum(runs) + 2 * quiet_zone
    unit = rect.width / total

    x = rect.x0 + quiet_zone * unit
    is_bar = True
    for run in runs:
        width = run * unit
        if is_bar:
            page.draw_rect(
                _rect_like(rect, x, x + width), color=None, fill=(0, 0, 0))
        x += width
        is_bar = not is_bar


def _rect_like(rect, x0: float, x1: float):
    import fitz

    return fitz.Rect(x0, rect.y0, x1, rect.y1)
