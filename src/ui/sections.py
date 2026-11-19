"""The program's sections, as the home screen needs them.

The navigation table in :mod:`src.ui.main_window` is a flat list of rows with
their group heading folded in as a separate entry — the shape a sidebar list
wants. The home screen wants the opposite shape: every section carrying the
heading it belongs under, so the cards can be laid out group by group.

Rather than keep a second list of sections (which would drift the first time
somebody adds a section to one and not the other), this reads the one table
there already is. Add a section to ``_NAV`` and its card appears by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

#: Sections that hold data or settings rather than making a document. They stay
#: in the sidebar but are not laid out as work cards on the home screen — the
#: home screen IS the dashboard, and the rest belong with it in the sidebar.
HOUSEKEEPING: frozenset[str] = frozenset({
    "nav.dashboard", "nav.companies", "nav.archive", "nav.search",
    "nav.settings",
})


@dataclass(frozen=True)
class Section:
    """One card on the home screen."""

    key: str
    title: str
    subtitle: str
    icon: str
    group: str


def sections_from_nav(nav: Iterable[Sequence]) -> list[Section]:
    """Every work section of ``nav``, each carrying its group heading.

    ``nav`` is the ``(group | None, key, title, subtitle, icon)`` table. A row
    whose group is ``None`` continues the group above it, which is how the
    sidebar writes a heading once for the rows that follow.
    """
    out: list[Section] = []
    group = ""
    for row in nav:
        heading, key, title, subtitle, icon = row
        if heading:
            group = str(heading)
        if key in HOUSEKEEPING:
            continue
        out.append(Section(key=str(key), title=str(title),
                           subtitle=str(subtitle), icon=str(icon),
                           group=group))
    return out


def grouped(sections: Iterable[Section]) -> list[tuple[str, list[Section]]]:
    """The sections in order, gathered under their headings.

    Order is the navigation's own — the office learned the program in that
    order, so the cards must not be re-sorted alphabetically underneath them.
    """
    out: list[tuple[str, list[Section]]] = []
    for section in sections:
        if not out or out[-1][0] != section.group:
            out.append((section.group, []))
        out[-1][1].append(section)
    return out


def matches(section: Section, query: str) -> bool:
    """Does this section answer what was typed in the search box?

    The office types in whatever alphabet is under their hands — «патент»,
    «patent», «ПАТЕНТ» — and sometimes a word from the subtitle («уведомление»)
    rather than the name. All of it is matched, case folded.
    """
    said = " ".join(query.split()).casefold()
    if not said:
        return True
    hay = f"{section.title} {section.subtitle} {section.key}".casefold()
    return all(word in hay for word in said.split())
