"""Russian пропись: numbers, dates and money written out in words."""

from __future__ import annotations

from datetime import date

import pytest

from src.utils.rus_words import (
    amount_to_words,
    date_to_words,
    format_amount,
    number_to_words,
    parse_amount,
    plural,
)


@pytest.mark.parametrize(("value", "expected"), [
    (0, "ноль"),
    (1, "один"),
    (5, "пять"),
    (11, "одиннадцать"),
    (21, "двадцать один"),
    (100, "сто"),
    (123, "сто двадцать три"),
    (1000, "одна тысяча"),
    (2000, "две тысячи"),
    (5000, "пять тысяч"),
    (10000, "десять тысяч"),
    (27500, "двадцать семь тысяч пятьсот"),
    (1000000, "один миллион"),
    (2345678, "два миллиона триста сорок пять тысяч шестьсот семьдесят восемь"),
])
def test_number_to_words(value: int, expected: str) -> None:
    assert number_to_words(value) == expected


def test_plural_forms() -> None:
    assert plural(1, "рубль", "рубля", "рублей") == "рубль"
    assert plural(2, "рубль", "рубля", "рублей") == "рубля"
    assert plural(5, "рубль", "рубля", "рублей") == "рублей"
    assert plural(11, "рубль", "рубля", "рублей") == "рублей"
    assert plural(21, "рубль", "рубля", "рублей") == "рубль"


@pytest.mark.parametrize(("value", "expected"), [
    (date(2026, 7, 26), "Двадцать шестое июля две тысячи двадцать шестого года"),
    (date(2026, 9, 9), "Девятое сентября две тысячи двадцать шестого года"),
    (date(2024, 1, 1), "Первое января две тысячи двадцать четвёртого года"),
    (date(2025, 3, 31), "Тридцать первое марта две тысячи двадцать пятого года"),
    (date(2000, 12, 15), "Пятнадцатое декабря двухтысячного года"),
    (date(2011, 5, 20), "Двадцатое мая две тысячи одиннадцатого года"),
    (date(2030, 11, 3), "Третье ноября две тысячи тридцатого года"),
])
def test_date_to_words(value: date, expected: str) -> None:
    assert date_to_words(value) == expected


@pytest.mark.parametrize(("rub", "kop", "expected"), [
    (10000, 0, "Десять тысяч рублей 00 копеек"),
    (27500, 0, "Двадцать семь тысяч пятьсот рублей 00 копеек"),
    (1500, 50, "Одна тысяча пятьсот рублей 50 копеек"),
    (1, 0, "Один рубль 00 копеек"),
    (22, 0, "Двадцать два рубля 00 копеек"),
    (0, 0, "Ноль рублей 00 копеек"),
])
def test_amount_to_words(rub: int, kop: int, expected: str) -> None:
    assert amount_to_words(rub, kop) == expected


@pytest.mark.parametrize(("text", "expected"), [
    ("10000", (10000, 0)),
    ("10 000,00", (10000, 0)),
    ("10000.50", (10000, 50)),
    ("27 500", (27500, 0)),
    ("1 500,5", (1500, 50)),
    ("10 000 ₽", (10000, 0)),
    ("1500 руб.", (1500, 0)),
])
def test_parse_amount(text: str, expected: tuple[int, int]) -> None:
    assert parse_amount(text) == expected


def test_parse_amount_rejects_garbage() -> None:
    for bad in ("", "abc", "—"):
        with pytest.raises(ValueError):
            parse_amount(bad)


def test_format_amount() -> None:
    assert format_amount(10000, 0) == "10 000,00"
    assert format_amount(1500, 50) == "1 500,50"


def test_round_trip_matches_the_check_sample() -> None:
    """The Сбербанк check the owner sent reads «Десять тысяч рублей 00 копеек»."""
    rub, kop = parse_amount("10 000,00")
    assert amount_to_words(rub, kop) == "Десять тысяч рублей 00 копеек"
    assert format_amount(rub, kop) == "10 000,00"
