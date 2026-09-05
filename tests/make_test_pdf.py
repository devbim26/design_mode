# -*- coding: utf-8 -*-
"""Генератор тестового PDF: 4 страницы с цветными блоками + оглавление.

Запуск: venv\\Scripts\\python.exe tests\\make_test_pdf.py [путь.pdf]
Без аргумента пишет tests/test-doc.pdf.
"""
import sys
from pathlib import Path


def build(path: str) -> None:
    out = Path(path)
    pages = [
        ("0.93 0.95 1", "Page 1 - cover"),
        ("0.90 0.98 0.90", "Page 2 - drawings"),
        ("0.99 0.94 0.87", "Page 3 - tables"),
        ("0.95 0.92 0.99", "Page 4 - notes"),
    ]
    # на каждой странице — сетка цветных прямоугольников (для проверки кропа)
    objs = {}  # num -> bytes

    objs[1] = b"<< /Type /Catalog /Pages 2 0 R /Outlines 100 0 R >>"
    kids = " ".join(f"{20 + i * 2} 0 R" for i in range(len(pages)))
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    objs[11] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    def content(i: int, color: str, label: str) -> bytes:
        rects = []
        for r in range(4):
            for c in range(3):
                x, y = 60 + c * 165, 120 + r * 150
                if (r + c) % 2 == 0:
                    rects.append(f"q 0.20 0.55 0.85 rg {x} {y} 150 130 re f Q")
                else:
                    rects.append(f"q 0.95 0.45 0.25 rg {x} {y} 150 130 re f Q")
        body = (
            f"q {color} rg 40 40 515 762 re f Q "
            + " ".join(rects)
            + f" BT /F1 24 Tf 0 0 0 rg 60 780 Td ({label}) Tj ET"
        )
        return body.encode()

    for i, (color, label) in enumerate(pages):
        pnum, cnum = 20 + i * 2, 21 + i * 2
        objs[pnum] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 11 0 R >> >> /Contents {cnum} 0 R >>"
        ).encode()
        c = content(i, color, label)
        objs[cnum] = b"<< /Length " + str(len(c)).encode() + b" >>\nstream\n" + c + b"\nendstream"

    # оглавление: Раздел A (стр.1) -> Подраздел (стр.2); Раздел B (стр.3)
    objs[100] = b"<< /Type /Outlines /First 101 0 R /Last 103 0 R /Count 3 >>"
    objs[101] = b"<< /Title (Section A) /Parent 100 0 R /Next 103 0 R /First 102 0 R /Last 102 0 R /Count 1 /Dest [20 0 R /XYZ 0 842 null] >>"
    objs[102] = b"<< /Title (Subsection A.1) /Parent 101 0 R /Dest [22 0 R /XYZ 0 842 null] >>"
    objs[103] = b"<< /Title (Section B) /Parent 100 0 R /Prev 101 0 R /Dest [24 0 R /XYZ 0 842 null] >>"

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(buf)
        buf += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
    xref_pos = len(buf)
    max_obj = max(objs)
    buf += f"xref\n0 {max_obj + 1}\n".encode()
    buf += b"0000000000 65535 f \n"
    for num in range(1, max_obj + 1):
        if num in offsets:
            buf += f"{offsets[num]:010d} 00000 n \n".encode()
        else:
            buf += b"0000000000 65535 f \n"
    buf += f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    out.write_bytes(bytes(buf))
    print("OK:", out, len(buf), "bytes,", len(pages), "pages")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "test-doc.pdf"))
