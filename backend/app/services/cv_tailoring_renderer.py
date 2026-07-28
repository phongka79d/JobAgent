"""Deterministic fixed-shell LaTeX rendering for grounded tailored content."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import quote, urlsplit, urlunsplit

from app.schemas.contact import normalize_github_profile_url
from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredAttribute,
    TailoredCVContent,
    TailoredItem,
)

_FIXED_SHELL = r"""\documentclass[11pt]{article}
\usepackage{graphicx}
\setlength{\parindent}{0pt}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage[utf8]{inputenc}
\usepackage[T1,T5]{fontenc}
\usepackage[vietnamese,english]{babel}
\usepackage[left=1.06cm,top=1.2cm,right=1.06cm,bottom=1.0cm]{geometry}
\usepackage{titlesec}

\titleformat{\section}{\large\bfseries}{}{0em}{\MakeUppercase}[\titlerule]
\titlespacing*{\section}{0pt}{10pt}{5pt}

\begin{document}"""

_TEXT_ESCAPES = {
    "\\": r"\textbackslash{}",
    "#": r"\#",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_URL_ESCAPES = {
    "\\": r"\textbackslash{}",
    "#": r"\#",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
}
_SIMPLE_KINDS = frozenset({"summary", "interests", "references"})
_COMPACT_KINDS = frozenset({"skills", "languages"})
_ITEM_OPTIONS = "[noitemsep, topsep=2pt, partopsep=0pt, parsep=0pt]"
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def escape_latex_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("LaTeX text must be a string")
    return "".join(_TEXT_ESCAPES.get(char, char) for char in value)


def _escape_latex_url(value: str) -> str:
    return "".join(_URL_ESCAPES.get(char, char) for char in value)


def _safe_http_url(value: str) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2_000
        or any(ord(char) < 32 or char.isspace() for char in value)
        or any(char in value for char in "\\{}")
        or _BAD_PERCENT_RE.search(value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname or ""
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not host
        or not _HOST_RE.fullmatch(host)
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    netloc = host.casefold() + (f":{port}" if port is not None else "")
    path = quote(parsed.path, safe="/%:@-._~!$&'()*+,;=")
    query = quote(parsed.query, safe="=&?/:@-._~!$'()*+,;[%]")
    fragment = quote(parsed.fragment, safe="=&?/:@-._~!$'()*+,;[%]")
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, fragment))


def _github_link(value: str) -> str:
    canonical = normalize_github_profile_url(value)
    parsed = urlsplit(canonical)
    username = parsed.path.removeprefix("/")
    url = f"{parsed.scheme}://github.com/{username}"
    return (
        rf"\href{{{_escape_latex_url(url)}}}"
        rf"{{GitHub: {escape_latex_text(username)}}}"
    )


def _render_header(content: TailoredCVContent) -> list[str]:
    header = content.header
    contacts: list[str] = []
    if header.location is not None:
        contacts.append(escape_latex_text(header.location))
    if header.phone is not None:
        contacts.append(escape_latex_text(header.phone))
    if header.email is not None:
        contacts.append(escape_latex_text(header.email))
    if header.github_url is not None:
        contacts.append(_github_link(header.github_url))
    name = escape_latex_text(header.full_name)
    lines = [r"\begin{center}"]
    if contacts:
        lines.extend(
            [
                rf"    \textbf{{\Large {name}}} \\",
                r"    \vspace{2pt}",
                "    " + r" \textbullet \ ".join(contacts),
            ]
        )
    else:
        lines.append(rf"    \textbf{{\Large {name}}}")
    lines.append(r"\end{center}")
    return lines


def _nonempty(values: Iterable[SourceBoundText]) -> list[str]:
    return [escape_latex_text(value.text) for value in values if value.text]


def _render_bullets(values: list[SourceBoundText]) -> list[str]:
    bullets = _nonempty(values)
    if not bullets:
        return []
    return [
        rf"\begin{{itemize}}{_ITEM_OPTIONS}",
        *(rf"    \item {bullet}" for bullet in bullets),
        r"\end{itemize}",
    ]


def _render_attribute(name: str, values: list[str]) -> str | None:
    if not values:
        return None
    return rf"\textbf{{{escape_latex_text(name)}:}} " + ", ".join(values)


def _render_optional_metadata(item: TailoredItem) -> list[str]:
    subtitle = (
        escape_latex_text(item.subtitle.text)
        if item.subtitle is not None and item.subtitle.text
        else ""
    )
    location = (
        escape_latex_text(item.location.text)
        if item.location is not None and item.location.text
        else ""
    )
    lines: list[str] = []
    if subtitle and location:
        lines.append(f"{subtitle} \\hfill {location}")
    elif subtitle or location:
        lines.append(subtitle or location)
    if item.date_text is not None and item.date_text.text:
        lines.append(escape_latex_text(item.date_text.text))
    return lines


def _comparison_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _display_item_title(
    item: TailoredItem, section_heading: str
) -> SourceBoundText | None:
    title = item.title
    if title is None or _comparison_text(title.text) == _comparison_text(section_heading):
        return None
    return title


def _render_simple_item(item: TailoredItem, section_heading: str) -> list[str]:
    lines: list[str] = []
    title = _display_item_title(item, section_heading)
    if title is not None and title.text:
        lines.append(rf"\textbf{{{escape_latex_text(title.text)}}}")
    lines.extend(_render_optional_metadata(item))
    if item.body.text:
        lines.append(escape_latex_text(item.body.text))
    lines.extend(_render_bullets(item.bullets))
    for attribute in item.attributes:
        rendered = _render_attribute(attribute.name, _nonempty(attribute.values))
        if rendered is not None:
            lines.append(rendered)
    return lines


def _render_compact_item(item: TailoredItem, section_heading: str) -> list[str]:
    body = escape_latex_text(item.body.text) if item.body.text else ""
    lines: list[str] = []
    title = _display_item_title(item, section_heading)
    if title is not None and title.text:
        prefix = rf"\textbf{{{escape_latex_text(title.text)}:}}"
        lines.append(f"{prefix} {body}".rstrip())
    elif body:
        lines.append(body)
    lines.extend(_render_optional_metadata(item))
    for attribute in item.attributes:
        rendered = _render_attribute(attribute.name, _nonempty(attribute.values))
        if rendered is not None:
            lines.append(rendered)
    lines.extend(_render_bullets(item.bullets))
    return lines


def _first_link(
    attributes: list[TailoredAttribute], *, enabled: bool
) -> tuple[str | None, tuple[int, int] | None]:
    if not enabled:
        return None, None
    for attribute_index, attribute in enumerate(attributes):
        for value_index, value in enumerate(attribute.values):
            url = _safe_http_url(value.text)
            if url is not None:
                return url, (attribute_index, value_index)
    return None, None


def _render_generic_item(item: TailoredItem, section_heading: str) -> list[str]:
    has_date = item.date_text is not None and bool(item.date_text.text)
    link, consumed = _first_link(item.attributes, enabled=not has_date)
    left = ""
    title = _display_item_title(item, section_heading)
    if title is not None and title.text:
        left = rf"\textbf{{{escape_latex_text(title.text)}}}"
    right = ""
    if has_date and item.date_text is not None:
        right = escape_latex_text(item.date_text.text)
    elif link is not None:
        right = rf"\href{{{_escape_latex_url(link)}}}{{[Link]}}"
    lines: list[str] = []
    if left and right:
        lines.append(f"{left} \\hfill {right}")
    elif left or right:
        lines.append(left or right)
    subtitle = (
        escape_latex_text(item.subtitle.text)
        if item.subtitle is not None and item.subtitle.text
        else ""
    )
    location = (
        escape_latex_text(item.location.text)
        if item.location is not None and item.location.text
        else ""
    )
    if subtitle and location:
        lines.append(f"{subtitle} \\hfill {location}")
    elif subtitle or location:
        lines.append(subtitle or location)
    if item.body.text:
        lines.append(escape_latex_text(item.body.text))
    lines.extend(_render_bullets(item.bullets))
    for attribute_index, attribute in enumerate(item.attributes):
        values = [
            escape_latex_text(value.text)
            for value_index, value in enumerate(attribute.values)
            if value.text and consumed != (attribute_index, value_index)
        ]
        rendered = _render_attribute(attribute.name, values)
        if rendered is not None:
            lines.append(rendered)
    return lines


def render_latex_cv(content: TailoredCVContent) -> str:
    if not isinstance(content, TailoredCVContent):
        raise TypeError("content must be TailoredCVContent")
    lines = [_FIXED_SHELL, "", *_render_header(content)]
    for section in content.sections:
        lines.extend(["", rf"\section{{{escape_latex_text(section.heading)}}}"])
        item_blocks: list[list[str]] = []
        for item in section.items:
            if section.kind in _SIMPLE_KINDS:
                block = _render_simple_item(item, section.heading)
            elif section.kind in _COMPACT_KINDS:
                block = _render_compact_item(item, section.heading)
            else:
                block = _render_generic_item(item, section.heading)
            if block:
                item_blocks.append(block)
        for index, block in enumerate(item_blocks):
            if index:
                lines.extend(["", r"\vspace{5pt}", ""])
            lines.extend(block)
    lines.extend(["", r"\end{document}"])
    return "\n".join(lines) + "\n"


__all__ = ["escape_latex_text", "render_latex_cv"]
