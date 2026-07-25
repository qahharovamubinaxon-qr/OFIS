"""Build a per-address registration template from the blank form.

Takes the operator's address data (область/район/город/улица, дом/корпус/
строение/квартира, владелец ФИО, региональный номер), prints it onto
``templates/registration/blank.pdf`` per ``address_mapping.v1.json`` (Times New
Roman) and saves the result as that address's ``template.pdf``. The worker-fill
mapping then works on it unchanged — the blank shares the form's geometry.
"""

from __future__ import annotations

from pathlib import Path

from src.common.errors import TemplateMissingError
from src.config import paths
from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping


def _clean(v: str | None) -> str:
    return (v or "").strip()


class AddressTemplateBuilder:
    def __init__(self) -> None:
        self._blank = paths.templates_dir() / "registration" / "blank.pdf"
        self._mapping = paths.templates_dir() / "registration" / "address_mapping.v1.json"

    def available(self) -> bool:
        return self._blank.exists() and self._mapping.exists()

    def build(
        self,
        dest: Path,
        *,
        oblast: str | None = None,
        raion: str | None = None,
        gorod: str | None = None,
        ulitsa: str | None = None,
        dom: str | None = None,
        korpus: str | None = None,
        stroenie: str | None = None,
        kvartira: str | None = None,
        host_fio: str | None = None,
        regional_number: str | None = None,
    ) -> Path:
        """Fill the blank with the address block → ``dest`` (the new template)."""
        if not self.available():
            raise TemplateMissingError(
                "Registration blank/mapping missing",
                context={"blank": str(self._blank), "mapping": str(self._mapping)},
            )
        parts = _clean(host_fio).split()
        surname = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else ""
        patronymic = " ".join(parts[2:]) if len(parts) > 2 else ""

        values: dict[str, str] = {
            "addr.oblast": _clean(oblast),
            "addr.raion": _clean(raion),
            "addr.gorod": _clean(gorod),
            "addr.ulitsa": _clean(ulitsa),
            "addr.dom": f"дом {_clean(dom)}" if _clean(dom) else "",
            "addr.korpus": f"корпус {_clean(korpus)}" if _clean(korpus) else "",
            "addr.stroenie": f"строение {_clean(stroenie)}" if _clean(stroenie) else "",
            "addr.kvartira": f"квартира {_clean(kvartira)}" if _clean(kvartira) else "",
            "addr.host_surname": surname,
            "addr.host_name": name,
            "addr.host_patronymic": patronymic,
            "addr.host_line": _clean(host_fio).title(),
            "addr.regional_number": (
                f"№ {_clean(regional_number)}" if _clean(regional_number) else ""
            ),
        }
        mapping = FieldMapping.load(self._mapping)
        return fill(self._blank, mapping, values, dest)
