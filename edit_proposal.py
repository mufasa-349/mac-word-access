#!/usr/bin/env python3
"""
Proposal Template.docx üzerinde alan güncellemeleri (python-docx ile doğrudan .docx dosyası).

Önemli: Word bu dosyayı açıkken kayıt genelde başarısız olur veya dosya kilitlenir.
Scripti çalıştırmadan önce belgeyi Word'de kapatın; ardından Word'de yeniden açın.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from docx import Document


DEFAULT_DOC = Path(__file__).resolve().parent / "Proposal Template.docx"


def set_project_title(doc: Document, value: str) -> bool:
    """'Project Title:' içeren paragrafı bulur; yer tutucu noktaları value ile değiştirir."""
    needle = "project title"
    for para in doc.paragraphs:
        if needle not in para.text.lower():
            continue
        runs = para.runs
        if not runs:
            return False
        # İlk run'da etiket + yeni değer; diğer tüm run'ları temizle (şablonda bölünmüş … karakterleri için)
        runs[0].text = f"Project Title: {value}"
        for r in runs[1:]:
            r.text = ""
        return True
    return False


def save_with_retry(path: Path, doc: Document, retries: int = 5, delay: float = 0.4) -> None:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            doc.save(str(path))
            return
        except PermissionError as e:
            last = e
            time.sleep(delay)
    assert last is not None
    raise PermissionError(
        f"Kaydedilemedi (dosya kilitli olabilir): {path}\n"
        "Word'de bu dosyayı kapatıp tekrar deneyin."
    ) from last


def main() -> int:
    parser = argparse.ArgumentParser(description="Proposal şablonunda Project Title güncelle")
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=DEFAULT_DOC,
        help=f"DOCX yolu (varsayılan: {DEFAULT_DOC.name})",
    )
    parser.add_argument(
        "--title",
        "-t",
        default="DENEME123",
        help='Project Title değeri (varsayılan: "DENEME123")',
    )
    parser.add_argument(
        "--backup",
        "-b",
        action="store_true",
        help="Kayıttan önce .bak yedek oluştur",
    )
    args = parser.parse_args()
    path: Path = args.file.expanduser().resolve()

    if not path.is_file():
        print(f"Dosya bulunamadı: {path}", file=sys.stderr)
        return 1

    doc = Document(str(path))
    if not set_project_title(doc, args.title):
        print(
            "Uyarı: 'Project Title' metni hiçbir paragrafta bulunamadı; dosya değiştirilmedi.",
            file=sys.stderr,
        )
        return 2

    if args.backup:
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        print(f"Yedek: {bak}")

    save_with_retry(path, doc)
    print(f"Güncellendi: {path}")
    print(f"Project Title → {args.title!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
