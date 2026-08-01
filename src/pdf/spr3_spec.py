"""3-СПРАВКА — a six-page certificate packet on the firm's own blank.

Pages 2 and 4 of the template are empty; pages 1, 3, 5 and 6 carry the black
worker texts: the ФИО (in Russian, read off the patent or миграционная карта),
the birth date, the passport, the citizenship, and the validity dates — the
start date the operator picks, repeated the same on every printed page, and
the end worked out as one year minus a day. The address the operator types
lands on page 5.

FIRST-PASS positions. The blank the owner sent vanished off OneDrive before
it could be opened, so each printed page starts with the same sensibly-stacked
block — and the owner drags every page true with «📐 Матнларни жойлаш», which
is what he said he would do («ХАММА САҲИФАНИ БИРМА-БИР ТЎҒИРЛАБ ЧИҚАМАН»).
Once a real sample arrives these numbers can be measured properly.

Positions are shares of the page, the house convention.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The certificate is set in Times; sizes are uniform («РАЗМЕР ШРИФТ БИРГА
#: БИР») and adjustable per value in the editor.
FONT = "OfisSerifBold"

TEXT_SIZE = 0.0128
TEXT_OPACITY = 0.9

PAGE_COUNT = 6

#: The pages that carry text at all — 2 and 4 stay untouched.
PRINTED_PAGES: tuple[int, ...] = (1, 3, 5, 6)


@dataclass(frozen=True)
class Slot:
    page: int
    x: float
    baseline: float
    size: float = TEXT_SIZE


def _page_block(page: int) -> dict[str, Slot]:
    """The standard block a справка repeats: who, born, passport, dates."""
    return {
        f"p{page}_fio":         Slot(page, 0.150, 0.300),
        f"p{page}_birth":       Slot(page, 0.150, 0.340),
        f"p{page}_passport":    Slot(page, 0.150, 0.380),
        f"p{page}_citizenship": Slot(page, 0.150, 0.420),
        f"p{page}_from":        Slot(page, 0.150, 0.460),
        f"p{page}_to":          Slot(page, 0.380, 0.460),
    }


SLOTS: dict[str, Slot] = {}
for _page in PRINTED_PAGES:
    SLOTS.update(_page_block(_page))
#: the address the operator types goes to page 5, the owner said
SLOTS["p5_address"] = Slot(5, 0.150, 0.520)
