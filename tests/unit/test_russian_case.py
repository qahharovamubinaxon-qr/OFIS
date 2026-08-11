"""A worker's name in the case a Russian form asks for it in.

The office asked for this by example: «Саидов Сардор» is «Саидову Сардору»
when the form says «выдано кому». What is checked here is that the endings
are right for both sexes and for the name shapes that actually walk through
the door — Uzbek, Tajik, Turkmen and Russian — and that the one rule everyone
gets wrong is held to: A WOMAN'S NAME ENDING IN A CONSONANT DOES NOT DECLINE.
"""

from __future__ import annotations

import pytest
from src.domain.russian_case import CASES, decline, decline_fio


# ------------------------------------------------------- the office example
def test_the_example_the_office_gave() -> None:
    """«Саидов Сардорга берилди» → «Саидову Сардору»."""
    assert decline_fio("Саидов", "Сардор", "", "dat") == "Саидову Сардору"


def test_a_man_in_every_case() -> None:
    said = {case: decline_fio("Саидов", "Сардор", "Акмалович", case)
            for case in CASES}
    assert said["gen"] == "Саидова Сардора Акмаловича"
    assert said["dat"] == "Саидову Сардору Акмаловичу"
    assert said["acc"] == "Саидова Сардора Акмаловича"
    assert said["ins"] == "Саидовым Сардором Акмаловичем"
    assert said["pre"] == "Саидове Сардоре Акмаловиче"


def test_a_woman_in_every_case() -> None:
    said = {case: decline_fio("Саидова", "Гулнора", "Акмаловна", case,
                              male=False) for case in CASES}
    assert said["gen"] == "Саидовой Гулноры Акмаловны"
    assert said["dat"] == "Саидовой Гулноре Акмаловне"
    assert said["acc"] == "Саидову Гулнору Акмаловну"
    assert said["ins"] == "Саидовой Гулнорой Акмаловной"
    assert said["pre"] == "Саидовой Гулноре Акмаловне"


# --------------------------------------------------------- the one big rule
@pytest.mark.parametrize("case", CASES)
def test_a_womans_name_ending_in_a_consonant_never_changes(case) -> None:
    """The commonest mistake on these forms, and half our workers.

    Central Asian women's names very often end in a consonant, and Russian
    leaves those exactly as they are — «Юсуф Гулшан» in every case.
    """
    assert decline_fio("Юсуф", "Гулшан", "", case, male=False) == "Юсуф Гулшан"
    assert decline("Нигор", case, male=False, kind="name") == "Нигор"
    assert decline("Каримзод", case, male=False, kind="surname") == "Каримзод"


@pytest.mark.parametrize("case", CASES)
def test_the_same_name_on_a_man_does_change(case) -> None:
    """…and the very same letters on a man decline normally, which is why
    the sex has to be known and not guessed from the ending."""
    assert decline("Гулшан", case, male=True, kind="name") != "Гулшан"


# ---------------------------------------------------------------- surnames
def test_the_possessive_surnames_our_workers_carry() -> None:
    for surname in ("Исоев", "Каримов", "Рустамов", "Холбердиев"):
        assert decline(surname, "dat", kind="surname") == surname + "у"
        assert decline(surname, "ins", kind="surname") == surname + "ым"


def test_a_foreign_surname_ending_in_a_consonant() -> None:
    assert decline("Юсуф", "dat", kind="surname") == "Юсуфу"
    assert decline("Юсуф", "ins", kind="surname") == "Юсуфом"
    assert decline("Каримзод", "gen", kind="surname") == "Каримзода"


def test_an_adjectival_surname() -> None:
    assert decline("Достоевский", "dat", kind="surname") == "Достоевскому"
    assert decline("Достоевская", "dat", male=False,
                   kind="surname") == "Достоевской"


def test_a_surname_ending_in_a_vowel_that_is_not_declinable() -> None:
    """«-о», «-и», «-у»: Шевченко, Гулиеви — unchanged for either sex."""
    for surname in ("Шевченко", "Дурсуни", "Бекмуроду"):
        assert decline(surname, "dat", kind="surname") == surname
        assert decline(surname, "dat", male=False, kind="surname") == surname


