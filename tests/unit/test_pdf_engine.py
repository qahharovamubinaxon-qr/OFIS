"""PDF engine: fills the real МВД template and verifies a valid PDF comes out
with the inserted Cyrillic values actually present on the page."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "mvd_prilozhenie_7" / "template.pdf"
MAPPING = ROOT / "templates" / "mvd_prilozhenie_7" / "mapping.v1.json"


@pytest.mark.skipif(not TEMPLATE.exists(), reason="template not present")
def test_fill_produces_valid_pdf(tmp_path: Path) -> None:
    mapping = FieldMapping.load(MAPPING)
    values = {
        "employee.surname": "РАХИМОВ",
        "employee.passport.number": "123456789",
    }
    out = fill(TEMPLATE, mapping, values, tmp_path / "out.pdf")

    assert out.exists() and out.stat().st_size > 0
    doc = fitz.open(str(out))
    assert doc.page_count == 5  # template preserved, no pages lost
    # the surname we inserted is now real text on page 2
    assert "РАХИМОВ" in doc[1].get_text().replace(" ", "")
    doc.close()


def test_mapping_loads_and_is_calibrated() -> None:
    mapping = FieldMapping.load(MAPPING)
    assert mapping.template == "mvd_prilozhenie_7"
    assert len(mapping.calibrated_fields()) >= 10
    assert all(f.pitch and f.pitch > 10 for f in mapping.calibrated_fields() if f.type == "grid")
