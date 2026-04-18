"""
draft_proposal.tex içinden kapak ve bölüm metinlerini çıkarır; basit LaTeX → düz metin dönüşümü.
Tam TeX ayrıştırıcı değildir; bu repodaki proposal taslağına uygundur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ContentLine:
    """Tek Word paragrafı veya madde satırı."""

    kind: str  # "normal" | "list" | "subheading"
    text: str


SECTION_ORDER = [
    "ABSTRACT",
    "INTRODUCTION",
    "PROPOSED SOLUTION AND METHODS",
    "RISK MANAGEMENT",
    "PROJECT SCHEDULE",
    "ETHICAL ISSUES",
    "REFERENCES",
]


def _strip_comments(tex: str) -> str:
    out: list[str] = []
    for line in tex.splitlines():
        if "%" in line:
            # basit: satır içi yorum (URL içindeki % için istisna yok — bu taslakta sorun yok)
            idx = line.find("%")
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _extract_begin_document(tex: str) -> str:
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", tex, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("\\begin{document} ... \\end{document} bulunamadı.")
    return m.group(1)


def _extract_first_center_block(body: str) -> str:
    m = re.search(r"\\begin\{center\}(.*?)\\end\{center\}", body, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("Kapak için \\begin{center} ... \\end{center} bulunamadı.")
    return m.group(1)


def _latex_cmd_arg(s: str, cmd: str) -> str | None:
    m = re.search(rf"\\{re.escape(cmd)}\s*\{{([^}}]*)\}}", s)
    return m.group(1) if m else None


def _strip_brace_commands(s: str) -> str:
    r"""{\Large\bfseries X} gibi yapılarda iç metni almaya çalışır."""
    s = re.sub(r"\\textbf\{{([^}}]*)\}}", r"\1", s)
    s = re.sub(r"\\textit\{{([^}}]*)\}}", r"\1", s)
    s = re.sub(r"\\texttt\{{([^}}]*)\}}", r"\1", s)
    s = re.sub(r"\\emph\{{([^}}]*)\}}", r"\1", s)
    s = re.sub(r"\\LARGE\b", "", s)
    s = re.sub(r"\\Large\b", "", s)
    s = re.sub(r"\\large\b", "", s)
    s = re.sub(r"\\normalsize\b", "", s)
    s = re.sub(r"\\bfseries\b", "", s)
    s = re.sub(r"\\centering\b", "", s)
    s = re.sub(r"\\small\b", "", s)
    # kalan {...} tek katman
    s = re.sub(r"\{{([^}}]+)\}}", r"\1", s)
    return s


def parse_cover(tex_path: Path) -> dict[str, str]:
    tex = _strip_comments(tex_path.read_text(encoding="utf-8"))
    body = _extract_begin_document(tex)
    center = _extract_first_center_block(body)

    def one(pattern: str, *, ignorecase: bool = False) -> str:
        flags = re.DOTALL | (re.IGNORECASE if ignorecase else 0)
        m = re.search(pattern, center, flags=flags)
        if not m:
            return ""
        s = m.group(1).strip()
        s = s.replace(r"\#", "#")
        s = re.sub(r"\\\[.*?]", "", s)
        s = _strip_brace_commands(s)
        return s.strip()

    # \large ile \LARGE karışmasın diye büyük/küçük harf duyarlı
    course = one(r"\{\s*\\LARGE\s*\\bfseries\s+([^}]+)\}")
    proposal_line = one(r"\{\s*\\large\s*\\bfseries\s+([^}]+)\}")
    title = one(
        r"\\bfseries\s+Project Title.*?\n\s*"
        r"\{\s*\\normalsize\s+([^}]+)\}"
    )
    members = one(
        r"\\bfseries\s+Group Members.*?\n\s*"
        r"\{\s*\\normalsize\s+([^}]+)\}"
    )
    supervisors = one(
        r"\\bfseries\s+Supervisor(?:\(s\))?.*?\n\s*"
        r"\{\s*\\normalsize\s+([^}]+)\}"
    )
    date_line = one(
        r"\\bfseries\s+Date.*?\n\s*"
        r"\{\s*\\normalsize\s+([^}]+)\}"
    )

    return {
        "course_line": course or "ENS 491 – Graduation Project (Design)",
        "proposal_line": proposal_line or "Proposal",
        "project_title": title,
        "group_members": members,
        "supervisors": supervisors,
        "date": date_line,
    }


def _clean_inline_latex(s: str) -> str:
    s = _strip_comments(s)
    s = s.replace("``", '"').replace("''", '"')
    s = s.replace("---", "—").replace("--", "–")
    s = re.sub(r"\\,'", ",", s)
    s = re.sub(r"\\cite\{([^}]+)\}", r"[\1]", s)
    s = re.sub(r"\\textbf\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\textit\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\texttt\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\emph\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\label\{[^}]+\}", "", s)
    s = re.sub(r"\\ref\{[^}]+\}", "[ref]", s)
    # basit inline math: bırak veya sadeleştir
    s = re.sub(r"\$([^$]+)\$", r"\1", s)
    s = re.sub(r"\\_", "_", s)
    s = re.sub(r"\\&", "&", s)
    s = re.sub(r"\\%", "%", s)
    s = re.sub(r"\\#", "#", s)
    # "et al.\ word" → "et al. word"
    s = re.sub(r"\.\\\s+", ". ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _replace_figure_blocks(s: str, base_dir: Path) -> str:
    """figure ortamını [Şekil: path — caption] ile değiştirir."""

    def repl(m: re.Match[str]) -> str:
        block = m.group(0)
        inc = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", block)
        cap = re.search(r"\\caption\{([^}]*)\}", block, re.DOTALL)
        path_s = inc.group(1) if inc else "?"
        cap_s = _clean_inline_latex(cap.group(1)) if cap else ""
        full = (base_dir / path_s).resolve()
        note = f"[Şekil: {path_s}"
        if full.is_file():
            note += " — dosya mevcut]"
        else:
            note += " — dosya bulunamadı]"
        if cap_s:
            note += f" {cap_s}"
        return "\n\n" + note + "\n\n"

    return re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", repl, s, flags=re.DOTALL | re.IGNORECASE)


def _skip_brace_group(s: str, i: int) -> int:
    """s[i] == '{' ise eşleşen '}' sonrası indeks."""
    if i >= len(s) or s[i] != "{":
        return i
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(s)


def _tabular_rows_to_text(body: str) -> str:
    """tabular iç gövdesini (satırlar) düz metne çevirir."""
    rows: list[str] = []
    for raw_line in body.split("\\\\"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("\\hline") or line.startswith("\\toprule") or line.startswith("\\midrule"):
            continue
        if line.startswith("\\bottomrule"):
            continue
        if "&" not in line:
            continue
        cells = [_clean_inline_latex(c.strip()) for c in line.split("&")]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _replace_standalone_tabular(s: str) -> str:
    """\\begin{center} içi dahil her yerdeki tabular ortamını metne çevirir."""

    token = r"\begin{tabular}"
    out: list[str] = []
    pos = 0
    while True:
        idx = s.find(token, pos)
        if idx < 0:
            out.append(s[pos:])
            break
        out.append(s[pos:idx])
        j = idx + len(token)
        if j < len(s) and s[j] == "[":
            k = s.find("]", j)
            if k >= 0:
                j = k + 1
        j = _skip_brace_group(s, j)
        end = s.find(r"\end{tabular}", j)
        if end < 0:
            out.append(s[idx:])
            break
        inner = s[j:end]
        txt = _tabular_rows_to_text(inner)
        out.append("\n\n[Tablo]\n" + txt + "\n\n")
        pos = end + len(r"\end{tabular}")
    return "".join(out)


def _replace_table_blocks(s: str) -> str:
    """table içindeki tabular satırlarını metin satırlarına çevirir (basit)."""

    def table_to_text(tab: str) -> str:
        rows: list[str] = []
        for line in tab.splitlines():
            line = line.strip()
            if not line or line.startswith("\\"):
                if "&" not in line:
                    continue
            if "&" in line and "\\\\" in line:
                cells = [c.strip() for c in line.split("&")]
                if cells and cells[0].startswith("\\"):
                    continue
                cells = [_clean_inline_latex(c) for c in cells if c and not c.startswith("\\")]
                if cells:
                    rows.append(" | ".join(cells))
        return "\n".join(rows)

    def repl(m: re.Match[str]) -> str:
        inner = m.group(0)
        tab = re.search(r"\\begin\{tabular\}.*?\\end\{tabular\}", inner, re.DOTALL)
        cap = re.search(r"\\caption\{([^}]*)\}", inner, re.DOTALL)
        body = table_to_text(tab.group(0)) if tab else ""
        cap_s = _clean_inline_latex(cap.group(1)) if cap else ""
        out = ""
        if cap_s:
            out += f"[Tablo: {cap_s}]\n"
        if body:
            out += body
        return "\n\n" + out + "\n\n"

    return re.sub(r"\\begin\{table\}.*?\\end\{table\}", repl, s, flags=re.DOTALL | re.IGNORECASE)


def _emit_plain_paragraphs(fragment: str, out: list[ContentLine]) -> None:
    fragment = fragment.strip()
    if not fragment:
        return
    # Aynı alt bölümde \textbf{...} ile başlayan satırları ayrı paragraflara böl
    fragment = re.sub(r"\n(?=\s*\\textbf\{)", "\n\n", fragment)
    for para in re.split(r"\n\s*\n+", fragment):
        para = _clean_inline_latex(para)
        if para:
            out.append(ContentLine("normal", para))


def _parse_list_inner(inner: str, env: str) -> list[ContentLine]:
    out: list[ContentLine] = []
    parts = re.split(r"\\item\s+", inner)
    for piece in parts:
        if not piece.strip():
            continue
        # iç içe ortam varsa kabaca kes
        if "\\begin{" in piece:
            nested = re.split(r"\\begin\{", piece, maxsplit=1)[0]
            piece = nested
        piece = piece.split(rf"\end{{{env}}}")[0]
        cle = _clean_inline_latex(piece.strip())
        if cle:
            out.append(ContentLine("list", cle))
    return out


def _walk_latex_body(chunk: str) -> list[ContentLine]:
    """subsection ve itemize/enumerate ile düz paragrafları sırayla üretir."""

    lines_out: list[ContentLine] = []
    pos = 0
    chunk = chunk.strip()
    while pos < len(chunk):
        m_sub = re.search(r"\\subsection\*?\{([^}]+)\}", chunk[pos:])
        m_list = re.search(
            r"\\begin\{(itemize|enumerate)\}(?:\[[^\]]*\])?",
            chunk[pos:],
            re.IGNORECASE,
        )
        candidates: list[tuple[int, str, re.Match[str]]] = []
        if m_sub:
            candidates.append((m_sub.start() + pos, "sub", m_sub))
        if m_list:
            candidates.append((m_list.start() + pos, "list", m_list))
        if not candidates:
            _emit_plain_paragraphs(chunk[pos:], lines_out)
            break
        first_abs, kind, m = min(candidates, key=lambda x: x[0])
        if first_abs > pos:
            _emit_plain_paragraphs(chunk[pos:first_abs], lines_out)
        if kind == "sub":
            title = _clean_inline_latex(m.group(1).strip())
            lines_out.append(ContentLine("subheading", title))
            # m, chunk[pos:] üzerinde; m.end() göreli — first_abs + m.end() çift sayım yapar
            pos = pos + m.end()
            continue
        env = m.group(1).lower()
        block_m = re.search(
            rf"\\begin\{{{re.escape(env)}\}}(?:\[[^\]]*\])?(.*?)\\end\{{{re.escape(env)}\}}",
            chunk[first_abs:],
            re.DOTALL | re.IGNORECASE,
        )
        if not block_m:
            pos = first_abs + 10
            continue
        inner = block_m.group(1)
        lines_out.extend(_parse_list_inner(inner, env))
        pos = first_abs + block_m.end()

    return lines_out


def extract_section_raw(body: str, name: str, next_name: str | None) -> str:
    esc = re.escape(name)
    start_m = re.search(rf"\\section\*?\{{{esc}\}}", body, re.IGNORECASE)
    if not start_m:
        raise ValueError(f"Bölüm bulunamadı: {name}")
    start = start_m.end()
    if next_name:
        end_m = re.search(rf"\\section\*?\{{{re.escape(next_name)}\}}", body[start:], re.IGNORECASE)
        if not end_m:
            raise ValueError(f"Sonraki bölüm bulunamadı: {next_name}")
        return body[start : start + end_m.start()]
    return body[start:]


def tex_section_to_content_lines(raw: str, base_dir: Path, *, is_references: bool = False) -> list[ContentLine]:
    raw = _replace_figure_blocks(raw, base_dir)
    raw = _replace_table_blocks(raw)
    raw = _replace_standalone_tabular(raw)
    if is_references:
        raw = re.sub(r"\\bibliographystyle\{[^}]+\}\s*", "", raw)
        raw = re.sub(
            r"\\bibliography\{[^}]+\}\s*",
            (
                "\n\n[Kaynaklar: LaTeX'te bibliography ile üretilen tam liste buraya eklenebilir. "
                "Şimdilik metin içindeki cite anahtarları köşeli parantezde görünür.]\n\n"
            ),
            raw,
        )
    return _walk_latex_body(raw)


def parse_proposal_tex(tex_path: Path) -> tuple[dict[str, str], dict[str, list[ContentLine]]]:
    tex = _strip_comments(tex_path.read_text(encoding="utf-8"))
    body = _extract_begin_document(tex)
    cover = parse_cover(tex_path)

    sections: dict[str, list[ContentLine]] = {}
    for i, name in enumerate(SECTION_ORDER):
        nxt = SECTION_ORDER[i + 1] if i + 1 < len(SECTION_ORDER) else None
        raw = extract_section_raw(body, name, nxt)
        sections[name] = tex_section_to_content_lines(
            raw, tex_path.parent, is_references=(name == "REFERENCES")
        )

    return cover, sections


def content_lines_to_debug(lines: Iterable[ContentLine]) -> str:
    return "\n".join(f"{x.kind}: {x.text[:120]}..." if len(x.text) > 120 else f"{x.kind}: {x.text}" for x in lines)