def test_a_double_surname_declines_on_both_halves() -> None:
    assert decline("Кара-Мурза", "dat", kind="surname") == "Каре-Мурзе"


# ------------------------------------------------------------ given names
def test_a_mans_name_after_a_husher_takes_ем_not_ом() -> None:
    """The spelling rule: «Фарух» → «Фарухом», but «Сироч» → «Сирочем»."""
    assert decline("Сироч", "ins", kind="name") == "Сирочем"
    assert decline("Фарух", "ins", kind="name") == "Фарухом"


def test_a_womans_name_after_a_velar_takes_и_not_ы() -> None:
    """«Малика» → «Малики», not «Маликы»."""
    assert decline("Малика", "gen", male=False, kind="name") == "Малики"
    assert decline("Гулнора", "gen", male=False, kind="name") == "Гулноры"


def test_a_womans_name_in_ия() -> None:
    assert decline("Мария", "dat", male=False, kind="name") == "Марии"
    assert decline("Мария", "pre", male=False, kind="name") == "Марии"


def test_a_mans_name_ending_in_a() -> None:
    assert decline("Никита", "dat", kind="name") == "Никите"
    assert decline("Мустафа", "gen", kind="name") == "Мустафы"


def test_a_mans_name_ending_in_soft_or_short_i() -> None:
    assert decline("Игорь", "dat", kind="name") == "Игорю"
    assert decline("Андрей", "dat", kind="name") == "Андрею"


# ------------------------------------------------------------ patronymics
def test_the_patronymics() -> None:
    assert decline("Акмалович", "dat", kind="patronymic") == "Акмаловичу"
    assert decline("Акмалович", "ins", kind="patronymic") == "Акмаловичем"
    assert decline("Акмаловна", "dat", male=False,
                   kind="patronymic") == "Акмаловне"
    assert decline("Акмаловна", "gen", male=False,
                   kind="patronymic") == "Акмаловны"


@pytest.mark.parametrize("case", CASES)
def test_an_uzbek_patronymic_is_left_alone(case) -> None:
    """«угли» and «кизи» are not Russian and take no Russian ending."""
    assert decline("Акмал угли", case, kind="patronymic").startswith("Акмал")


# -------------------------------------------------------------- the edges
def test_nothing_typed_gives_nothing_back() -> None:
    assert decline("", "dat") == ""
    assert decline_fio("", "", "", "dat") == ""


def test_a_case_nobody_asked_for_leaves_the_word_alone() -> None:
    assert decline("Саидов", "nominative", kind="surname") == "Саидов"
    assert decline("Саидов", "", kind="surname") == "Саидов"


def test_a_worker_with_no_patronymic_leaves_no_double_space() -> None:
    assert decline_fio("Саидов", "Сардор", "", "dat") == "Саидову Сардору"


def test_a_shape_the_rules_do_not_cover_is_handed_back_unchanged() -> None:
    """Better a name the operator can see and fix than one invented."""
    assert decline("Ойбегу", "dat", kind="name") == "Ойбегу"


# --------------------------------------------------- and it reaches a form
def test_the_declined_name_is_a_field_the_office_can_place() -> None:
    from src.pdf.universal_fields import CATALOGUE, UniversalData, values

    assert "fio_dat" in CATALOGUE
    assert "Дательный" in CATALOGUE["fio_dat"]

    said = values(UniversalData(surname="Саидов", name="Сардор",
                                patronymic="Акмалович", gender="Мужской"))
    assert said["fio_dat"] == "Саидову Сардору Акмаловичу"
    assert said["surname_gen"] == "Саидова"


def test_the_form_follows_the_sex_the_operator_set() -> None:
    from src.pdf.universal_fields import UniversalData, values

    woman = UniversalData(surname="Юсуф", name="Гулшан", gender="Женский")
    assert values(woman)["fio_dat"] == "Юсуф Гулшан"

    man = UniversalData(surname="Юсуф", name="Гулшан", gender="Мужской")
    assert values(man)["fio_dat"] == "Юсуфу Гулшану"
