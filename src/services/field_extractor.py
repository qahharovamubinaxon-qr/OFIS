"""Flatten structured domain data into the ``{field_id: value}`` dict the PDF
engine fills. This is the one place the МВД business rules live:

* field 11 (patent expiry) = patent issue date **+ 1 year** (owner's rule).
* field 15 = "ФАМИЛИЯ ИМЯ ОТЧЕСТВО, ГРАЖДАНСТВО".
* field 16 (должность) is emitted only when it differs from the pre-printed
  default, so the default is left untouched on the template.

Both AI mode (OCR → Employee) and manual mode (table → Employee) call this, so
the two paths converge on identical output. Date sub-fields (д/м/г) all receive
the same ISO date; the mapping's formatter extracts the needed part.
"""

from __future__ import annotations

from datetime import date

from src.domain.company import Company
from src.domain.employee import Employee

DEFAULT_PROFESSION = "ПОДСОБНЫЙ РАБОЧИЙ"


def plus_one_year(d: date) -> date:
    """Patent validity end = issue + 1 year. Feb-29 → Mar-1 on non-leap years."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return date(d.year + 1, 3, 1)


def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def build_values(
    employee: Employee,
    company: Company,
    *,
    form_date: date,
    reg_number: int | str,
    profession: str | None = None,
) -> dict[str, str]:
    """Produce the flat field map for :func:`src.pdf.engine.fill`."""
    p = employee.passport
    pat = employee.patent

    fio_parts = [p.surname, p.name, p.patronymic or ""]
    fio = " ".join(x for x in fio_parts if x).strip()
    citizenship = p.nationality or ""
    fio_citizenship = f"{fio}, {citizenship}" if citizenship else fio

    values: dict[str, str] = {
        # identity (marks 1–4)
        "employee.surname": p.surname,
        "employee.name": p.name,
        "employee.patronymic": p.patronymic or "",
        "employee.citizenship": citizenship,
        # birth date (mark 5)
        "employee.birth.d": _iso(p.birth_date),
        "employee.birth.m": _iso(p.birth_date),
        "employee.birth.y": _iso(p.birth_date),
        # passport (marks 6–8)
        "employee.passport.series": p.series or "",
        "employee.passport.number": p.number,
        "employee.passport.issue.d": _iso(p.issue_date),
        "employee.passport.issue.m": _iso(p.issue_date),
        "employee.passport.issue.y": _iso(p.issue_date),
        "employee.passport.issued_by": p.issued_by or "",
        # form date (mark 13) + reg number (mark 14) + FIO/citizenship (mark 15)
        "doc.date.d": _iso(form_date),
        "doc.date.m": _iso(form_date),
        "doc.date.y": _iso(form_date),
        "doc.reg_number": str(reg_number),
        "employee.fio_citizenship": fio_citizenship,
    }

    if pat is not None:
        issue = pat.issue_date
        expiry = plus_one_year(issue) if issue else None
        values.update(
            {
                "patent.series": pat.series or "",
                "patent.number": pat.number,
                "patent.issue.d": _iso(issue),
                "patent.issue.m": _iso(issue),
                "patent.issue.y": _iso(issue),
                "patent.issued_by": pat.issued_by or "",
                "patent.from.d": _iso(issue),
                "patent.from.m": _iso(issue),
                "patent.from.y": _iso(issue),
                "patent.to.d": _iso(expiry),
                "patent.to.m": _iso(expiry),
                "patent.to.y": _iso(expiry),
            }
        )

    # должность (mark 16): only when the operator overrode the default.
    chosen = (profession or employee.profession or "").strip()
    if chosen and chosen.upper() != DEFAULT_PROFESSION:
        values["employee.profession"] = chosen

    _ = company  # company block is pre-printed on each company's template
    return {k: v for k, v in values.items() if v != ""}
