"""Fixed-shell, escaping, dynamic-section, and generic-link rendering."""

from __future__ import annotations

import pytest
from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredAttribute,
    TailoredCVContent,
    TailoredHeaderSnapshot,
    TailoredItem,
    TailoredSection,
)
from app.services.cv_tailoring_renderer import escape_latex_text, render_latex_cv


def _text(value: str) -> SourceBoundText:
    return SourceBoundText(
        text=value,
        source_fact_ids=["sf_synthetic"] if value else [],
    )


def _item(
    item_id: str,
    body: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    date_text: str | None = None,
    location: str | None = None,
    bullets: list[str] | None = None,
    attributes: list[tuple[str, list[str]]] | None = None,
) -> TailoredItem:
    return TailoredItem(
        id=item_id,
        source_entry_id=item_id,
        title=_text(title) if title is not None else None,
        subtitle=_text(subtitle) if subtitle is not None else None,
        date_text=_text(date_text) if date_text is not None else None,
        location=_text(location) if location is not None else None,
        body=_text(body),
        bullets=[_text(value) for value in bullets or []],
        attributes=[
            TailoredAttribute(name=name, values=[_text(value) for value in values])
            for name, values in attributes or []
        ],
    )


def _content(
    *,
    location: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    github_url: str | None = None,
    sections: list[TailoredSection] | None = None,
) -> TailoredCVContent:
    return TailoredCVContent(
        header=TailoredHeaderSnapshot(
            full_name="Nguyễn An",
            location=location,
            phone=phone,
            email=email,
            github_url=github_url,
        ),
        sections=sections
        or [
            TailoredSection(
                id="summary",
                ordinal=0,
                heading="Tóm tắt",
                kind="summary",
                items=[_item("summary-1", "Thiết kế dịch vụ công cộng.")],
            )
        ],
    )


