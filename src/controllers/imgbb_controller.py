"""IMGBB — pictures up to the owner's imgbb account, links and QR codes back.

Two jobs, both leaning on the same key the КРКОД РЕГ section already keeps in
Sozlamalar: drop a picture → its public DIRECT link (https://i.ibb.co/…);
drop a picture into the second field → the link is folded into a QR code.
"""

from __future__ import annotations

from src.common.logging import get_logger

log = get_logger(__name__)


class ImgbbController:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    def key(self) -> str:
        from src.services.imgbb import KEY_IMGBB

        if self._settings is None:
            return ""
        return str(self._settings.get(KEY_IMGBB, "") or "").strip()

    def upload(self, image: bytes, name: str = "") -> str:
        """The picture published on imgbb — its DIRECT link."""
        from src.services.imgbb import upload

        link = upload(image, self.key(), name=name)
        log.info("IMGBB: юкланди — %s", link)
        return link

    @staticmethod
    def qr(link: str) -> bytes:
        """The link as a QR code, PNG bytes."""
        from src.pdf.qrreg_renderer import make_qr

        return make_qr(link)
