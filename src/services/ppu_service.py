"""ППУ — the pair the office prints from a worker's регистрация.

One run takes the регистрация the worker already has, the worker's photograph,
and the day the office wants the ППУ to start. Everything else comes off the
регистрация itself: the Ф.И.О., the birth date, the citizenship, the passport,
the address, and the day it runs to.

The finished pair is saved to the desktop as two PICTURES, front and back,
under the worker's surname — that is how the office files them.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.ppu_renderer import PAGE_FILES, PpuData, pages_as_png, render

log = get_logger(__name__)

KEY_NUMBER = "ppu.number"

#: What the office's own sheet carried, so the first run starts somewhere real.
DEFAULT_NUMBER = "AL0531591"


@dataclass(frozen=True)
class PpuResult:
    pdf: bytes
    #: front and back, as PNG bytes
    pages: list[bytes]
    #: where each page was written
    saved: list[Path]
    number: str
    valid_from: date | None
    valid_to: date | None


def _folder() -> Path:
    return paths.user_templates_dir() / "ppu"


def _file_stem(surname: str) -> str:
    stem = "".join(c for c in (surname or "").strip()
                   if c.isalnum() or c in " _-").strip()
    return stem or "ППУ"


def desktop_target(filename: str) -> Path:
    """Where on the desktop this page goes, without treading on another."""
    folder = paths.desktop_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    stem, suffix = target.stem, target.suffix
    counter = 2
    while target.exists():
        target = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return target


class PpuService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ----------------------------------------------------------- settings
    def _get(self, key: str, default: str = "") -> str:
        if self._settings is None:
            return default
        try:
            value = self._settings.get(key)
        except TypeError:
            value = self._settings.get(key, default)
        return str(value) if value not in (None, "") else default

    def _set(self, key: str, value: str) -> None:
        if self._settings is not None:
            self._settings.set(key, value)

    def number(self) -> str:
        """The blank number standing in the box from the last worker."""
        return self._get(KEY_NUMBER, DEFAULT_NUMBER)

    # ---------------------------------------------------------- templates
    def templates(self) -> list[Path]:
        """The blank pairs on offer. Empty until the office uploads one."""
        out = []
        bundled = paths.templates_dir() / "ppu" / "standart"
        if (bundled / PAGE_FILES[0]).exists():
            out.append(bundled)
        folder = _folder()
        if folder.exists():
            out += sorted(p for p in folder.iterdir()
                          if p.is_dir() and (p / PAGE_FILES[0]).exists())
        return out

    def add_template(self, name: str, front: Path, back: Path) -> Path:
        """Register a blank pair — the front, then the back."""
        name = "".join(c for c in name.strip() if c.isalnum() or c in " _-").strip()
        if not name:
            raise ValidationError("Шаблонга ном керак")
        for src in (front, back):
            if src.suffix.lower() != ".pdf" or not src.exists():
                raise ValidationError("Олд ва орқа бланка PDF бўлиши керак",
                                      context={"path": str(src)})
        dest = _folder() / name
        dest.mkdir(parents=True, exist_ok=True)
        for src, target in zip((front, back), PAGE_FILES, strict=True):
            shutil.copyfile(src, dest / target)
        log.info("ППУ шаблони қўшилди: %s", name)
        return dest

    # ----------------------------------------------------------- printing
    def generate(
        self,
        *,
        surname: str,
        name: str,
        patronymic: str = "",
        birth_date: date | None = None,
        gender: str = "",
        citizenship: str = "",
        document: str = "",
        address: str = "",
        valid_from: date,
        valid_to: date | None = None,
        number: str = "",
        photo: bytes | None = None,
        template: Path | None = None,
    ) -> PpuResult:
        if not surname.strip() or not name.strip():
            raise ValidationError("Фамилия ва Исм бўш бўлмасин")
        if template is None:
            raise ValidationError(
                "ППУ бланкаси юкланмаган — «Шаблон қўшиш» орқали олд ва орқа "
                "саҳифани юкланг.")

        number = number.strip() or self.number()
        data = PpuData(
            surname=surname, name=name, patronymic=patronymic,
            birth_date=birth_date, gender=gender, citizenship=citizenship,
            document=document, address=address, valid_from=valid_from,
            valid_to=valid_to, number=number, photo=photo)
        pdf = render(data, Path(template))
        pages = pages_as_png(pdf)

        stem = _file_stem(surname)
        saved = []
        for index, png in enumerate(pages, 1):
            target = desktop_target(f"{stem} ППУ {index}.png")
            target.write_bytes(png)
            saved.append(target)

        self._set(KEY_NUMBER, number)
        log.info("ППУ: %s — %d саҳифа сақланди", surname, len(saved))
        return PpuResult(pdf=pdf, pages=pages, saved=saved, number=number,
                         valid_from=valid_from, valid_to=valid_to)
