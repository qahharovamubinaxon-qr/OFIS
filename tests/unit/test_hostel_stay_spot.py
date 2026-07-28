"""Choosing where a hostel wants the stay-start date printed.

The «Отметка о подтверждении» box on the МВД form is large, and every hostel
stamps it differently, so the operator marks the spot once against a picture of
the page and it is used for that hostel from then on.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.config import paths
from src.domain.documents import Passport
from src.domain.enums import Gender
from src.domain.registration_address import RegistrationAddress
from src.pdf import boxes
from src.services.hostel_service import HostelService, stay_from_default

ROOT = Path(__file__).resolve().parents[2]
BLANK = ROOT / "templates" / "hostel_blank" / "blank.pdf"

pytestmark = pytest.mark.skipif(not BLANK.exists(), reason="hostel blank not bundled")

PASSPORT = Passport(surname="НАЗАРОВ", name="МУРОДУЛЛО", patronymic="ХАИТАЛИЕВИЧ",
                    number="1234567", series="FB", birth_date=date(2004, 2, 22),
                    issue_date=date(2023, 2, 16), issued_by="МВД",
                    nationality="УЗБЕКИСТАН", gender=Gender.MALE)


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _hostel(**extra) -> RegistrationAddress:
    return RegistrationAddress(
        label="ХОСТЕЛ", internal_code="x", address_text="-", host_fio="-",
        kind="hostel", template_path=BLANK, **extra)


def _date_at(pdf: Path, text: str = "28.07.2026") -> tuple[float, float]:
    """Where the printed date actually landed: its centre and baseline-ish y."""
    doc = fitz.open(pdf)
    try:
        hits = doc[1].search_for(text)
        assert hits, "the date was not printed on page 2"
        r = hits[0]
        return ((r.x0 + r.x1) / 2, r.y1)
    finally:
        doc.close()


def _generate(address: RegistrationAddress, out: Path) -> Path:
    return HostelService().generate(
        PASSPORT, None, address, registration_expiry=date(2027, 4, 13),
        registration_start=date(2026, 7, 28), output_dir=out).pdf_path


# ------------------------------------------------------------------ the box


def test_the_confirmation_box_is_found_on_the_form() -> None:
    """It is drawn as ink, not as a rectangle — it has to be seen, not read."""
    _page, x, y = stay_from_default()
    box = boxes.enclosing_box(BLANK, 2, (x, y))
    assert box is not None
    x0, y0, x1, y1 = box
    assert x0 < x < x1 and y0 < y < y1, (box, x, y)
    assert x1 - x0 > 200 and y1 - y0 > 80, box


def test_a_point_in_open_paper_has_no_box() -> None:
    assert boxes.enclosing_box(BLANK, 2, (300.0, 700.0)) is None


def test_a_page_that_does_not_exist_is_refused() -> None:
    from src.common.errors import ValidationError

    with pytest.raises(ValidationError):
        boxes.render(BLANK, 9)
    assert boxes.enclosing_box(BLANK, 9, (300.0, 200.0)) is None


def test_pixels_and_points_convert_both_ways() -> None:
    image = boxes.render(BLANK, 2)
    x, y = image.to_points(*image.to_pixels(434.9, 194.5))
    assert x == pytest.approx(434.9, abs=0.5)
    assert y == pytest.approx(194.5, abs=0.5)


# ---------------------------------------------------------------- the spot


def test_the_spot_starts_where_the_form_itself_puts_it() -> None:
    spot = HostelService().stay_from_spot(_hostel(), sample=date(2026, 7, 28))
    assert spot.is_default
    assert spot.page == 2
    assert spot.sample.startswith("28.07.2026")
    assert spot.size > 0 and spot.image.png[:4] == b"\x89PNG"
    assert spot.box is not None


def test_a_hostel_that_marked_a_spot_opens_on_it() -> None:
    spot = HostelService().stay_from_spot(_hostel(stay_from_x=380.0,
                                                  stay_from_y=250.0))
    assert (spot.x, spot.y) == (380.0, 250.0)
    assert not spot.is_default
    assert (spot.default_x, spot.default_y) == stay_from_default()[1:]


def test_a_hostel_being_added_is_shown_the_bundled_blank() -> None:
    """There is no template of its own yet — the box is in the same place."""
    spot = HostelService().stay_from_spot(None)
    assert spot.is_default and spot.box is not None


def test_a_spot_marked_but_not_yet_saved_is_not_thrown_away() -> None:
    spot = HostelService().stay_from_spot(_hostel(), current=(400.0, 230.0))
    assert (spot.x, spot.y) == (400.0, 230.0)


# ------------------------------------------------------------- the filling


def test_the_marked_spot_is_where_the_date_prints(tmp_path) -> None:
    default = _date_at(_generate(_hostel(), tmp_path / "a"))
    moved = _date_at(_generate(_hostel(stay_from_x=380.0, stay_from_y=250.0),
                               tmp_path / "b"))
    assert moved[1] == pytest.approx(250.0, abs=2.5)
    assert moved[0] == pytest.approx(default[0] - (434.9 - 380.0), abs=1.5)


def test_a_hostel_with_no_spot_prints_where_it_always_did(tmp_path) -> None:
    _page, dx, dy = stay_from_default()
    at = _date_at(_generate(_hostel(), tmp_path / "a"))
    assert at[1] == pytest.approx(dy, abs=2.5)
    assert at[0] < dx      # «28.07.2026» sits left of centre; « 00:00» follows


def test_only_the_start_date_moves(tmp_path) -> None:
    """Everything else on the form must stay exactly where it was."""
    plain = _generate(_hostel(), tmp_path / "a")
    moved = _generate(_hostel(stay_from_x=380.0, stay_from_y=250.0), tmp_path / "b")

    def words(pdf: Path, page: int) -> set:
        doc = fitz.open(pdf)
        try:
            return {(w[4], round(w[0], 1), round(w[1], 1))
                    for w in doc[page].get_text("words")
                    if "2026" not in w[4] and "00:00" not in w[4]}
        finally:
            doc.close()

    assert words(plain, 0) == words(moved, 0)
    assert words(plain, 1) == words(moved, 1)


# -------------------------------------------------------------- remembered


def test_the_spot_is_remembered_for_next_time(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.registration_address_repo import (
        RegistrationAddressRepository,
    )
    from src.services.registration_address_service import RegistrationAddressService

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    repo = RegistrationAddressRepository(db)
    address = _hostel()
    repo.upsert(address)

    service = RegistrationAddressService(repo)
    service.set_stay_from(address.id, (380.0, 250.0))

    back = repo.by_internal_code("x")
    assert (back.stay_from_x, back.stay_from_y) == (380.0, 250.0)
    # …and the next registration for that hostel uses it without being told
    assert _date_at(_generate(back, tmp_path / "out"))[1] == pytest.approx(250.0, abs=2.5)


def test_the_spot_can_be_put_back_to_the_forms_own(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.registration_address_repo import (
        RegistrationAddressRepository,
    )
    from src.services.registration_address_service import RegistrationAddressService

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    repo = RegistrationAddressRepository(db)
    repo.upsert(_hostel(stay_from_x=380.0, stay_from_y=250.0))
    address = repo.by_internal_code("x")

    service = RegistrationAddressService(repo)
    service.set_stay_from(address.id, None)
    back = repo.by_internal_code("x")
    assert back.stay_from_x is None and back.stay_from_y is None
    assert HostelService().stay_from_spot(back).is_default


def test_marking_a_hostel_that_is_gone_is_refused(tmp_path) -> None:
    from uuid import uuid4

    from src.common.errors import ValidationError
    from src.database.connection import Database
    from src.database.repositories.registration_address_repo import (
        RegistrationAddressRepository,
    )
    from src.services.registration_address_service import RegistrationAddressService

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    service = RegistrationAddressService(RegistrationAddressRepository(db))
    with pytest.raises(ValidationError):
        service.set_stay_from(uuid4(), (380.0, 250.0))


def test_other_hostels_keep_their_own_spot(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.registration_address_repo import (
        RegistrationAddressRepository,
    )
    from src.services.registration_address_service import RegistrationAddressService

    db = Database(tmp_path / "ofis.db")
    db.migrate()
    repo = RegistrationAddressRepository(db)
    first, second = _hostel(), _hostel()
    repo.upsert(first)
    repo.upsert(second.model_copy(update={"internal_code": "y", "label": "Y"}))

    RegistrationAddressService(repo).set_stay_from(first.id, (380.0, 250.0))
    assert repo.by_internal_code("y").stay_from_x is None
    assert repo.by_internal_code("x").stay_from_x == 380.0
