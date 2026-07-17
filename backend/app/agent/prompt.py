"""Conversation-first system prompt (Plan 3 §7.5 / Master §12.5).

The Agent answers greetings, casual conversation, and general knowledge
directly through the LLM. Tool use is limited to names injected from the
Agent registry for the current process — production Phase 2 injects none.
"""

from __future__ import annotations

from collections.abc import Sequence

# Domain tool names that must never appear when the registry is empty.
PRODUCTION_DOMAIN_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    }
)


def build_system_prompt(
    registered_tools: Sequence[str] | None = None,
) -> str:
    """Build the conversation-first system prompt for the decision node.

    Parameters
    ----------
    registered_tools:
        Tool names currently injected into the graph registry for this run.
        Empty or ``None`` means no tools are available: the prompt forbids
        inventing or calling tools and does not list domain capabilities.

    The prompt always:
    - permits greetings, general knowledge, and job-related conversation;
    - limits tool use to the injected names only;
    - forbids claiming success after a failed tool result (``ok=false``).
    """
    names = _normalize_tool_names(registered_tools)

    sections: list[str] = [
        "You are JobAgent, a helpful local career and conversation assistant.",
        "",
        "Conversation policy:",
        "- Answer greetings, casual conversation, and general knowledge "
        "questions naturally and directly through conversation.",
        "- A user message does not need to be related to jobs.",
        "- Keep the response language aligned with the user's language when "
        "practical.",
        "- Answer directly without tools when no registered JobAgent "
        "capability is required.",
        "",
        "Tool policy:",
        "- Call tools only when a registered JobAgent capability is needed "
        "(for example CVs, Candidate Profile, job preferences, job "
        "descriptions, saved jobs, matching, or skill gaps) and that "
        "capability is listed below.",
        "- Do not invent or expose general-purpose tools for unrelated "
        "requests.",
        "- Do not invent tool names that are not listed as registered.",
        "- When a tool returns a failed result (ok=false, a non-null error "
        "code, or an explicit failure summary), never claim that the action "
        "succeeded. Explain the failure truthfully using the tool summary.",
        "",
    ]

    if not names:
        sections.extend(
            [
                "Registered JobAgent tools: none.",
                "No tools are available for this session. Do not call or "
                "invent tools. Answer every request with natural conversation "
                "only.",
            ]
        )
    else:
        sections.append(
            "Registered JobAgent tools (use only these; do not invent others):"
        )
        for name in names:
            sections.append(f"- {name}")
        sections.append(
            "Use a listed tool only when the user request requires that "
            "capability; otherwise answer directly."
        )
        if "propose_profile_from_cv" in names or "commit_profile_draft" in names:
            sections.extend(
                [
                    "",
                    "Profile / CV tools:",
                    "- propose_profile_from_cv requires a staged attachment "
                    "UUID from this turn or durable working memory. Never pass "
                    "draft_id placeholders such as 'current' or 'latest' as "
                    "attachment_id.",
                    "- After a successful propose that creates or reuses a "
                    "draft, call commit_profile_draft with draft_id='current' "
                    "so the user can Save Profile or Request Changes. Without "
                    "that call the sidebar stays empty (no approved profile).",
                    "- Answer follow-up profile questions from the current "
                    "unapproved draft or approved profile context when present; "
                    "do not re-run propose with invented attachment IDs.",
                ]
            )
        if "read_active_cv" in names:
            sections.extend(
                [
                    "",
                    "Active CV evidence (read_active_cv):",
                    "- Prompt context includes only the active CV identity and "
                    "compact outline (section ids/headings/kinds/counts). It "
                    "never includes section bodies or chunk text by default.",
                    "- Call read_active_cv only when the user needs document "
                    "evidence beyond the outline. Prefer the narrowest mode: "
                    "section for one outline section_id, search for a short "
                    "query, or chunk for one ordered raw page.",
                    "- Never pass attachment IDs; the tool resolves the active "
                    "CV server-side and rejects archived or staged CVs.",
                    "- Paginate with next_cursor only when the user's request "
                    "genuinely needs more evidence. Do not walk every cursor "
                    "or exhaust the document automatically.",
                ]
            )

    return "\n".join(sections)


def _normalize_tool_names(registered_tools: Sequence[str] | None) -> list[str]:
    """Return stripped non-empty tool names in caller order (deduplicated)."""
    if not registered_tools:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in registered_tools:
        name = raw.strip() if isinstance(raw, str) else ""
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
