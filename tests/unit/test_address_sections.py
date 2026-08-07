"""Each section shows its OWN addresses and nobody else's.

The office's words: «МВД регистрациялар фақат МВД бўлимда, хостел
регистрациялар фақат хостел бўлимда чиқадиган қил». They all live in one
table under a ``kind``, and ХОСТЕЛ and МВД РЕГИСТРАЦИЯ each asked for their
own — but РЕГИСТРАЦИЯ asked for the lot, so its list carried three sections'
addresses on a blank meant for one.
"""

from __future__ import annotations

from src.controllers.registration_controller import RegistrationController


class _Addresses:
    """The address service, remembering what it was asked for."""

    def __init__(self) -> None:
        self.asked: list[str | None] = []
        self.kept = {"regular": ["Балашиха, Ленина 33"],
                     "hostel": ["ХОСТЕЛ Мытищи"],
                     "mvdreg": ["МВД Одинцово"]}

    def list(self, kind: str | None = None):
        self.asked.append(kind)
        if kind is None:
            return [a for group in self.kept.values() for a in group]
        return list(self.kept.get(kind, []))


def _controller(addresses):
    return RegistrationController(addresses, ocr=None, registration=None)


def test_registration_shows_only_its_own_addresses() -> None:
    addresses = _Addresses()
    shown = _controller(addresses).addresses()
    assert shown == ["Балашиха, Ленина 33"]
    assert addresses.asked == ["regular"], "тури айтилмай сўралди"


def test_a_hostel_never_turns_up_in_the_registration_list() -> None:
    addresses = _Addresses()
    shown = _controller(addresses).addresses()
    assert "ХОСТЕЛ Мытищи" not in shown
    assert "МВД Одинцово" not in shown


def test_the_other_two_sections_still_ask_for_their_own() -> None:
    """They were right all along — this checks they stay right."""
    import inspect

    from src.controllers.hostel_controller import HostelController
    from src.controllers.mvdreg_controller import MvdRegController

    assert 'kind="hostel"' in inspect.getsource(HostelController.addresses)
    assert 'kind="mvdreg"' in inspect.getsource(MvdRegController.addresses)
