"""
LaTeX kaynak listesi: .bbl (tercih) veya .bib dosyasından düz metin satırları üretir.
"""

from __future__ import annotations

import re
from pathlib import Path


def extract_bibliography_stem(tex_path: Path) -> str | None:
    text = tex_path.read_text(encoding="utf-8")
    m = re.search(r"\\bibliography\{([^}]+)\}", text)
    if not m:
        return None
    return m.group(1).split(",")[0].strip()


def _clean_bbl_chunk(s: str) -> str:
    s = re.sub(r"\\newblock\s*", " ", s)
    s = re.sub(r"\\emph\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\textit\{([^}]*)\}", r"\1", s)
    s = re.sub(r"``|''", '"', s)
    s = re.sub(r"\\&", "&", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def lines_from_bbl(bbl_path: Path) -> list[str]:
    """BibTeX/LaTeX'in ürettiği .bbl içinden \\bibitem bloklarını çıkarır."""
    raw = bbl_path.read_text(encoding="utf-8", errors="replace")
    # \begin{thebibliography} ... içi
    m = re.search(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
        raw,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        body = m.group(0)
    else:
        body = raw
    items = re.split(r"\\bibitem(?:\[[^\]]*\])?\{[^}]*\}", body)
    out: list[str] = []
    for chunk in items:
        chunk = _clean_bbl_chunk(chunk)
        if len(chunk) > 10:
            out.append(chunk)
    return out


def _decode_bibtex_text(s: str) -> str:
    """Yazar/başlıkta kalan basit LaTeX kaçışlarını Unicode'a çevirir."""
    rep = [
        (r"\{\\'a\}", "á"),
        (r"\{\\'e\}", "é"),
        (r"\{\\'i\}", "í"),
        (r"\{\\'o\}", "ó"),
        (r"\{\\'u\}", "ú"),
        (r"\{\\~a\}", "ã"),
        (r"\{\\~n\}", "ñ"),
        (r"\{\\~o\}", "õ"),
        (r"\{\\c\{c\}\}", "ç"),
        (r"\{\\u\{g\}\}", "ğ"),
        (r"\{\\i\}", "ı"),
        (r"\{\\'I\}", "İ"),
        (r"\{\\ss\}", "ß"),
        (r"--", "–"),
    ]
    for pat, ch in rep:
        s = re.sub(pat, ch, s, flags=re.IGNORECASE)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def lines_from_bib(bib_path: Path) -> list[str]:
    """references.bib için basit IEEE-benzeri tek satırlık maddeler."""
    try:
        import bibtexparser
    except ImportError as e:
        raise ImportError(
            "references.bib kullanmak için: pip install bibtexparser"
        ) from e

    with open(bib_path, encoding="utf-8") as f:
        db = bibtexparser.load(f)

    lines: list[str] = []
    for i, e in enumerate(db.entries, start=1):
        authors = e.get("author", "Unknown")
        authors = authors.replace("\n", " ").replace(" and ", ", ")
        authors = _decode_bibtex_text(authors)
        title = _decode_bibtex_text(e.get("title", ""))
        year = e.get("year", "")
        journal = e.get("journal") or e.get("booktitle") or ""
        journal = _decode_bibtex_text(journal) if journal else ""
        volume = e.get("volume", "")
        pages = e.get("pages", "")
        if pages:
            pages = pages.replace("--", "–")
        doi = (e.get("doi") or "").strip()

        parts = [f'[{i}] {authors}, "{title},"']
        if journal:
            parts.append(f" {journal}")
        if volume:
            parts.append(f", vol. {volume}")
        if pages:
            parts.append(f", pp. {pages}")
        if year:
            parts.append(f", {year}")
        if doi:
            parts.append(f", doi: {doi}")
        parts.append(".")
        line = "".join(parts)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def resolve_reference_lines(
    tex_path: Path,
    *,
    bbl_path: Path | None = None,
    bib_path: Path | None = None,
) -> list[str] | None:
    """
    Öncelik: --references-bbl → --references-bib → tex yanında references.bib.
    Hiçbiri yoksa None (LaTeX metnindeki yer tutucu kullanılır).
    """
    base = tex_path.parent
    if bbl_path and bbl_path.is_file():
        return lines_from_bbl(bbl_path.resolve())
    if bib_path and bib_path.is_file():
        return lines_from_bib(bib_path.resolve())
    stem = extract_bibliography_stem(tex_path)
    if stem:
        guess = base / f"{stem}.bib"
        if guess.is_file():
            return lines_from_bib(guess)
    return None
