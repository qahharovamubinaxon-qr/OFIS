"""АЛПИНИСТ — blanks, the печать, the self-counting number, the printing.

The section serves the training centre's climber cards: the worker's photo is
cleaned to a white ground and cut 3×4 into the card's frame, the worker signs
with the mouse in ink, the back's blank number counts up on its own —
145, 146, 147 — and the finished two-page PDF lands in output/alpinist.
"""

from __future__ import annotations

import io
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.alpinist_renderer import AlpinistData, output_name, render
from src.services import blank_layout

log = get_logger(__name__)

SECTION = "alpinist"
BLANK_SUFFIXES = {".pdf"}
STAMP_SUFFIXES = {".png", ".jpg", ".jpeg"}

#: The next blank number to hand out — the owner's run starts at 145.
KEY_COUNTER = "alpinist.counter"
FIRST_NUMBER = 145


@dataclass(frozen=True)
class AlpinistResult:
    pdf: bytes
    saved: Path
    surname: str


def ink_only(data: bytes) -> bytes:
    """The picture with its white paper made transparent, as PNG bytes.

    Serves the печать AND a photographed signature: whatever is drawn in
    ink stays, the sheet behind it goes — so on the card only the ink
    lands over the print, the way a real stamp or signature would."""
    import numpy as np
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGBA")
    pixels = np.array(image)
    paper = pixels[:, :, :3].astype(int).sum(axis=2) > 690
    pixels[paper, 3] = 0
    out = io.BytesIO()
    Image.fromarray(pixels).save(out, "PNG")
    return out.getvalue()


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "alpinist"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe(name: str) -> str:
    cleaned = "".join(c for c in (name or "").strip()
                      if c.isalnum() or c in " _-").strip()
    if not cleaned:
        raise ValidationError("Ном керак")
    return cleaned


class AlpinistService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        return sorted(p for p in templates_dir().iterdir()
                      if p.is_file() and p.suffix.lower() in BLANK_SUFFIXES)

    def add_template(self, name: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка 2 саҳифали PDF бўлиши керак")
        dest = templates_dir() / f"{_safe(name)}.pdf"
        shutil.copyfile(source, dest)
        log.info("АЛПИНИСТ бланкаси қўшилди: %s", dest.name)
        return dest

    def remove_template(self, template: Path) -> None:
        Path(template).unlink(missing_ok=True)
        blank_layout.reset(SECTION, template)

    # ------------------------------------------------------------ печать
    def stamp(self) -> Path | None:
        found = sorted((templates_dir() / "stamp").glob("stamp.png"))
        return found[0] if found else None

    def set_stamp(self, source: Path) -> Path:
        """Keep the печать with its paper made transparent, so it overlays
        the card's text the way a real stamp does."""
        source = Path(source)
        if source.suffix.lower() not in STAMP_SUFFIXES or not source.exists():
            raise ValidationError("Печать PNG ёки JPG расм бўлиши керак")
        folder = templates_dir() / "stamp"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "stamp.png"
        dest.write_bytes(ink_only(source.read_bytes()))
        log.info("АЛПИНИСТ печати янгиланди")
        return dest

    def remove_stamp(self) -> None:
        found = self.stamp()
        if found:
            found.unlink(missing_ok=True)

    # ------------------------------------------------------------ layout
    def layout(self, template: Path | None) -> dict:
        if not template:
            return {}
        loaded = blank_layout.load(SECTION, template)
        fields = (loaded or {}).get("fields") or {}
        old = fields.get("img_stamp")
        from src.pdf.alpinist_spec import LEGACY_STAMP

        if (old and len(old) == 3
                and all(abs(float(a) - b) < 1e-6
                        for a, b in zip(old, LEGACY_STAMP, strict=True))):
            # the печать moved to the card's face — a layout saved before
            # that must not pin it to the back's old spot
            fields = {k: v for k, v in fields.items() if k != "img_stamp"}
            loaded = {**loaded, "fields": fields}
        return loaded

    def save_layout(self, template: Path, layout: dict) -> Path:
        return blank_layout.save(SECTION, template, layout)

    def reset_layout(self, template: Path) -> None:
        blank_layout.reset(SECTION, template)

    # ----------------------------------------------------------- counter
    def next_number(self) -> int:
        """The number the next card takes — 145 on a fresh machine."""
        if self._settings is None:
            return FIRST_NUMBER
        raw = str(self._settings.get(KEY_COUNTER, "") or "").strip()
        return int(raw) if raw.isdigit() else FIRST_NUMBER

    def _advance_counter(self, used: str) -> None:
        used = (used or "").strip()
        if self._settings is not None and used.isdigit():
            self._settings.set(KEY_COUNTER, str(int(used) + 1))

    # ---------------------------------------------------------- printing
    def generate(self, data: AlpinistData,
                 template: Path | None) -> AlpinistResult:
        if template is None:
            raise ValidationError(
                "АЛПИНИСТ бланкаси юкланмаган — «➕ Бланка» орқали юкланг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — ҳужжатларни ўқитинг")

        data.layout = self.layout(Path(template))
        pdf = render(data, Path(template))

        folder = paths.output_dir() / "alpinist"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / output_name(data)
        counter = 2
        while target.exists():
            target = folder / f"{target.stem.split(' (')[0]} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)
        self._advance_counter(data.blank_number)
        log.info("АЛПИНИСТ: %s — %s", data.fio(), target.name)
        return AlpinistResult(pdf=pdf, saved=target,
                              surname=(data.surname or "").strip())
