"""«📐 Созлаш» for the sections built on a shared :class:`FieldMapping`.

Some sections print through a mapping every office shares — ХОСТЕЛ,
РЕГИСТРАЦИЯ, СФЕРА all write onto the same МВД forms — and until now the
office could only move a value, if that. This is the bridge that gives those
sections the same window the newer ones have: drag a value, resize it, pick
its face, set it bold, colour it, turn it, add a text of your own, zoom in on
a printed rule.

Why a bridge and not a rewrite
------------------------------
A mapping is in POINTS on a particular page size, and the editor works in
FRACTIONS of the page — that is what lets one office's re-scan of a form sit
a shade differently without moving everybody else's. So this converts one way
in and the other way out, and nothing about the mapping itself changes.

What the office may and may not do
----------------------------------
The form's OWN values can be moved, resized and restyled, but not deleted:
they are what the form is for, and a mapping shared with every other office
is not a thing one office may cut fields out of. A text the office ADDS is
its own and can be deleted freely — it lives only in this blank's layout.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.pdf.mapping import FieldMapping, anchor_x
from src.pdf.trud8_fields import Field
from src.ui.widgets.field_editor import OWN_TEXT, FieldEditor

log = get_logger(__name__)

#: What the «➕ Матн» list calls the office's own text.
OWN_LABEL = "✎ Ўз матним (ўзим ёзаман)"

#: Turning an id into words. A mapping names its fields for the program —
#: «reg.passport.issue.d» — and the office should not have to read that.
_WORDS: dict[str, str] = {
    "reg": "", "surname": "Фамилия", "name": "Исм", "patronymic": "Отчество",
    "citizenship": "Гражданство", "birth": "Туғилган сана",
    "gender": "Жинси", "male": "эркак", "female": "аёл",
    "passport": "Паспорт", "series": "серия", "number": "номер",
    "issue": "берилган", "expiry": "амал қилиш охири",
    "stay_until": "яшаш муддати", "stay_from": "яшаш бошланиши",
    "registered_until": "рўйхат муддати", "address": "Адрес",
    "host": "Қабул қилувчи", "organisation": "Ташкилот", "inn": "ИНН",
    "d": "куни", "m": "ойи", "y": "йили",
}


def label_of(field_id: str, given: dict[str, str] | None = None) -> str:
    """«reg.passport.issue.d» → «Паспорт берилган куни»."""
    if given and field_id in given:
        return given[field_id]
    if field_id.startswith(OWN_TEXT):
        return f"✎ {field_id[len(OWN_TEXT):]}"
    said = [_WORDS.get(part, part) for part in field_id.split(".")]
    made = " ".join(word for word in said if word).strip()
    return made or field_id


def sample_of(field_id: str, given: dict[str, str] | None = None) -> str:
    """What stands in for the value while it is being dragged."""
    if given and field_id in given:
        return given[field_id]
    if field_id.startswith(OWN_TEXT):
        return field_id[len(OWN_TEXT):]
    return label_of(field_id)


def to_fields(mapping: FieldMapping, layout: dict | None
              ) -> tuple[list[Field], dict[str, float]]:
    """The mapping (and the office's own texts) as the editor's fields.

    Also hands back the cell pitch of every letter-cell row, as a share of
    the page width — those print one glyph per box and have to be drawn that
    way on screen or the office cannot line them up.
    """
    width, height = mapping.page_size
    layout = layout or {}
    styles = layout.get("fields") or {}
    made: list[Field] = []
    pitches: dict[str, float] = {}

    for one in mapping.fields:
        extra = one.model_extra or {}
        saved = styles.get(one.id)
        saved = saved if isinstance(saved, dict) else {}
        made.append(Field(
            key=one.id, page=one.page,
            x=anchor_x(one) / width, baseline=(one.y or 0.0) / height,
            size=(one.size or 10.0) / height,
            bold=bool(saved.get("bold", extra.get("bold", False))),
            font=str(saved.get("font") or one.font or "OfisSerif"),
            colour=tuple(float(c) for c in (
                saved.get("colour") or extra.get("colour") or (0.0, 0.0, 0.0)
            )[:3]),
            rotate=int(saved.get("rotate") or extra.get("rotate") or 0)))
        if one.type == "grid" and one.pitch:
            pitches[one.id] = float(one.pitch) / width

    for raw in layout.get("texts") or []:
        if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
            continue
        made.append(Field(
            key=OWN_TEXT + " ".join(str(raw["text"]).split()),
            page=int(raw.get("page") or 1),
            x=float(raw.get("x") or 0.1),
            baseline=float(raw.get("y") or 0.1),
            size=float(raw.get("size") or 0.014),
            bold=bool(raw.get("bold")),
            font=str(raw.get("font") or "OfisSerif"),
            colour=tuple(float(c) for c in
                         (raw.get("colour") or (0.0, 0.0, 0.0))[:3]),
            rotate=int(raw.get("rotate") or 0)))
    return made, pitches


def to_layout(fields: list[Field]) -> dict:
    """What the editor left, in the shape the layout store keeps."""
    placed: dict[str, dict] = {}
    texts: list[dict] = []
    for one in fields:
        body = {"x": round(one.x, 5), "y": round(one.baseline, 5),
                "size": round(one.size, 5), "font": one.font,
                "bold": bool(one.bold),
                "colour": [round(c, 4) for c in one.colour],
                "rotate": int(getattr(one, "rotate", 0) or 0)}
        if one.key.startswith(OWN_TEXT):
            texts.append({**body, "page": one.page,
                          "text": one.key[len(OWN_TEXT):]})
        else:
            placed[one.key] = body
    return {"fields": placed, "texts": texts}


def arrange(parent, *, pages: list[bytes], mapping: FieldMapping,
            layout: dict | None, title: str,
            labels: dict[str, str] | None = None,
            samples: dict[str, str] | None = None,
            images: dict[str, bytes] | None = None) -> dict | None:
    """Open the window. Returns the new layout, or ``None`` if it was closed.

    ``images`` puts a real picture where a word would be — a signature or a
    stamp the office is placing rather than a value it is printing.
    """
    fields, pitches = to_fields(mapping, layout)
    catalogue = {f.key: label_of(f.key, labels) for f in fields}
    shown = {f.key: sample_of(f.key, samples) for f in fields}
    # the form's own values may be moved and restyled, never deleted: a
    # mapping shared with every office is not one office's to cut fields from
    frozen = {one.id for one in mapping.fields}

    editor = FieldEditor(pages, fields, title=title, parent=parent,
                         catalogue=catalogue, samples=shown, frozen=frozen,
                         pitches=pitches, images=images or {},
                         own_text=OWN_LABEL)
    if editor.exec() != FieldEditor.DialogCode.Accepted:
        return None
    made = to_layout(editor.fields())
    log.info("Созлаш: «%s» — %d майдон, %d ўз матни", title,
             len(made["fields"]), len(made["texts"]))
    return made


__all__ = ["OWN_LABEL", "arrange", "label_of", "sample_of", "to_fields",
           "to_layout"]
