"""Latin → Cyrillic transliteration."""

from __future__ import annotations

from src.ocr.translit import to_cyrillic


def test_latin_names_to_cyrillic() -> None:
    assert to_cyrillic("KHUDAYBERDIEV") == "ХУДАЙБЕРДИЕВ"
    assert to_cyrillic("JASUR") == "ЖАСУР"
    assert to_cyrillic("UZBEKISTAN") == "УЗБЕКИСТАН"
    assert to_cyrillic("SHAROFIDDIN") == "ШАРОФИДДИН"


def test_already_cyrillic_unchanged() -> None:
    assert to_cyrillic("АЗИМОВ") == "АЗИМОВ"
    assert to_cyrillic("ТАДЖИКИСТАН") == "ТАДЖИКИСТАН"


def test_empty_and_digraphs() -> None:
    assert to_cyrillic("") == ""
    assert to_cyrillic("ZHASUR") == "ЖАСУР"
    assert to_cyrillic("CHORI") == "ЧОРИ"
