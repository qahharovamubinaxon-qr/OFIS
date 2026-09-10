"""Terminaldan sinash uchun:
    python -m photo_tools.cli person foto.jpg --size 35x45 --bg white --out rasm
    python -m photo_tools.cli doc old.jpg orqa.jpg --preset id_card --color color --out patent
    python -m photo_tools.cli doc pasport.jpg --preset passport_spread --out pasport
    python -m photo_tools.cli models     # GFPGAN og'irligini yuklab olish
"""
import argparse
import sys

from . import (BACKGROUNDS, COLOR_MODES, DOC_PRESETS, PHOTO_SIZES, ensure_models,
               layout_a4, make_person_photo, models_status, save_sheet_pdf, scan_document)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="photo_tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("person")
    p.add_argument("src")
    p.add_argument("--size", default="35x45", choices=PHOTO_SIZES)
    p.add_argument("--bg", default="white", choices=BACKGROUNDS)
    p.add_argument("--no-face", action="store_true", help="GFPGAN ishlatilmasin")
    p.add_argument("--weight", type=float, default=0.5)
    p.add_argument("--no-cut", action="store_true", help="burchak kesimi bo'lmasin")
    p.add_argument("--out", default="rasm")

    d = sub.add_parser("doc")
    d.add_argument("src", nargs="+")
    d.add_argument("--preset", default="auto", choices=DOC_PRESETS)
    d.add_argument("--color", default="color", choices=COLOR_MODES)
    d.add_argument("--out", default="hujjat")

    sub.add_parser("models")
    a = ap.parse_args(argv)

    if a.cmd == "models":
        print(ensure_models(lambda f: print(f"\r{f*100:5.1f}%", end="")))
        return
    if a.cmd == "person":
        r = make_person_photo(a.src, a.size, a.bg, not a.no_face, a.weight,
                              corner_cut=not a.no_cut, progress=print)
        r.photo.save(f"{a.out}.png", dpi=(600, 600))
        if r.sheet is not None:
            save_sheet_pdf(r.sheet_pdf_items, f"{a.out}_6ta.pdf")
        print("yuz topildi:", r.face_found, "| yuz tiklandi:", r.face_enhanced)
        return
    pages = []
    for i, f in enumerate(a.src):
        pages += scan_document(f, a.preset, a.color, label=["old", "orqa"][i] if i < 2 else "", progress=print)
    layout_a4(pages, f"{a.out}.pdf", preview_png=f"{a.out}_preview.png")
    print("tayyor:", f"{a.out}.pdf")


if __name__ == "__main__":
    sys.exit(main())
