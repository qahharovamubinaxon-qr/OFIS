"""КУК ЧЕК — the СФЕРА payment чек."""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.kukchek_renderer import (
    IPGU_PREFIX,
    KukChekData,
    output_name,
    render,
    uip_of,
    values,
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


_WORKER = dict(fam="КАХХАРОВ", ism="КАХРАМОН", otch="АБДИСАТТОР УГЛИ",
               inn="540963187924", when=date(2026, 7, 30),
               at=datetime(2026, 7, 30, 10, 54, 53),
               rubles=23600, kopecks=0)


def _blank(folder: Path) -> Path:
    from PIL import Image

    blank = folder / "CHEK.png"
    Image.new("RGB", (700, 1800), (245, 245, 245)).save(blank)
    return blank


def test_the_values_write_the_samples_manner() -> None:
    made = values(KukChekData(**_WORKER),
                  uip="10466146320086093007202611948663")
    assert made["top_date"] == "30 июля 2026 10:54:53 мск"
    assert made["inn"] == "540963187924"
    assert made["fam"] == "КАХХАРОВ"
    assert made["ism_otch"] == "КАХРАМОН АБДИСАТТОР УГЛИ"
    assert made["ipgu"] == "121000000000540963187924"
    assert made["ipgu"] == IPGU_PREFIX + made["inn"]
    assert made["summa_platezha"] == made["summa"] == made["itogo"] \
        == "23 600.00"
    assert made["propis"] == "Двадцать три тысячи шестьсот рублей 00 копеек"


def test_the_uip_carries_the_days_digits_inside() -> None:
    uip = uip_of(date(2026, 7, 30))
    assert len(uip) == 32 and uip.isdigit()
    assert uip[16:24] == "30072026"


def test_render_prints_bold_in_the_offices_indigo(tmp_path) -> None:
    """#3f1ba6, and thick — Matricha has one weight, so bold is stroked."""
    import numpy as np

    pdf = render(KukChekData(**_WORKER), _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        ink = doc[0].get_text().replace("\xa0", " ")
        assert "КАХХАРОВ" in ink
        assert "121000000000540963187924" in ink
        assert "23 600.00" in ink
        assert "Двадцать три тысячи шестьсот рублей" in ink
        pix = doc[0].get_pixmap(dpi=100)
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3].astype(int)
    from src.pdf.kukchek_renderer import BLUE, BOLD_STROKE

    marked = img.reshape(-1, 3)
    ink = marked[marked.sum(1) < 600]
    assert len(ink) > 200, "the чек left no ink"
    # glyph CORES only — the anti-aliased edges blend toward the paper
    core = ink[ink.sum(1) <= np.percentile(ink.sum(1), 40)]
    median = np.median(core, axis=0)
    wanted = np.array([c * 255 for c in BLUE])
    # the dot-matrix glyphs are thin, so even their cores touch the paper a
    # little at 100 dpi — the hue must be the office's, not the old blue
    assert np.abs(median - wanted).max() < 25,         f"ink {median} is not #3f1ba6 {wanted}"
    assert median[2] > median[0] > median[1], "not an indigo"
    assert BOLD_STROKE > 0, "the чек must print bold"


def test_a_short_sum_stays_on_one_line_a_long_one_wraps(tmp_path) -> None:
    """The office: «10000, 30000, 100000 — бир қаторга; 13578, 25470 —
    биринчи қаторга 4 сўз, қолгани иккинчисига»."""

    def _lines(rubles: int) -> list[str]:
        data = KukChekData(**{**_WORKER, "rubles": rubles})
        pdf = render(data, _blank(tmp_path))
        with fitz.open("pdf", pdf) as doc:
            return [sp["text"].strip()
                    for b in doc[0].get_text("dict")["blocks"]
                    for line in b.get("lines", []) for sp in line["spans"]
                    if any(w in sp["text"] for w in
                           ("рубл", "копеек", "тысяч", "дцать", "Сто"))]

    assert _lines(30000) == ["Тридцать тысяч рублей 00 копеек"]
    assert _lines(100000) == ["Сто тысяч рублей 00 копеек"]
    long_one = _lines(13578)
    assert len(long_one) == 2, f"a long sum must wrap: {long_one}"
    assert long_one[0] == "Тринадцать тысяч пятьсот семьдесят"
    assert long_one[0].count(" ") == 3, "the first line takes four words"
    assert long_one[1] == "восемь рублей 00 копеек"


def test_colour_and_weight_travel_in_the_layout(tmp_path) -> None:
    from src.pdf.kukchek_renderer import SLOTS, placed
    from src.services.kukchek_service import KukChekService

    service = KukChekService()
    blank = service.add_template("СФЕРА", _blank(tmp_path))
    assert SLOTS["itogo"].bold is True
    service.save_layout(blank, {"fields": {"itogo": [0.4, 0.5, 0.02]}})
    service.save_layout(blank, {"styles": {"itogo": {
        "colour": [1.0, 0.0, 0.0], "bold": False}}})
    slot = placed(service.layout(blank), SLOTS)["itogo"]
    assert slot.colour == (1.0, 0.0, 0.0) and slot.bold is False
    # the move survived the style being saved after it
    assert abs(slot.x - 0.4) < 1e-6 and abs(slot.baseline - 0.5) < 1e-6


def test_the_service_keeps_the_stamp_and_prints(tmp_path) -> None:
    from PIL import Image
    from src.services.kukchek_service import KukChekService

    service = KukChekService()
    blank = service.add_template("СФЕРА", _blank(tmp_path))

    stamp_src = tmp_path / "stamp.jpg"
    Image.new("RGB", (200, 200), (255, 255, 255)).save(stamp_src)
    with Image.open(stamp_src) as im:
        px = im.load()
        for i in range(60, 140):
            for j in range(60, 140):
                px[i, j] = (40, 40, 190)
        im.save(stamp_src)
    service.set_stamp(stamp_src)

    result = service.generate(KukChekData(**_WORKER), blank)
    assert result.saved.exists()
    assert result.saved.name.startswith("КАХХАРОВ_КАХРАМОН")
    with fitz.open(str(result.saved)) as doc:
        assert len(doc[0].get_images(full=True)) >= 2   # blank + печать


def test_the_bot_needs_a_blank_first() -> None:
    from src.controllers.ofis_modules import BY_KEY

    module = BY_KEY["kukchek"]
    assert module.photo_labels == ("Патент",)
    assert [a.field for a in module.asks] == ["when", "amount"]

    class _Ctl:
        @staticmethod
        def templates():
            return []

    assert "бланкаси йўқ" in module.ready({"kukchek": _Ctl()})


def test_the_filename_is_surname_name() -> None:
    assert output_name(KukChekData(**_WORKER)) == "КАХХАРОВ_КАХРАМОН.pdf"
