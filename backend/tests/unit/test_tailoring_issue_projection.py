from __future__ import annotations

from app.schemas.cv_tailoring import TailoringUserIssue, parse_tailored_content
from app.schemas.sse import RunFailedPayload
from app.services.cv_tailoring_guard import GroundingIssue
from app.services.tailoring_issue_projection import (
    decode_internal_issue,
    encode_internal_issue,
    project_grounding_issues,
)


def _content():
    return parse_tailored_content(
        {
            "header": {
                "full_name": "Synthetic Candidate",
                "location": None,
                "phone": None,
                "email": None,
                "github_url": None,
            },
            "sections": [
                {
                    "id": "experience",
                    "ordinal": 0,
                    "heading": "Experience",
                    "kind": "experience",
                    "items": [
                        {
                            "id": "entry-1",
                            "source_entry_id": "entry-1",
                            "title": None,
                            "subtitle": None,
                            "date_text": None,
                            "location": None,
                            "body": {
                                "text": "Grounded",
                                "source_fact_ids": [
                                    "sf_11111111111111111111111111111111"
                                ],
                            },
                            "bullets": [],
                            "attributes": [],
                        }
                    ],
                }
            ],
        }
    )


def test_maps_internal_issue_to_bounded_user_issue() -> None:
    projected = project_grounding_issues(
        issue_list=[
            GroundingIssue(code="CROSS_SECTION_FACT", path="sections[0].items[0].body")
        ],
        parent=_content(),
    )
    assert [item.model_dump(mode="json") for item in projected] == [
        {
            "section_id": "experience",
            "section_heading": "Experience",
            "item_index": 0,
            "field": "body",
            "reason": "belongs_to_another_section",
        }
    ]


def test_unknown_path_collapses_without_leaking_the_raw_path() -> None:
    projected = project_grounding_issues(
        issue_list=[GroundingIssue(code="UNKNOWN_FACT", path="provider.secret[99]")],
        parent=_content(),
    )
    assert len(projected) == 1
    assert projected[0].field == "section"
    assert "provider.secret" not in projected[0].model_dump_json()


def test_durable_activity_codec_round_trips_only_allowlisted_identity() -> None:
    issue = GroundingIssue(
        code="EMPTY_PROVENANCE", path="sections[0].items[0].bullets[1]"
    )
    assert decode_internal_issue(encode_internal_issue(issue)) == issue
    assert (
        decode_internal_issue("tailoring-grounding:v1:UNKNOWN_FACT|provider.secret[99]")
        is None
    )
    assert decode_internal_issue(
        encode_internal_issue(
            GroundingIssue(code="UNKNOWN_FACT", path="provider.secret[99]")
        )
    ) == GroundingIssue(code="UNKNOWN_FACT", path="sections")


def test_chat_failure_omits_issues_while_tailoring_failure_is_safe() -> None:
    chat = RunFailedPayload(state="failed", error_code="FAILED", summary="Failed")
    assert chat.model_dump(mode="json") == {
        "state": "failed",
        "error_code": "FAILED",
        "summary": "Failed",
    }
    issue = TailoringUserIssue(
        section_id="experience",
        section_heading="Experience",
        item_index=0,
        field="body",
        reason="not_in_source",
    )
    tailored = RunFailedPayload(
        state="failed",
        error_code="TAILORING_GROUNDING_FAILED",
        summary="Tailored content is not source-supported",
        issues=[issue],
    )
    assert tailored.model_dump(mode="json")["issues"] == [issue.model_dump(mode="json")]
