"""The МИГ card's own list of values, handed to the general layout editor.

The dragging, the wheel, the arrow keys and the saving all live in
:mod:`src.ui.widgets.layout_editor` — every section that prints onto an
uploaded blank uses the same one. This module only says WHAT the ИШЧИ КАРТАСИ
has on it: which values, what to call them, and a sample of each.
"""

from __future__ import annotations

from src.pdf.mig_renderer import digits_spaced, spaced
from src.pdf.mig_spec import BLUE, CODE_SLOTS, JOBS
from src.ui.widgets.layout_editor import Item, LayoutEditor, RuleItem

#: What each value is called on screen, and a sample, in printing order.
SAMPLES: tuple[tuple[str, str, str], ...] = (
    ("series", "СЕРИЯ", "46 26"),
    ("number", "НОМЕР", "0367598"),
    ("surname", "ФАМИЛИЯ", spaced("ЖАХОНГИРОВА")),
    ("surname_lat", "ФАМИЛИЯ лотинча", spaced("JAKHONGIROVA")),
    ("name", "ИСМИ", spaced("МЕХРАНГИЗБОНУ")),
    ("patronymic", "ОТЧЕСТВО", spaced("РАХИМ КИЗИ")),
    ("birth_date", "ТУГИЛГАН САНА", digits_spaced("13.08.2009")),
    ("citizenship", "ГРАЖДАНСТВАСИ", spaced("УЗБЕКИСТАН")),
    ("passport", "ПАСПОРТ", digits_spaced("FB2376204")),
    ("visa", "ВИЗА", "АШХ23652"),
    ("valid_from", "МУДДАТ — С", "20.07.2026"),
    ("valid_to", "МУДДАТ — ДО", "14.10.2026"),
    ("issued", "БЕРИЛГАН САНА (кўк)", "15 03 26"),
    ("code_tl", "КОД — чап тепа", "2352"),
    ("code_tr", "КОД — ўнг тепа", "2352"),
    ("code_bl", "КОД — чап паст", "2352"),
    ("code_br", "КОД — ўнг паст", "2352"),
)

#: The face the card is typed in, and the two the office stamps in.
SCREEN_FONT = "Courier New"
_SCREEN_FACES = {"issued": "Akshar", **{k: "Times New Roman" for k in CODE_SLOTS}}


def build(fields, sex, jobs) -> tuple[list[Item], list[RuleItem]]:
    """Everything on the card that can be dragged, ready for the editor."""
    items = [
        Item(key=key, label=label, sample=sample,
             x=fields[key].x, baseline=fields[key].baseline,
             size=fields[key].size,
             colour=BLUE if key == "issued" or key in CODE_SLOTS
             else (0.08, 0.08, 0.08),
             font_family=_SCREEN_FACES.get(key, SCREEN_FONT))
        for key, label, sample in SAMPLES if key in fields
    ]
    items += [
        Item(key=f"sex:{key}", label=label, sample="X",
             x=sex[key].x, baseline=sex[key].baseline, size=sex[key].size,
             font_family=SCREEN_FONT)
        for key, label in (("male", "МУЖ — X"), ("female", "ЖЕН — X"))
        if key in sex
    ]
    rules = [RuleItem(key=key, label=label, x0=jobs[key].x0,
                      x1=jobs[key].x1, y=jobs[key].y)
             for key, label, _rule in JOBS if key in jobs]
    return items, rules


class MigLayoutEditor(LayoutEditor):
    """«Матнларни жойлаш» for the ИШЧИ КАРТАСИ."""

    def __init__(self, page_png: bytes, fields, sex, jobs, parent=None) -> None:
        items, rules = build(fields, sex, jobs)
        super().__init__(page_png, items, rules,
                         title="ИШЧИ КАРТАСИ — матнларни жойлаш", parent=parent)

    def layout_data(self) -> dict:
        """What to keep beside this firm's blank."""
        moved = self.result()
        return {
            "fields": {k: v for k, v in moved.items.items()
                       if not k.startswith("sex:")},
            "sex": {k.split(":", 1)[1]: v for k, v in moved.items.items()
                    if k.startswith("sex:")},
            "jobs": dict(moved.rules),
        }
