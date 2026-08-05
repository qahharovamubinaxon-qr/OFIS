"""«tozalash.bat» — what the cleaner may delete, and what it may never.

The office asked how to clear the junk off its computer «фақат керакли
файллар учиб кетмаслиги керак». A cleaning script is the one kind of
program where a mistake cannot be undone, so this file reads the script
and refuses to let a dangerous path in: the office's own OFIS data — its
firms, addresses, blanks, arrangements, finished documents and archive —
lives in AppData\\Local\\OFIS, and nothing in that script may name it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tozalash.bat"

#: The verbs that destroy something.
_DESTROYS = ("rd ", "rmdir", "del ", "erase", "format", "remove-item")

#: Nothing the office would miss may ever appear on a destroying line.
_PROTECTED = (
    "local\\ofis",          # firms, addresses, blanks, layouts, output
    "roaming",              # anybody else's settings
    "documents", "мои документы",
    "desktop", "рабочий стол",
    "downloads", "загрузки",
    "onedrive",
    "recycle",              # the bin is the office's to empty, not ours
    "pagefile", "hiberfil", "swapfile",
    "program files",
    "\\users\\*",           # never a whole profile
    "c:\\windows\\system32",
    "dist\\ofis",           # the working program itself
)


def _lines() -> list[str]:
    return SCRIPT.read_text(encoding="utf-8").splitlines()


def _destroying_lines() -> list[str]:
    found = []
    for raw in _lines():
        line = raw.strip()
        low = line.lower()
        if low.startswith(("rem", "echo", "::")):
            continue
        if any(verb in low for verb in _DESTROYS):
            found.append(line)
    return found


def test_the_cleaner_exists_and_asks_first() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    assert "choice" in text, "тасдиқ сўралмайди"
    assert "errorlevel 2" in text, "«йўқ» жавоби ишламайди"


@pytest.mark.parametrize("protected", _PROTECTED)
def test_no_protected_path_is_ever_deleted(protected) -> None:
    guilty = [line for line in _destroying_lines()
              if protected in line.lower()]
    assert guilty == [], f"«{protected}» ўчириш сатрида: {guilty}"


def test_every_deletion_is_a_cache_that_comes_back() -> None:
    """Each destroying line must name one of the known throwaway places."""
    allowed = ("%temp%", "c:\\windows\\temp",
               "softwaredistribution\\download",
               "\\cache", "code cache", "crashdumps",
               "windows\\logs", "wer\\reportarchive",
               "thumbcache_", "iconcache_", "build\\ofis")
    for line in _destroying_lines():
        low = line.lower()
        assert any(place in low for place in allowed), \
            f"нотаниш жой ўчирилаяпти: {line}"


def test_it_never_deletes_a_whole_drive_or_wildcard_root() -> None:
    for line in _destroying_lines():
        low = line.lower().replace('"', "")
        for reckless in ("c:\\*", "c:\\ ", "%userprofile%\\*",
                         "%localappdata%\\*", "%appdata%\\*"):
            assert reckless not in low, f"жуда хавфли: {line}"


def test_the_script_is_a_windows_file() -> None:
    """.bat files must keep CRLF or cmd.exe misreads the last line."""
    raw = SCRIPT.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n"), "CRLF бузилган"
