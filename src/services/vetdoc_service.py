"""МЕРКУРИЙ — дўкон маълумотномаси: ёзув, сайт саҳифаси ва бланка.

Бир «чоп этиш» учта нарсани бирданига ясайди:

1. **ёзув** — ``vetdoc/records/<КОД>.json``, маълумотнинг ўзи шу ерда туради;
2. **сайт саҳифаси** — ``vetdoc/site/<КОД>.html`` ва янгиланган рўйхат
   (``index.html``), дўкон доменига қўйиладиган тайёр папка;
3. **бланка** — QR'и ўша саҳифага қарайдиган PDF.

Ҳаммаси AppData да: EXE қайта йиғилса ҳам ёзувлар ҳам, сайт ҳам жойида қолади.
База эмас, оддий файллар — нусха олиш ҳам, кўчириш ҳам осон бўлсин.

Сайт **чиқариб берилади**, ўзи ҳеч қаёққа юбормайди: папкани дўкон ўз домени
ёки GitHub Pages га қўяди. Дастур мижоз маълумотини ўзидан ташқарига
чиқармайди — бу атайин шундай.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.domain.vetdoc import Animal, DocRef, Shop, Treatment, VetRecord
from src.pdf.vetdoc_renderer import output_name, render
from src.services.vetdoc_page import index_html, page_html

log = get_logger(__name__)

SECTION = "vetdoc"
LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
#: Созламадаги калитлар — дўкон бир марта ёзиб қўяди.
SHOP_KEYS = ("name", "legal", "address", "phone", "site", "inn")


def _dir(*parts: str) -> Path:
    folder = paths.data_dir().joinpath(SECTION, *parts)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def records_dir() -> Path:
    return _dir("records")


def site_dir() -> Path:
    return _dir("site")


def logo_path() -> Path:
    return paths.data_dir() / SECTION / "logo.png"


# ------------------------------------------------------------------ JSON
def to_dict(record: VetRecord) -> dict:
    data = dataclasses.asdict(record)
    data["issued"] = record.issued.isoformat() if record.issued else ""
    return data


def _rows(raw: object, factory: type) -> list:
    """Жадвал қаторлари — нотаниш калитлар ўтказиб юборилади.

    Ёзув файли эскироқ (ёки янгироқ) бўлса ҳам очилиши керак: битта қўшилган
    майдон туфайли дўконнинг архиви ўқилмай қолмасин.
    """
    known = {f.name for f in dataclasses.fields(factory)}
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            out.append(factory(**{k: str(v or "") for k, v in item.items()
                                  if k in known}))
    return out


def from_dict(data: dict) -> VetRecord:
    known = {f.name for f in dataclasses.fields(VetRecord)}
    plain = {k: v for k, v in data.items()
             if k in known and k not in ("issued", "docs", "animals",
                                         "treatments")}
    record = VetRecord(**{k: str(v or "") for k, v in plain.items()})
    issued = str(data.get("issued") or "")
    if issued:
        try:
            record.issued = date.fromisoformat(issued)
        except ValueError:
            log.warning("vetdoc: сана ўқилмади: %r", issued)
    record.docs = _rows(data.get("docs"), DocRef)
    record.animals = _rows(data.get("animals"), Animal)
    record.treatments = _rows(data.get("treatments"), Treatment)
    return record


@dataclass(frozen=True)
class VetDocResult:
    """Бир чоп этишнинг натижаси."""

    record: VetRecord
    pdf: Path
    page: Path
    link: str


class VetDocService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ------------------------------------------------------------- дўкон
    def shop(self) -> Shop:
        if self._settings is None:
            return Shop()
        values = {key: str(self._settings.get(f"{SECTION}.shop.{key}", "") or "")
                  for key in SHOP_KEYS}
        return Shop(**values)

    def save_shop(self, shop: Shop) -> None:
        if self._settings is None:
            return
        for key in SHOP_KEYS:
            self._settings.set(f"{SECTION}.shop.{key}", getattr(shop, key, ""))
        log.info("МЕРКУРИЙ: дўкон маълумоти сақланди")

    def logo(self) -> Path | None:
        found = logo_path()
        return found if found.exists() else None

    def set_logo(self, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in LOGO_SUFFIXES or not source.exists():
            raise ValidationError("Логотип PNG, JPG ёки WEBP расм бўлиши керак")
        target = logo_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".png":
            shutil.copyfile(source, target)
        else:
            self._as_png(source, target)
        log.info("МЕРКУРИЙ: логотип юкланди")
        return target

    @staticmethod
    def _as_png(source: Path, target: Path) -> None:
        from PIL import Image

        with Image.open(source) as img:
            img.convert("RGBA").save(target, format="PNG")

    # ------------------------------------------------------------ ҳавола
    def link_for(self, record: VetRecord) -> str:
        """QR ичига тушадиган ҳавола.

        Домен ёзилмаган бўлса — фақат код: QR барибир ишлайди, мижоз кодни
        сайтга қўлда киритиб текширади.
        """
        site = (self.shop().site or "").strip().rstrip("/")
        if not site:
            return record.code
        if not site.startswith(("http://", "https://")):
            site = "https://" + site
        return f"{site}/{record.code}.html"

    # ------------------------------------------------------------ ёзувлар
    def path_of(self, code: str) -> Path:
        return records_dir() / f"{code}.json"

    def store(self, record: VetRecord) -> Path:
        target = self.path_of(record.code)
        target.write_text(json.dumps(to_dict(record), ensure_ascii=False,
                                     indent=2), encoding="utf-8")
        return target

    def load(self, code: str) -> VetRecord | None:
        found = self.path_of(code)
        if not found.exists():
            return None
        try:
            return from_dict(json.loads(found.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.warning("vetdoc: ёзув ўқилмади (%s): %s", code, exc)
            return None

    def records(self) -> list[VetRecord]:
        """Барча ёзувлар — янгиси юқорида."""
        found = []
        for file in records_dir().glob("*.json"):
            record = self.load(file.stem)
            if record is not None:
                found.append(record)
        found.sort(key=lambda r: (r.issued or date.min, r.code), reverse=True)
        return found

    # -------------------------------------------------------------- сайт
    def write_page(self, record: VetRecord) -> Path:
        target = site_dir() / f"{record.code}.html"
        target.write_text(page_html(record, self.shop()), encoding="utf-8")
        return target

    def rebuild_site(self) -> Path:
        """Ҳамма ёзувдан сайтни бошидан ясаш — папкани кўчиришдан олдин."""
        shop = self.shop()
        records = self.records()
        for record in records:
            (site_dir() / f"{record.code}.html").write_text(
                page_html(record, shop), encoding="utf-8")
        index = site_dir() / "index.html"
        index.write_text(index_html(records, shop), encoding="utf-8")
        log.info("МЕРКУРИЙ: сайт янгиланди — %d ёзув", len(records))
        return site_dir()

    def export_site(self, target: Path) -> Path:
        """Сайтни бошқа папкага нусхалаш (домен ёки GitHub Pages папкаси)."""
        self.rebuild_site()
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        for file in site_dir().glob("*.html"):
            shutil.copyfile(file, target / file.name)
        log.info("МЕРКУРИЙ: сайт чиқарилди — %s", target)
        return target

    # ------------------------------------------------------------ бланка
    def publish(self, record: VetRecord,
                out_dir: Path | None = None) -> VetDocResult:
        """Ёзувни сақлаш, саҳифасини ясаш ва бланкани PDF қилиш."""
        if not (record.title or record.product or record.animals):
            raise ValidationError(
                "Маҳсулот/ҳайвон ёзилмаган — камида номини киритинг.")
        if record.issued is None:
            record.issued = date.today()
        self.store(record)
        page = self.write_page(record)
        (site_dir() / "index.html").write_text(
            index_html(self.records(), self.shop()), encoding="utf-8")

        link = self.link_for(record)
        folder = Path(out_dir) if out_dir is not None \
            else paths.output_dir() / SECTION
        folder.mkdir(parents=True, exist_ok=True)
        target = _unique(folder / output_name(record))
        doc = render(record, self.shop(), link=link, logo=self.logo())
        try:
            doc.save(str(target))
        finally:
            doc.close()
        log.info("МЕРКУРИЙ: %s — %s", record.code, target.name)
        return VetDocResult(record=record, pdf=target, page=page, link=link)


def _unique(target: Path) -> Path:
    counter = 2
    stem = target.stem
    while target.exists():
        target = target.with_name(f"{stem} ({counter}){target.suffix}")
        counter += 1
    return target
