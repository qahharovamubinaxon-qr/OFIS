"""ТРУД ППУ — the three sheets printed off a patent, a contract and a notice.

Offline: the AI is stubbed, the blanks are plain pages of the office's own
sizes. What is checked is the deterministic half — the two values the office
derives rather than reads (the patent's expiry and its «Номер дела»), that every
value lands on the sheet it belongs to, and that sheet 1 is filled by the ППУ's
own code so it can never drift from the ППУ section.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths

#: The office's own sheets: the patent page landscape, the notice page portrait.
_PAGE2_SIZE = (1600.0, 900.0)
_PAGE3_SIZE = (899.0, 1599.0)
_FRONT_SIZE = (842.0, 474.0)


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _blank(path: Path, size: tuple[float, float]) -> Path:
    doc = fitz.open()
    doc.new_page(width=size[0], height=size[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def _plain(text: str) -> str:
    """PDF text as it reads, not as MuPDF spells it.

    Liberation Sans draws the hyphen and the soft hyphen with one glyph, and a
    space laid down by a TextWriter comes back as NO-BREAK SPACE, so MuPDF hands
    «18.07.2024-» back as «18.07.2024\xad». Fold both to what was drawn.
    """
    return " ".join(text.replace("\xa0", " ").replace("\xad", "-").split())


def _data(**over):
    from src.pdf.trud_ppu_renderer import TrudPpuData

    base = {
        "surname": "МУРТАЗОЕВ", "name": "АББОСХОН",
        "patronymic": "АБДУЛОХОНОВИЧ",
        "birth_date": date(1990, 3, 3), "gender": "Мужской",
        "citizenship": "УЗБЕКИСТАН", "document": "FA 7822242",
        "patent_series": "77", "patent_number": "2400328451",
        "patent_issue": date(2024, 7, 18),
        "contract_date": date(2024, 9, 20), "firm": "ООО “ЭКСПЕРТ”",
        "uved_number": "4785796716",
    }
    base.update(over)
    return TrudPpuData(**base)


# --------------------------------------------------------- derived values


def test_patent_runs_to_the_same_date_next_year() -> None:
    """A patent expires exactly one year on — NOT «a day short of a year» the
    way the ППУ and разрешение do."""
    from src.pdf.trud_ppu_renderer import plus_one_year

    assert plus_one_year(date(2024, 7, 18)) == date(2025, 7, 18)
    assert plus_one_year(date(2023, 12, 31)) == date(2024, 12, 31)
    # 29 February has no anniversary — the office writes the 28th
    assert plus_one_year(date(2024, 2, 29)) == date(2025, 2, 28)
    assert plus_one_year(None) is None


def test_case_number_turns_the_patent_round() -> None:
    from src.pdf.trud_ppu_renderer import case_number, patent_serial

    assert patent_serial("77", "2400328451") == "77 № 2400328451"
    assert case_number("77", "2400328451") == "2400328451-77ПАТ"
    assert case_number("77", "2600356251") == "2600356251-77ПАТ"
    # the readers hand the number back spaced as the patent prints it
    assert case_number("77", "26003 56251") == "2600356251-77ПАТ"
    # nothing to swap, and never a dangling dash
    assert case_number("", "2400328451") == "2400328451ПАТ"
    assert case_number("77", "") == ""


# ------------------------------------------------------------- rendering


def test_every_value_lands_on_its_own_sheet(tmp_path) -> None:
    from src.pdf.trud_ppu_renderer import render

    pdf = render(
        _data(),
        front=_blank(tmp_path / "front.pdf", _FRONT_SIZE),
        page2=_blank(tmp_path / "page2.pdf", _PAGE2_SIZE),
        page3=_blank(tmp_path / "page3.pdf", _PAGE3_SIZE))

    doc = fitz.open("pdf", pdf)
    assert len(doc) == 3
    front, patent, notice = (_plain(p.get_text()) for p in doc)

    # sheet 1 — the ППУ front, filled by the ППУ's own code
    assert "Муртазоев Аббосхон Абдулохонович" in front
    assert "Murtazoev Abboskhon Abdulokhonovich" in front
    assert "03.03.1990" in front and "УЗБЕКИСТАН" in front
    assert "№FA7822242" in front

    # sheet 2 — ①..⑦
    assert "77 № 2400328451" in patent          # ①
    assert patent.count("18.07.2024") >= 2      # ② and ⑤
    assert "18.07.2024-" in patent              # ③, first line
    assert "18.07.2025" in patent               # ③, second line — derived
    assert "2400328451-77ПАТ" in patent         # ④
    assert "20.09.2024" in patent               # ⑥
    assert "ЭКСПЕРТ" in patent                  # ⑦

    # sheet 3 — ⑧ and ⑨, and nothing from sheet 2
    assert "№ 4785796716" in notice
    assert "Муртазоев Аббосхон Абдулохонович" in notice
    assert "ЭКСПЕРТ" not in notice and "2400328451" not in notice


def test_values_sit_where_the_office_measured_them(tmp_path) -> None:
    """The slots are fractions of the page, so they must land at the office's
    own measured spots whatever size the blank is photographed at."""
    from src.pdf.trud_ppu_renderer import render
    from src.pdf.trud_ppu_spec import PAGE2, PAGE3

    pdf = render(
        _data(),
        front=_blank(tmp_path / "front.pdf", _FRONT_SIZE),
        page2=_blank(tmp_path / "page2.pdf", _PAGE2_SIZE),
        page3=_blank(tmp_path / "page3.pdf", _PAGE3_SIZE))
    doc = fitz.open("pdf", pdf)

    def where(page, needle: str) -> tuple[float, float]:
        """The left edge and the BASELINE of the value, in page fractions."""
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if _plain(span["text"]) == needle:
                        x, y = span["origin"]
                        return x / page.rect.width, y / page.rect.height
        raise AssertionError(f"{needle!r} саҳифада йўқ")

    # ① sits on the «Серия и номер» column …
    slot = PAGE2["patent_serial"]
    x, baseline = where(doc[1], "77 № 2400328451")
    assert abs(x - slot.x) < 0.004 and abs(baseline - slot.baseline) < 0.004
    # ⑦ two thirds across the sheet, on the «Источник уведомления» column
    assert abs(where(doc[1], "ООО “ЭКСПЕРТ”")[0] - PAGE2["firm"].x) < 0.004
    # ③ really is two lines, one above the other, at the same left edge
    top_x, top_y = where(doc[1], "18.07.2024-")
    bottom_x, bottom_y = where(doc[1], "18.07.2025")
    assert abs(top_x - bottom_x) < 0.002
    assert bottom_y > top_y, "the term must read downwards, issued then expiring"
    # ⑧ sits under the page title, ⑨ far below it
    slot = PAGE3["uved_number"]
    x, baseline = where(doc[2], "№ 4785796716")
    assert abs(x - slot.x) < 0.004 and abs(baseline - slot.baseline) < 0.004
    assert where(doc[2], "Муртазоев Аббосхон Абдулохонович")[1] > baseline


def test_the_notice_name_may_differ_from_the_contract_name(tmp_path) -> None:
    """The notification is filed under the name the МВД accepted, which is not
    always spelled the way the contract spells it."""
    from src.pdf.trud_ppu_renderer import render

    pdf = render(
        _data(uved_fio="Муртазоев Аббосхон"),
        front=_blank(tmp_path / "front.pdf", _FRONT_SIZE),
        page2=_blank(tmp_path / "page2.pdf", _PAGE2_SIZE),
        page3=_blank(tmp_path / "page3.pdf", _PAGE3_SIZE))
    notice = _plain(fitz.open("pdf", pdf)[2].get_text())
    assert "Муртазоев Аббосхон" in notice
    assert "АБДУЛОХОНОВИЧ" not in notice.upper().replace("МУРТАЗОЕВ АББОСХОН", "")


def test_a_patent_that_states_its_own_expiry_wins(tmp_path) -> None:
    from src.pdf.trud_ppu_renderer import render

    pdf = render(
        _data(patent_to=date(2025, 6, 1)),
        front=_blank(tmp_path / "front.pdf", _FRONT_SIZE),
        page2=_blank(tmp_path / "page2.pdf", _PAGE2_SIZE),
        page3=_blank(tmp_path / "page3.pdf", _PAGE3_SIZE))
    patent = _plain(fitz.open("pdf", pdf)[1].get_text())
    assert "01.06.2025" in patent and "18.07.2025" not in patent


# -------------------------------------------------------------- service


def test_service_saves_three_pictures_and_refuses_without_blanks(tmp_path,
                                                                 monkeypatch):
    from src.services import trud_ppu_service as svc_mod
    from src.services.trud_ppu_service import TrudPpuService

    desktop = tmp_path / "desktop"
    desktop.mkdir()
    monkeypatch.setattr(svc_mod.paths, "desktop_dir", lambda: desktop)
    monkeypatch.setattr("src.services.ppu_service.paths.desktop_dir",
                        lambda: desktop)

    service = TrudPpuService()
    fields = {
        "surname": "МУРТАЗОЕВ", "name": "АББОСХОН",
        "patent_series": "77", "patent_number": "2400328451",
        "patent_issue": date(2024, 7, 18),
        "contract_date": date(2024, 9, 20), "firm": "ООО “ЭКСПЕРТ”",
        "uved_number": "4785796716",
    }

    # no blanks at all — the office is told which one is missing, not crashed at
    with pytest.raises(Exception, match="ППУ бланкаси"):
        service.generate(**fields)

    ppu_template = tmp_path / "ppu"
    _blank(ppu_template / "front.pdf", _FRONT_SIZE)
    _blank(ppu_template / "back.pdf", _FRONT_SIZE)
    with pytest.raises(Exception, match="ТРУД ППУ бланкаси"):
        service.generate(ppu_template=ppu_template, **fields)

    page2 = _blank(tmp_path / "in2.pdf", _PAGE2_SIZE)
    page3 = _blank(tmp_path / "in3.pdf", _PAGE3_SIZE)
    template = service.add_template("ОФИС", page2, page3)
    assert template in service.templates()

    result = service.generate(ppu_template=ppu_template, template=template,
                              **fields)
    assert len(result.pages) == 3 and len(result.saved) == 3
    assert all(p.exists() and p.parent == desktop for p in result.saved)
    assert [p.name for p in result.saved] == [
        "МУРТАЗОЕВ ТРУД ППУ 1.png", "МУРТАЗОЕВ ТРУД ППУ 2.png",
        "МУРТАЗОЕВ ТРУД ППУ 3.png"]
    assert result.case_number == "2400328451-77ПАТ"
    assert result.valid_to == date(2025, 7, 18)


# --------------------------------------------------------- reading the PDFs


def test_contract_is_read_from_its_own_text_not_photographed(monkeypatch,
                                                             tmp_path):
    """A PDF this program produced carries text; reading that is exact and
    costs no picture upload."""
    from src.controllers import trud_ppu_controller as mod

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "TRUDOVOY DOGOVOR No 12 ot 20.09.2024 g. Moskva "
                              "OOO EKSPERT prinimaet na rabotu", fontsize=11)
    page.insert_text((60, 120), "Murtazoev Abboskhon, pasport FA7822242",
                     fontsize=11)
    # a real contract runs for pages; only its length decides text-or-pictures
    for line in range(20):
        page.insert_text((60, 160 + line * 14),
                         f"punkt {line + 1}. Storony dogovorilis o nizhesleduyushem",
                         fontsize=9)
    data = doc.tobytes()

    seen = {}

    def fake_ask(key, prompt, images=None, **kw):
        seen["images"] = images
        seen["prompt"] = prompt
        return ('{"contract_date":"20.09.2024","firm":"ООО \\"ЭКСПЕРТ\\"",'
                '"surname":"МУРТАЗОЕВ","name":"АББОСХОН","patronymic":"",'
                '"birth_date":"03.03.1990","gender":"Мужской",'
                '"citizenship":"УЗБЕКИСТАН","passport":"FA7822242"}')

    monkeypatch.setattr(mod, "ask", fake_ask)
    controller = mod.TrudPpuController(ocr=None, service=None,
                                       key_getter=lambda: "k")
    fields = controller.read_contract(data)

    assert seen["images"] is None, "a text PDF must not be uploaded as pictures"
    assert "TRUDOVOY DOGOVOR" in seen["prompt"]
    assert fields["contract_date"] == "20.09.2024"
    assert fields["firm"] == "ООО “ЭКСПЕРТ”"     # quotes as the site shows them
    assert fields["document"] == "FA7822242"


def test_a_scanned_contract_goes_up_as_pictures(monkeypatch, tmp_path):
    from src.controllers import trud_ppu_controller as mod

    doc = fitz.open()
    doc.new_page(width=595, height=842)          # no text at all
    data = doc.tobytes()

    seen = {}

    def fake_ask(key, prompt, images=None, **kw):
        seen["images"] = images
        return '{"contract_date":"","firm":"","surname":""}'

    monkeypatch.setattr(mod, "ask", fake_ask)
    controller = mod.TrudPpuController(ocr=None, service=None,
                                       key_getter=lambda: "k")
    controller.read_contract(data)
    assert seen["images"] and len(seen["images"]) == 1


def test_notice_number_keeps_its_leading_zero(monkeypatch):
    """JSON drops a leading zero off a number; the reader asks for a string and
    keeps only the digits, so «№ 0478579671» survives."""
    from src.controllers import trud_ppu_controller as mod

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "UVEDOMLENIE " + "x" * 200, fontsize=11)

    monkeypatch.setattr(mod, "ask", lambda *a, **k:
                        '{"number":"№ 0478579671","surname":"МУРТАЗОЕВ",'
                        '"name":"АББОСХОН","patronymic":"АБДУЛОХОНОВИЧ"}')
    controller = mod.TrudPpuController(ocr=None, service=None,
                                       key_getter=lambda: "k")
    fields = controller.read_uved(doc.tobytes())
    assert fields["uved_number"] == "0478579671"
    assert fields["uved_fio"] == "МУРТАЗОЕВ АББОСХОН АБДУЛОХОНОВИЧ"


def test_a_broken_ai_answer_leaves_the_form_empty_not_crashed(monkeypatch):
    from src.controllers import trud_ppu_controller as mod

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    monkeypatch.setattr(mod, "ask", lambda *a, **k: "не JSON, а извинения")
    controller = mod.TrudPpuController(ocr=None, service=None,
                                       key_getter=lambda: "k")
    assert all(value == "" for value in controller.read_uved(doc.tobytes()).values())


# ------------------------------------------------- the firm, cut down to size


def test_the_firm_is_cut_down_to_how_the_office_writes_it() -> None:
    """A контракт spells the employer out in full; the sheet has one cell."""
    from src.pdf.trud_ppu_renderer import short_firm

    assert short_firm(
        'Общество с ограниченной ответственностью "СФЕРА", в лице директора'
    ) == "ООО “СФЕРА”"
    assert short_firm('ООО "ЭКСПЕРТ"') == "ООО “ЭКСПЕРТ”"
    assert short_firm("Индивидуальный предприниматель Матаков Алишер Салимович"
                      ) == "ИП МАТАКОВ А.С."
    assert short_firm("ИП Матаков А.С.") == "ИП МАТАКОВ А.С."
    assert short_firm("ЗАО «СТРОЙИНВЕСТ-ГРУПП»") == "ЗАО “СТРОЙИНВЕСТ-ГРУПП”"
    # nothing recognised is passed through rather than mangled
    assert short_firm("Крестьянское хозяйство Заря") == "Крестьянское хозяйство Заря"
    assert short_firm("") == ""


def test_the_firm_is_set_larger_than_the_rest_of_the_sheet() -> None:
    from src.pdf.trud_ppu_spec import PAGE2

    assert PAGE2["firm"].size > PAGE2["issue_date"].size
    # two points larger on the 900pt sheet the office handed over
    assert abs((PAGE2["firm"].size - PAGE2["issue_date"].size) * 900 - 2.0) < 0.01


# ------------------------------------------------------ the missing three


def test_sex_comes_off_the_patronymic_because_a_patent_never_prints_it() -> None:
    from src.controllers.trud_ppu_controller import gender_from_patronymic

    assert gender_from_patronymic("Зафаровна") == "Женский"
    assert gender_from_patronymic("Абдулохонович") == "Мужской"
    assert gender_from_patronymic("Хайдар қизи") == "Женский"
    assert gender_from_patronymic("Азиз ўғли") == "Мужской"
    assert gender_from_patronymic("") == ""
    assert gender_from_patronymic("Смит") == ""


def test_the_patents_twelve_digit_inn_is_never_read_as_a_passport() -> None:
    """The patent prints «FB0717527 / 072501692992» on ONE line."""
    from src.controllers.trud_ppu_controller import _passport

    assert _passport("FB0717527 / 072501692992") == "FB0717527"
    assert _passport("FA 7822242") == "FA7822242"
    assert _passport("4012345678") == "4012345678"
    assert _passport("") == ""


def test_the_notification_number_is_found_in_the_text_when_the_ai_misses_it():
    from src.controllers.trud_ppu_controller import uved_number_from_text

    assert uved_number_from_text(
        "Уведомление о заключении трудового договора № 4785796716 от 20.09.2024"
    ) == "4785796716"
    # a leading zero survives, because it is read as text and not as a number
    assert uved_number_from_text("Регистрационный номер № 0478579671"
                                 ) == "0478579671"
    # a twelve-digit ИНН is not a notification number
    assert uved_number_from_text("ИНН 072501692992 работника") == ""
    assert uved_number_from_text("") == ""


# -------------------------------------- the blank the office actually uploaded


def _front_blank(path: Path, *, shift: float, scale: float) -> Path:
    """A ППУ front blank framed the way a fresh photograph of it would be.

    Draws the seven label rows the fitter anchors on, plus the two values the
    site leaves on the sheet, at ``shift``/``scale`` away from the reference
    frame — which is exactly how the office's three real blanks differ.
    """
    import fitz
    from src.pdf.engine import _font_file

    # reference cap-tops of «Физическое лицо» … «Гражданство», off the office's
    # own blank. The fitter anchors on rows 1 and 6 of this list.
    reference = (0.1409, 0.1868, 0.2454, 0.3425, 0.4000, 0.4554, 0.5525)
    labels = ("Физическое лицо ААА", "ФИО ААА", "ФИО лат. ААА",
              "Дата рождения ААА", "Пол ААА", "Место рождения ААА",
              "Гражданство ААА")
    doc = fitz.open()
    page = doc.new_page(width=841.89, height=473.56)
    # the built-in Helvetica has no Cyrillic at all and would draw nothing
    page.insert_font(fontname="lb", fontfile=str(_font_file("OfisArialBold")))
    height, width = page.rect.height, page.rect.width
    size = 0.0116 * height * scale

    def place(top: float) -> float:
        """Where a reference row lands on a blank framed like this one."""
        return (shift + (top - 0.1868) * scale) * height

    for top, text in zip(reference, labels, strict=True):
        # insert_text takes the BASELINE; the cap-top is a cap height above it
        page.insert_text((0.178 * width, place(top) + size * 0.716), text,
                         fontname="lb", fontsize=size)
    for top, text in ((0.7113, "Отсутствует"), (0.8280, "Нет")):
        page.insert_text((0.3135 * width, place(top) + size * 1.2 * 0.716), text,
                         fontname="lb", fontsize=size * 1.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


@pytest.mark.parametrize(("shift", "scale"), [
    (0.1868, 1.0),        # framed exactly like the reference
    (0.2042, 1.0246),     # the office's third blank: lower and 2.5% bigger
    (0.1750, 0.97),       # framed higher and smaller
])
def test_values_land_on_their_labels_whatever_blank_was_uploaded(
        tmp_path, shift, scale) -> None:
    """The three real ППУ fronts in the office are framed differently. Fixed
    fractions land above the labels on two of them — «қийшиқ» — so the blank is
    measured and every slot mapped onto it."""
    import fitz
    from src.pdf.blank_fit import text_bands
    from src.pdf.ppu_renderer import PpuData, _fill_front

    blank = _front_blank(tmp_path / f"front_{shift}_{scale}.pdf",
                         shift=shift, scale=scale)
    doc = fitz.open(str(blank))
    _fill_front(doc[0], PpuData(
        surname="МУРТАЗОЕВ", name="АББОСХОН", patronymic="АБДУЛОХОНОВИЧ",
        birth_date=date(1990, 3, 3), gender="Мужской",
        citizenship="УЗБЕКИСТАН", document="FA 7822242"))

    filled = fitz.open("pdf", doc.tobytes())[0]
    shot = filled.get_pixmap(matrix=fitz.Matrix(4.0, 4.0))
    import cv2
    import numpy as np
    arr = np.frombuffer(shot.samples, np.uint8).reshape(
        shot.height, shot.width, shot.n)
    grey = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)

    label_tops = [t for t, _b in text_bands(grey, 0.17, 0.30)]
    value_tops = [t for t, _b in text_bands(grey, 0.33, 0.62)]
    assert len(label_tops) >= 7, "the synthetic blank did not draw its labels"
    assert value_tops, "nothing was written in the value column"
    # ФИО, ФИО лат., Дата рождения, Пол, Место рождения, Гражданство — every one
    # of them has a value whose cap-top is level with its label's, whatever the
    # framing. Matched by nearest rather than by index: a value row can split
    # into two ink bands and that must not fail the check.
    for label in (1, 2, 3, 4, 5, 6):
        top = label_tops[label]
        nearest = min(value_tops, key=lambda v, t=top: abs(v - t))
        assert abs(nearest - top) < 0.005, (
            f"row {label}: label {top:.4f}, nearest value {nearest:.4f} — "
            "the value column does not sit on the labels")


# ------------------------- the patent, when the patent card is not to hand
def _uved_pdf(text: str = "UVEDOMLENIE " + "x" * 200) -> bytes:
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((60, 80), text, fontsize=11)
    return doc.tobytes()


def _contract_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "TRUDOVOY DOGOVOR ot 20.09.2024", fontsize=11)
    for line in range(20):
        page.insert_text((60, 120 + line * 14), "punkt " + "x" * 60, fontsize=9)
    return doc.tobytes()


def _controller(monkeypatch, answer: str):
    from src.controllers import trud_ppu_controller as mod

    monkeypatch.setattr(mod, "ask", lambda *a, **k: answer)
    return mod.TrudPpuController(ocr=None, service=None, key_getter=lambda: "k")


def test_the_contract_gives_up_the_patent_it_names(monkeypatch) -> None:
    """«агар патент йукламасам шуларни ичидеги малумотлардан фойдалансин».

    A трудовой договор names the worker's patent in its opening paragraph.
    The office often has the contract and the notification but not the patent
    card, and the three patent boxes came out blank.
    """
    controller = _controller(monkeypatch, (
        '{"contract_date":"20.09.2024","firm":"ООО \\"СОЗВЕЗДИЕ\\"",'
        '"surname":"АСРАНОВ","patent_series":"77",'
        '"patent_number":"2400328451","patent_issued":"18.07.2024"}'))
    fields = controller.read_contract(_contract_pdf())
    assert fields["weak_patent_series"] == "77"
    assert fields["weak_patent_number"] == "2400328451"
    assert fields["weak_patent_issued"] == "18.07.2024"


def test_the_notification_gives_up_the_patent_it_names(monkeypatch) -> None:
    controller = _controller(monkeypatch, (
        '{"number":"4785796716","surname":"АСРАНОВ","patent_series":"77",'
        '"patent_number":"2400328451","patent_issued":"18.07.2024"}'))
    fields = controller.read_uved(_uved_pdf())
    assert fields["uved_number"] == "4785796716"
    assert fields["weak_patent_number"] == "2400328451"


def test_the_notifications_own_number_is_not_taken_for_the_patents(monkeypatch):
    """The one confusion the prompt warns about, refused in code as well."""
    controller = _controller(monkeypatch, (
        '{"number":"4785796716","patent_series":"77",'
        '"patent_number":"4785796716","patent_issued":"18.07.2024"}'))
    fields = controller.read_uved(_uved_pdf())
    assert fields["uved_number"] == "4785796716"
    assert fields["weak_patent_number"] == ""
    assert fields["weak_patent_series"] == ""


def test_a_document_that_names_no_patent_offers_nothing(monkeypatch) -> None:
    """Nothing invented: a contract that is silent about the patent stays so."""
    controller = _controller(monkeypatch, (
        '{"contract_date":"20.09.2024","firm":"ООО \\"СОЗВЕЗДИЕ\\""}'))
    fields = controller.read_contract(_contract_pdf())
    assert all(fields[key] == "" for key in
               ("weak_patent_series", "weak_patent_number",
                "weak_patent_issued"))


def test_the_patent_is_asked_for_in_both_prompts() -> None:
    from src.controllers import trud_ppu_controller as mod

    for prompt in (mod._CONTRACT_PROMPT, mod._UVED_PROMPT):
        assert "patent_series" in prompt and "patent_number" in prompt
        assert "НЕ ВЫДУМЫВАЙ" in prompt, "ўйлаб топмаслик айтилмаган"
