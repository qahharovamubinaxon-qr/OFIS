"""Value formatters & text transforms applied before a value is drawn.

Pure functions, unit-tested. A field names its formatter/transform in the
mapping; the engine looks it up here. Never guesses.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date


def _upper(v: str) -> str:
    return v.upper()


def _lower(v: str) -> str:
    return v.lower()


def _title(v: str) -> str:
    return v.title()


TRANSFORMS: dict[str, Callable[[str], str]] = {
    "uppercase": _upper,
    "lowercase": _lower,
    "title": _title,
}


def apply_transform(value: str, name: str | None) -> str:
    if not name:
        return value
    fn = TRANSFORMS.get(name)
    return fn(value) if fn else value


def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _date_dd(v: object) -> str:
    d = _parse_date(v)
    return f"{d.day:02d}" if d else ""


def _date_mm(v: object) -> str:
    d = _parse_date(v)
    return f"{d.month:02d}" if d else ""


def _date_yyyy(v: object) -> str:
    d = _parse_date(v)
    return f"{d.year:04d}" if d else ""


_MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _date_dmy(v: object) -> str:
    """05.11.2023 — dotted numeric date."""
    d = _parse_date(v)
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}" if d else ""


def _date_dmy_g(v: object) -> str:
    """05.11.2023 г. — dotted numeric date with the Russian year marker."""
    d = _parse_date(v)
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d} г." if d else ""


def _date_long_g(v: object) -> str:
    """06 ноября 2023 г. — long Russian date (genitive month)."""
    d = _parse_date(v)
    return f"{d.day:02d} {_MONTHS_GEN[d.month - 1]} {d.year:04d} г." if d else ""


FORMATTERS: dict[str, Callable[[object], str]] = {
    "date_dd": _date_dd,
    "date_mm": _date_mm,
    "date_yyyy": _date_yyyy,
    "date_dmy": _date_dmy,
    "date_dmy_g": _date_dmy_g,
    "date_long_g": _date_long_g,
}


def apply_formatter(value: object, name: str | None) -> str:
    if name and name in FORMATTERS:
        return FORMATTERS[name](value)
    return "" if value is None else str(value)
