"""Controlled Agent runtime package (state, prompts, graph, lifecycle).

Plan 3 owns bounded state, domain prompt policy, the single ToolNode graph,
and per-run AsyncSqliteSaver checkpoint lifecycle.
"""

from __future__ import annotations

from app.agent.graph import (
    DEFAULT_TOOL_LOOP_LIMIT,
    TOOL_LOOP_LIMIT_EXCEEDED,
    AgentGraphState,
    build_agent_graph,
    has_successful_run_outcome,
    initial_graph_state,
)
from app.agent.lifecycle import (
    CHECKPOINT_TABLE_NAMES,
    CheckpointLifecycleError,
    count_thread_checkpoints_on_disk,
    delete_completed_thread_checkpoints,
    open_async_sqlite_saver,
    thread_run_config,
)
from app.agent.prompt import (
    DOMAIN_REDIRECT_MESSAGE,
    DOMAIN_SYSTEM_POLICY,
    DomainPolicyDecision,
    build_system_prompt,
    evaluate_domain_policy,
    wrap_untrusted_document,
)
from app.agent.state import (
    AGENT_STATE_KEYS,
    FORBIDDEN_STATE_BODY_KEYS,
    AgentState,
    initial_agent_state,
    validate_agent_state,
)

__all__ = [
    "AGENT_STATE_KEYS",
    "CHECKPOINT_TABLE_NAMES",
    "DEFAULT_TOOL_LOOP_LIMIT",
    "DOMAIN_REDIRECT_MESSAGE",
    "DOMAIN_SYSTEM_POLICY",
    "FORBIDDEN_STATE_BODY_KEYS",
    "TOOL_LOOP_LIMIT_EXCEEDED",
    "AgentGraphState",
    "AgentState",
    "CheckpointLifecycleError",
    "DomainPolicyDecision",
    "build_agent_graph",
    "build_system_prompt",
    "count_thread_checkpoints_on_disk",
    "delete_completed_thread_checkpoints",
    "evaluate_domain_policy",
    "has_successful_run_outcome",
    "initial_agent_state",
    "initial_graph_state",
    "open_async_sqlite_saver",
    "thread_run_config",
    "validate_agent_state",
    "wrap_untrusted_document",
]
