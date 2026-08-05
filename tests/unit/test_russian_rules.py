"""The Russian rules are the PROGRAM's rules — no prompt may forget them.

The office's complaint was that the same worker came back spelled three
ways from three screens. The cure is one rule text carried by every ask,
and this file is what keeps it that way: add a section tomorrow, forget
the rules, and the last test here fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from src.ai.russian import RUSSIAN_RULES, RUSSIAN_SHORT, with_rules
from src.ocr.translit import to_cyrillic

SRC = Path(__file__).resolve().parents[2] / "src"


# ------------------------------------------------------- what the rule says
@pytest.mark.parametrize("must", [
    "O'G'LI→УГЛИ", "ERGASH→ЭРГАШ", "Ҷ/ҷ→ДЖ/дж",
    "СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ", "ТАДЖИКИСТАН", "КИРГИЗИЯ",
    "не транслитерируй ИДЕНТИФИКАТОРЫ", "верни пустую",
])
def test_the_rule_covers_what_the_office_kept_correcting(must) -> None:
    assert must in RUSSIAN_RULES, must


def test_the_short_rule_is_short_but_carries_the_letters() -> None:
    assert len(RUSSIAN_SHORT) < len(RUSSIAN_RULES) / 3
    for must in ("O'→У", "Ҷ→ДЖ", "СУРХАНДАРЬИНСКАЯ ОБЛАСТЬ"):
        assert must in RUSSIAN_SHORT, must


def test_with_rules_puts_them_first() -> None:
    made = with_rules("ЗАДАЧА: прочитай документ.")
    assert made.startswith(RUSSIAN_RULES)
    assert made.endswith("ЗАДАЧА: прочитай документ.")
    assert with_rules("x", short=True).startswith(RUSSIAN_SHORT)


# --------------------------------------------- the program obeys its own rule
#: Every prompt the program sends, and where it lives. A prompt naming a
#: person, a place or an authority MUST carry the rules.
_PROMPTS = {
    "src/ai/prompts.py": ("_COMMON", "_INN_ONLY", "_REGISTRATION"),
    "src/services/perevod_service.py": ("_PROMPT",),
    "src/controllers/rusreg_controller.py": ("_PASSPORT_PROMPT",
                                             "_BIRTH_PROMPT"),
    "src/services/umumiy_service.py": ("_PROMPT",),
    "src/services/umumiy_templates.py": ("_TEXT_PROMPT",),
    "src/controllers/trud_ppu_controller.py": ("_CONTRACT_PROMPT",),
    "src/controllers/chek_controller.py": ("_CHEK_PROMPT",),
}


@pytest.mark.parametrize("path, names", sorted(_PROMPTS.items()))
def test_every_prompt_carries_the_rules(path, names) -> None:
    text = (SRC.parent / path).read_text(encoding="utf-8")
    for name in names:
        found = re.search(rf"^{re.escape(name)} = (.+)$", text, re.MULTILINE)
        assert found, f"{path}: {name} топилмади"
        head = found.group(1)
        assert "RUSSIAN_RULES" in head or "RUSSIAN_SHORT" in head, \
            f"{path}: {name} рус қоидаларини олмаган"


def test_no_section_writes_its_own_transcription_table() -> None:
    """One table, in one file — a second one would drift from it."""
    guilty = []
    for path in SRC.rglob("*.py"):
        if path.name == "russian.py":
            continue
        text = path.read_text(encoding="utf-8")
        # the giveaway: a prompt spelling out its own letter mapping
        if "O'G'LI→УГЛИ" in text or "O'G'LI → УГЛИ" in text:
            guilty.append(path.name)
    assert guilty == [], f"ўз жадвалини ёзган файллар: {guilty}"


# ------------------------------------------------ the deterministic net below
@pytest.mark.parametrize("latin, russian", [
    ("MATKARIMOV", "МАТКАРИМОВ"), ("UKTAMBOY", "УКТАМБОЙ"),
    ("ABDIRIMOVICH", "АБДИРИМОВИЧ"), ("JURAYEVA", "ЖУРАЕВА"),
    ("XO'JAYEV", "ХУЖАЕВ"), ("SAIDOV JAMSHID TESHA O‘G‘LI",
                             "САИДОВ ЖАМШИД ТЕША УГЛИ"),
    ("SHUKUROVA MOHIRA QIZI", "ШУКУРОВА МОХИРА КИЗИ"),
    ("G‘AYRAT", "ГАЙРАТ"), ("ERGASHEV", "ЭРГАШЕВ"),
])
def test_the_program_transcribes_the_same_way_it_tells_the_model_to(
        latin, russian) -> None:
    """What the rules ask of the model, the program does deterministically —
    so a careless reading is corrected rather than carried onto a form."""
    assert to_cyrillic(latin) == russian
