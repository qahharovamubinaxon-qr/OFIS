"""МЕРКУРИЙ — ҳужжат расмларини ўқиш ва маълумотномани чиқариш.

Дўкон ҳайвонни оладиган ҳужжатлар турлича: етказиб берувчининг юк хати,
аввалги справка, эмлаш дафтарчаси, қабул қилиш акти. Уларга ягона схема йўқ —
шунинг учун ўқиш УНИВЕРСАЛ дагидек, **майдон номи сўров бўлиб** боради
(:meth:`OcrService.read_named`): нима сўралса, ўша қидирилади, топилмагани
бўш қолади ва операторнинг ўзи ёзади.

AI ҳеч қачон тўғридан-тўғри PDF га ўтмайди: ўқилган ҳар қиймат аввал шаклда
кўринади, оператор тасдиқлайди, кейин босилади.
"""

from __future__ import annotations

from pathlib import Path

from src.common.logging import get_logger
from src.domain.vetdoc import Shop, VetRecord
from src.ocr.service import OcrService
from src.services.vetdoc_service import VetDocResult, VetDocService

log = get_logger(__name__)

#: (ёзув майдони, AI дан сўраладиган ном). Номлар русча — ҳужжатлар русча.
ASK: tuple[tuple[str, str], ...] = (
    ("product", "Продукция (птица, КРС, МРС, собака, кошка)"),
    ("species", "Вид продукции"),
    ("title", "Наименование продукции"),
    ("volume", "Объём (количество голов)"),
    ("birth", "Дата рождения животного"),
    ("batch", "Номер производственной партии"),
    ("purpose", "Направление (цель перемещения)"),
    ("wellbeing", "Благополучие местности"),
    ("held_since", "Животные содержались"),
    ("origin_country", "Страна происхождения"),
    ("produced_by", "Кем выращены (хозяйство)"),
    ("origin_doc", "Документ о происхождении"),
    ("transport", "Тип транспорта"),
    ("sender_company", "Отправитель (название предприятия)"),
    ("receiver_company", "Получатель (название предприятия)"),
    ("buyer", "Покупатель (Ф.И.О.)"),
    ("vet_name", "Ф.И.О. ветеринарного врача"),
    ("incoming_doc", "Номер и дата входящего документа"),
    ("notes", "Особые отметки"),
)
#: Битта ҳайвон ҳақидаги сўровлар — рўйхатнинг биринчи қаторига тушади.
ASK_ANIMAL: tuple[tuple[str, str], ...] = (
    ("nickname", "Кличка животного"),
    ("sex", "Пол животного (самец/самка)"),
    ("breed", "Порода животного"),
    ("age", "Возраст животного"),
    ("mark", "Номер средства маркирования (чип, бирка)"),
    ("count", "Количество голов"),
)


class VetDocController:
    def __init__(self, ocr: OcrService, service: VetDocService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- дўкон
    def shop(self) -> Shop:
        return self._service.shop()

    def save_shop(self, shop: Shop) -> None:
        self._service.save_shop(shop)

    def logo(self) -> Path | None:
        return self._service.logo()

    def set_logo(self, source: Path) -> Path:
        return self._service.set_logo(source)

    # ------------------------------------------------------------ ўқиш
    @staticmethod
    def read_image(path: Path) -> bytes:
        """Файл байтлари — UI оқимида ўқилади, кейин ишчи оқимга берилади."""
        return Path(path).read_bytes()

    def read_documents(self, images: list[bytes]) -> dict[str, str]:
        """Расмлардан топилганлар: ``{майдон номи: қиймат}``.

        Ҳайвон ҳақидагилари ``animal.`` префикси билан қайтади — шакл уларни
        рўйхатнинг биринчи қаторига қўяди.
        """
        if not images:
            return {}
        pairs = list(ASK) + [(f"animal.{key}", label)
                             for key, label in ASK_ANIMAL]
        answer = self._ocr.read_named(images, [label for _, label in pairs])
        found = {field: str(answer.get(label, "") or "").strip()
                 for field, label in pairs}
        found = {k: v for k, v in found.items() if v}
        log.info("МЕРКУРИЙ: %d майдондан %d таси ўқилди", len(pairs), len(found))
        return found

    # ---------------------------------------------------------- чиқариш
    def publish(self, record: VetRecord,
                out_dir: Path | None = None) -> VetDocResult:
        return self._service.publish(record, out_dir)

    def link_for(self, record: VetRecord) -> str:
        return self._service.link_for(record)

    def records(self) -> list[VetRecord]:
        return self._service.records()

    def load(self, code: str) -> VetRecord | None:
        return self._service.load(code)

    def site_dir(self) -> Path:
        return self._service.rebuild_site()

    def export_site(self, target: Path) -> Path:
        return self._service.export_site(target)
