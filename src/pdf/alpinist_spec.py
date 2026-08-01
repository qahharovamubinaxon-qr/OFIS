"""АЛПИНИСТ — the industrial climber's card, measured off the owner's sample.

The card is landscape (842×632 pt), two pages. The filled sample against its
own empty twin gave every value's spot:

* page 1 — «УДОСТОВЕРЕНИЕ № …», the worker's ФИО in three bold lines, the
  photo in its printed 3:4 frame, «Дата выдачи» and «Действительно до»
  (always three years apart), and the owner's hand-drawn signature in ink;
* page 2 — the blank's own number before the start date on the
  «Основание: протокол № …» line.

Texts are Times Bold like the sample. Images (the photo, the signature, the
печать) live in IMG_SLOTS: ``x`` is the left edge, ``baseline`` the BOTTOM
edge and ``size`` the height — the same manner the text slots use, so the
same layout editor moves and resizes them.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT = "OfisSerifBold"
TEXT_OPACITY = 0.94

#: The card is two pages: face and back.
PAGE_COUNT = 2

#: The printed photo frame on page 1 — its interior, off the blank itself.
#: Width over height ≈ 0.73, the «3×4» the owner asked the photo cut to.
PHOTO_RATIO = 0.7305

#: The ink the worker signs with — measured off the sample's signature.
INK_RGB = (61, 49, 162)


@dataclass(frozen=True)
class Slot:
    page: int
    x: float
    baseline: float
    size: float


#: The texts, measured off the filled sample.
SLOTS: dict[str, Slot] = {
    "p1_number":         Slot(1, 0.6659, 0.3484, 0.0391),
    "p1_fio_surname":    Slot(1, 0.4259, 0.4638, 0.0390),
    "p1_fio_name":       Slot(1, 0.4265, 0.5177, 0.0390),
    "p1_fio_patronymic": Slot(1, 0.4259, 0.5762, 0.0390),
    "p1_issued":         Slot(1, 0.4898, 0.7113, 0.0294),
    "p1_until":          Slot(1, 0.6762, 0.7113, 0.0294),
    "p2_protocol":       Slot(2, 0.3905, 0.6295, 0.0298),
}

#: The pictures. The photo's default IS the printed frame (x 0.1556–0.3851,
#: y 0.3606–0.7792); the signature sits right of «Подпись владельца»; the
#: печать's default matches where the sample's stamp stands on the back.
IMG_SLOTS: dict[str, Slot] = {
    "img_photo": Slot(1, 0.1556, 0.7792, 0.4186),
    "img_sign":  Slot(1, 0.6720, 0.8000, 0.0900),
    "img_stamp": Slot(2, 0.2300, 0.6900, 0.4000),
}

#: What the layout editor shows in an image's place while arranging.
IMG_LABELS = {"img_photo": "🖼 РАСМ", "img_sign": "✒ ИМЗО",
              "img_stamp": "⬛ ПЕЧАТЬ"}
