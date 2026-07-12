"""Phase 3 exit proof entrypoint (task 06A).

Cohesive cases live under ``tests.integration.profile_workflow`` as non-collected
helper modules. They are re-exported here so:

- ``pytest tests/integration/test_full_profile_workflow.py`` runs the full suite
- full ``pytest -q`` collects each case exactly once (no double collection)

Never calls ShopAIKey or a live Neo4j instance.
"""

from __future__ import annotations

from tests.integration.profile_workflow.exposure_cases import (
    test_application_routes_are_exactly_seven_authorized,
    test_neo4j_failure_does_not_roll_back_approved_sqlite,
    test_production_has_exactly_six_tools_and_no_forbidden_exposure,
)
from tests.integration.profile_workflow.failure_cases import (
    test_oversized_pdf_rejected_with_zero_side_effects,
    test_replacement_failures_preserve_prior_or_new_state,
    test_upload_and_pipeline_failures_are_sanitized,
)
from tests.integration.profile_workflow.workflow_cases import (
    test_full_profile_workflow_upload_correct_approve_sync_restart,
)

__all__ = [
    "test_application_routes_are_exactly_seven_authorized",
    "test_full_profile_workflow_upload_correct_approve_sync_restart",
    "test_neo4j_failure_does_not_roll_back_approved_sqlite",
    "test_oversized_pdf_rejected_with_zero_side_effects",
    "test_production_has_exactly_six_tools_and_no_forbidden_exposure",
    "test_replacement_failures_preserve_prior_or_new_state",
    "test_upload_and_pipeline_failures_are_sanitized",
]
