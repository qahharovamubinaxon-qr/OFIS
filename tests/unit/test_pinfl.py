"""ПИНФЛ off the strip at the foot of an Uzbek passport.

The line used here is a real one — КАХОРОВ АББОСБЕК's own passport, the
same page the office sent when the surname was coming out wrong. Its
ПИНФЛ has to fall out of the strip and agree with the birth date printed
on the face of the page: 13.01.1995.
"""

from __future__ import annotations

from datetime import date

import pytest
from src.domain.pinfl import birth_of, is_male, is_pinfl, pinfl_from_mrz

#: the office's own passport, second line of the strip
KAKHOROV = "FA28305166UZB9501131M31052053130195405008788"
PINFL = "31301954050087"


def test_the_office_s_own_rule_gives_the_office_s_own_number() -> None:
    """«охиридаги 16 рақамдан 14 таси» — and the last two are dropped."""
    assert pinfl_from_mrz(KAKHOROV) == PINFL
    assert len(PINFL) == 14
    # the two that are NOT taken are the strip's check digits
    assert KAKHOROV.endswith(PINFL + "88")


def test_the_number_agrees_with_the_date_the_page_prints() -> None:
    """That agreement is the whole reason for reading it rather than typing."""
    assert birth_of(PINFL) == date(1995, 1, 13)
    assert pinfl_from_mrz(KAKHOROV, born=date(1995, 1, 13)) == PINFL
    # a page whose face says something else means the strip was misread
    assert pinfl_from_mrz(KAKHOROV, born=date(1995, 1, 14)) == ""


def test_a_strip_that_did_not_read_gives_nothing() -> None:
    """An empty box the operator fills in beats a wrong number sent home."""
    for rubbish in ("", "   ", "FA283051", "не цифры вовсе",
                    "FA28305166UZB9501131M310520531301954050087"):
        assert pinfl_from_mrz(rubbish) == "", rubbish


@pytest.mark.parametrize("value, born, male", [
    ("31301954050087", date(1995, 1, 13), True),
    ("42505734220034", date(1973, 5, 25), False),
    ("52001100000001", date(2010, 1, 20), True),
    ("11512880000002", date(1888, 12, 15), True),
    ("21512880000002", date(1888, 12, 15), False),
])
def test_the_century_and_the_sex_are_in_the_first_digit(value, born, male
                                                        ) -> None:
    assert is_pinfl(value)
    assert birth_of(value) == born
    assert is_male(value) is male


@pytest.mark.parametrize("value", [
    "",
    "3130195405008",           # thirteen
    "313019540500871",         # fifteen
    "3130195405008a",          # a letter in it
    "73001100000001",          # there is no century 7
    "33201100000001",          # there is no 32nd day
    "31991954050087",          # there is no 99th month
])
def test_what_is_not_a_number_is_refused(value) -> None:
    assert not is_pinfl(value)
    assert birth_of(value) is None
    assert is_male(value) is None