@pytest.mark.parametrize(
    ("value", "escaped"),
    [
        ("#", r"\#"),
        ("$", r"\$"),
        ("%", r"\%"),
        ("&", r"\&"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
        ("\\", r"\textbackslash{}"),
    ],
)
def test_escape_latex_text(value: str, escaped: str) -> None:
    assert escape_latex_text(value) == escaped


def test_minimal_bilingual_render_is_byte_for_byte_stable() -> None:
    expected = r"""\documentclass[11pt]{article}
\usepackage{graphicx}
\setlength{\parindent}{0pt}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage[utf8]{inputenc}
\usepackage[T5,T1]{fontenc}
\usepackage[vietnamese,english]{babel}
\usepackage[left=1.06cm,top=1.2cm,right=1.06cm,bottom=1.0cm]{geometry}
\usepackage{titlesec}

\titleformat{\section}{\large\bfseries\uppercase}{}{0em}{}[\titlerule]
\titlespacing*{\section}{0pt}{10pt}{5pt}

\begin{document}

\begin{center}
    \textbf{\Large Nguyễn An} \\
    \vspace{2pt}
    Đà Nẵng
\end{center}

\section{Tóm tắt}
Thiết kế dịch vụ công cộng.

\end{document}
"""
    assert render_latex_cv(_content(location="Đà Nẵng")) == expected


@pytest.mark.parametrize(
    ("location", "phone", "email", "github", "expected"),
    [
        (None, None, None, None, None),
        ("Hà Nội", None, None, None, "Hà Nội"),
        (None, "+84900000000", None, None, "+84900000000"),
        (None, None, "person@example.test", None, "person@example.test"),
        (None, None, None, "https://github.com/example-user", "GitHub: example-user"),
    ],
)
def test_optional_contacts_have_no_blank_separators(
    location: str | None,
    phone: str | None,
    email: str | None,
    github: str | None,
    expected: str | None,
) -> None:
    rendered = render_latex_cv(
        _content(
            location=location,
            phone=phone,
            email=email,
            github_url=github,
        )
    )
    header = rendered.split("\\end{center}", 1)[0]
    if expected is None:
        assert "\\textbullet" not in header
        assert "\\vspace{2pt}" not in header
    else:
        assert expected in header
        assert "\\textbullet" not in header


@pytest.mark.parametrize(
    ("has_location", "has_phone", "has_email", "has_github"),
    [
        (location, phone, email, github)
        for location in (False, True)
        for phone in (False, True)
        for email in (False, True)
        for github in (False, True)
    ],
)
def test_every_optional_contact_combination_has_exact_separator_count(
    has_location: bool,
    has_phone: bool,
    has_email: bool,
    has_github: bool,
) -> None:
    rendered = render_latex_cv(
        _content(
            location="Hà Nội" if has_location else None,
            phone="+84900000000" if has_phone else None,
            email="person@example.test" if has_email else None,
            github_url=(
                "https://github.com/example-user" if has_github else None
            ),
        )
    )
    header = rendered.split("\\end{center}", 1)[0]
    count = sum((has_location, has_phone, has_email, has_github))
    assert header.count("\\textbullet") == max(count - 1, 0)


def test_dynamic_generic_sections_links_bullets_and_attributes() -> None:
    sections = [
        TailoredSection(
            id="experience",
            ordinal=0,
            heading="Experience",
            kind="experience",
            items=[
                _item(
                    "experience-1",
                    "Coordinated public planning.",
                    title="Planning Specialist",
                    subtitle="Synthetic Civic Lab",
                    date_text="2023–2026",
                    location="Huế",
                    bullets=["Reduced review time by 20%."],
                    attributes=[("tools", ["Python", "SQL"])],
                )
            ],
        ),
        TailoredSection(
            id="awards",
            ordinal=1,
            heading="Awards",
            kind="awards",
            items=[_item("award-1", "Synthetic community award")],
        ),
        TailoredSection(
            id="other",
            ordinal=2,
            heading="Community Practice",
            kind="other",
            items=[
                _item(
                    "other-1",
                    "Mentored learners.",
                    title="Volunteer Mentor",
                    attributes=[
                        ("reference", ["https://example.test/work", "Public archive"])
                    ],
                )
            ],
        ),
    ]
    rendered = render_latex_cv(
        _content(
            phone="+84900000000",
            email="person@example.test",
            github_url="https://github.com/example-user",
            sections=sections,
        )
    )
    assert rendered.index("\\section{Experience}") < rendered.index(
        "\\section{Awards}"
    ) < rendered.index("\\section{Community Practice}")
    assert "2023–2026" in rendered
    assert "Reduced review time by 20\\%." in rendered
    assert "\\textbf{tools:} Python, SQL" in rendered
    assert r"\href{https://example.test/work}{[Link]}" in rendered
    assert "\\textbf{reference:} Public archive" in rendered
    assert rendered.count("\\textbullet") == 2


def test_simple_and_compact_layouts_do_not_drop_optional_source_fields() -> None:
    sections = [
        TailoredSection(
            id="summary",
            ordinal=0,
            heading="Summary",
            kind="summary",
            items=[
                _item(
                    "summary-1",
                    "Summary body",
                    title="Summary title",
                    subtitle="Summary subtitle",
                    date_text="Summary date",
                    location="Summary location",
                )
            ],
        ),
        TailoredSection(
            id="skills",
            ordinal=1,
            heading="Capabilities",
            kind="skills",
            items=[
                _item(
                    "skills-1",
                    "Capability body",
                    title="Capability label",
                    subtitle="Capability subtitle",
                    date_text="Capability date",
                    location="Capability location",
                )
            ],
        ),
    ]
    rendered = render_latex_cv(_content(sections=sections))
    for expected in (
        "Summary subtitle",
        "Summary date",
        "Summary location",
        "Capability subtitle",
        "Capability date",
        "Capability location",
    ):
        assert expected in rendered


def test_user_controlled_commands_are_only_escaped_text() -> None:
    attack = r"\input{secret} \write18{boom} % \end{document}"
    section = TailoredSection(
        id="other",
        ordinal=0,
        heading=attack,
        kind="other",
        items=[_item("attack-1", attack, attributes=[("url", [attack])])],
    )
    rendered = render_latex_cv(_content(sections=[section]))
    assert rendered.count(r"\end{document}") == 1
    assert r"\input{secret}" not in rendered
    assert r"\write18{boom}" not in rendered
    assert r"\textbackslash{}input\{secret\}" in rendered
    assert r"\includegraphics" not in rendered
    assert "\\href{" not in rendered
