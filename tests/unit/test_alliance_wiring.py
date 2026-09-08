import pathlib


def test_main_window_registers_alliance():
    src = pathlib.Path("src/ui/main_window.py").read_text(encoding="utf-8")
    assert "АЛЬЯНСКОТ 2400" in src
    assert "AllianceView" in src and "AllianceController" in src
