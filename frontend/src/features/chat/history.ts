/**
 * Durable history hydration and chronological merge for chat state.
 * History is authoritative: completed-turn tool activity replaces transient stream tools.
 * Interrupted profile_commit pending_approval is recovered for restart-safe cards.
 * Compact ToolResult.data is preserved as ClientToolActivity.resultData (stream keeps null).
 */

import {projectMatchJobsResultData} from '../jobs/matchResult';
import {projectCompactResultData} from '../jobs/types';
import {projectActiveCvResultData} from './activeCvEvidence';
import type {
  AgentRunView,
  ApprovalRequiredPayload,
  ChatMessageView,
  HistoryPage,
  JsonObject,
  ToolExecutionView,
} from './types';
import type {
  ClientMessage,
  ClientRun,
  ClientToolActivity,
} from './reducer';

/**
 * Durable ToolResult.data projection: save_job, match_jobs, then read_active_cv.
 * Unrelated tools retain null resultData (no second store or parser fork).
 * Stream tool_status keeps resultData null; only terminal history supplies evidence.
 */
export function projectToolResultData(
  toolName: string,
  data: JsonObject | null | undefined,
): JsonObject | null {
  return (
    projectCompactResultData(toolName, data) ??
    projectMatchJobsResultData(toolName, data) ??
    projectActiveCvResultData(toolName, data)
  );
}

/** Map a durable tool execution into client tool activity (history source). */
export function toolViewToActivity(tool: ToolExecutionView): ClientToolActivity {
  const rawData = tool.result?.data ?? null;
  return {
    toolExecutionId: tool.id,
    toolCallId: tool.tool_call_id,
    toolName: tool.tool_name,
    status: tool.status,
    durationMs: tool.duration_ms,
    summary: tool.result?.summary ?? null,
    errorCode: tool.error_code,
    source: 'history',
    // save_job + match_jobs + read_active_cv allowlists — unrelated tools retain no resultData.
    resultData: projectToolResultData(tool.tool_name, rawData),
  };
}

/** Map a durable agent run into client run state. */
export function runViewToClient(run: AgentRunView): ClientRun {
  return {
    id: run.id,
    userMessageId: run.user_message_id,
    state: run.state,
    pendingApproval: run.pending_approval,
    errorCode: run.error_code,
    completedAt: run.completed_at,
    tools: run.tool_executions.map(toolViewToActivity),
  };
}

/** Map one history message item to a client message. */
export function messageViewToClient(item: ChatMessageView): ClientMessage {
  return {
    id: item.id,
    clientKey: item.id,
    role: item.role,
    content: item.content,
    createdAt: item.created_at,
    run: item.run ? runViewToClient(item.run) : null,
    isStreaming: false,
  };
}

/**
 * Merge history items chronologically by (createdAt, id).
 * Drops duplicates by durable message id and replaces optimistic user turns
 * when durable history confirms the same run id.
 */
export function mergeMessagesChronological(
  existing: readonly ClientMessage[],
  incoming: readonly ClientMessage[],
): ClientMessage[] {
  const byId = new Map<string, ClientMessage>();
  const userMessageIdByRun = new Map<string, string>();
  for (const m of existing) {
    byId.set(m.id, m);
    if (m.role === 'user' && m.run) {
      userMessageIdByRun.set(m.run.id, m.id);
    }
  }
  for (const m of incoming) {
    if (m.role === 'user' && m.run) {
      const existingUserId = userMessageIdByRun.get(m.run.id);
      if (existingUserId && existingUserId !== m.id) {
        byId.delete(existingUserId);
      }
      userMessageIdByRun.set(m.run.id, m.id);
    }
    byId.set(m.id, m);
  }
  return [...byId.values()].sort((a, b) => {
    const ta = a.createdAt ?? '';
    const tb = b.createdAt ?? '';
    if (ta !== tb) {
      return ta < tb ? -1 : 1;
    }
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

/**
 * For completed (or failed) durable runs, replace any transient stream tools
 * on matching run ids with history tool activity.
 */
export function replaceTransientToolsFromHistory(
  messages: readonly ClientMessage[],
  historyItems: readonly ChatMessageView[],
): ClientMessage[] {
  const durableByRun = new Map<string, ClientRun>();
  for (const item of historyItems) {
    if (item.run) {
      const clientRun = runViewToClient(item.run);
      if (
        clientRun.state === 'completed' ||
        clientRun.state === 'failed'
      ) {
        durableByRun.set(clientRun.id, clientRun);
      }
    }
  }
  if (durableByRun.size === 0) {
    return [...messages];
  }
  return messages.map((msg) => {
    if (!msg.run) {
      return msg;
    }
    const durable = durableByRun.get(msg.run.id);
    if (!durable) {
      return msg;
    }
    return {
      ...msg,
      run: {
        ...msg.run,
        state: durable.state,
        errorCode: durable.errorCode,
        completedAt: durable.completedAt,
        pendingApproval: durable.pendingApproval,
        // Durable tools replace all transient stream tools for this run.
        tools: durable.tools,
      },
      isStreaming: false,
    };
  });
}

/**
 * Terminal runs whose history page includes a durable assistant sibling after
 * the initiating user turn (canonical card host after rehydrate).
 */
function terminalRunsWithDurableAssistant(
  historyItems: readonly ChatMessageView[],
): ReadonlySet<string> {
  const withAssistant = new Set<string>();
  for (let i = 0; i < historyItems.length; i += 1) {
    const item = historyItems[i];
    if (
      item.role !== 'user' ||
      !item.run ||
      (item.run.state !== 'completed' && item.run.state !== 'failed')
    ) {
      continue;
    }
    const runId = item.run.id;
    for (let j = i + 1; j < historyItems.length; j += 1) {
      const next = historyItems[j];
      if (next.role === 'assistant') {
        withAssistant.add(runId);
        break;
      }
      if (next.role === 'user') {
        break;
      }
    }
  }
  return withAssistant;
}

/**
 * Drop stream-shaped assistant hosts (`assistant:<run_id>`) when durable
 * history already provides a terminal assistant for that run. Prevents two
 * saved-job cards when stream and durable message IDs differ or timestamps tie.
 * Interrupted runs are never collapsed (profile approval stays on stream host).
 */
export function dropSupersededStreamAssistants(
  messages: readonly ClientMessage[],
  historyItems: readonly ChatMessageView[],
): ClientMessage[] {
  const durableHosts = terminalRunsWithDurableAssistant(historyItems);
  if (durableHosts.size === 0) {
    return [...messages];
  }
  return messages.filter((msg) => {
    if (msg.role !== 'assistant' || !msg.run) {
      return true;
    }
    const runId = msg.run.id;
    if (!durableHosts.has(runId)) {
      return true;
    }
    // Ephemeral stream assistants use id/clientKey `assistant:<run_id>`.
    if (msg.id === `assistant:${runId}` || msg.clientKey === `assistant:${runId}`) {
      return false;
    }
    return true;
  });
}

/**
 * Recover a single pending profile/approval interrupt from durable messages.
 * Used after history load/restart so the approval card and composer lock return.
 */
export function recoverPendingApproval(messages: readonly ClientMessage[]): {
  pendingApproval: ApprovalRequiredPayload | null;
  activeRunId: string | null;
} {
  for (const msg of messages) {
    const run = msg.run;
    if (!run || run.state !== 'interrupted' || !run.pendingApproval) {
      continue;
    }
    const raw = run.pendingApproval;
    const kind =
      typeof raw.kind === 'string' && raw.kind.trim() !== '' ? raw.kind : null;
    if (kind === null) {
      continue;
    }
    const allowedRaw = raw.allowed_actions;
    const allowed_actions = Array.isArray(allowedRaw)
      ? allowedRaw.filter(
          (a): a is string => typeof a === 'string' && a.trim() !== '',
        )
      : [];
    if (allowed_actions.length === 0) {
      continue;
    }
    const card: JsonObject =
      raw.card !== null &&
      typeof raw.card === 'object' &&
      !Array.isArray(raw.card)
        ? (raw.card as JsonObject)
        : {};
    return {
      pendingApproval: {
        state: 'interrupted',
        kind,
        allowed_actions,
        card,
      },
      activeRunId: run.id,
    };
  }
  return {pendingApproval: null, activeRunId: null};
}

/**
 * Initial hydration: set messages from a history page (newest page).
 * Preserves next_cursor; durable tools are the sole tool source for those turns.
 */
export function hydrateFromHistoryPage(page: HistoryPage): {
  messages: ClientMessage[];
  nextCursor: string | null;
} {
  const messages = page.items.map(messageViewToClient);
  return {
    messages: mergeMessagesChronological([], messages),
    nextCursor: page.next_cursor,
  };
}

/**
 * Load-older merge: prepend older chronological items without duplicates.
 * Updates next_cursor to the older page's cursor (null when no more).
 */
export function mergeOlderHistoryPage(
  currentMessages: readonly ClientMessage[],
  page: HistoryPage,
): {
  messages: ClientMessage[];
  nextCursor: string | null;
} {
  const incoming = page.items.map(messageViewToClient);
  // Replace transient tools on any overlapping completed runs.
  const withDurableTools = replaceTransientToolsFromHistory(
    mergeMessagesChronological(currentMessages, incoming),
    page.items,
  );
  return {
    messages: dropSupersededStreamAssistants(withDurableTools, page.items),
    nextCursor: page.next_cursor,
  };
}

/**
 * Re-hydrate after reconnect: merge page and force durable tools for
 * completed turns over any in-memory stream tool state. Collapses stream
 * assistant hosts when durable terminal assistants exist for the same run.
 */
export function rehydrateWithDurableTruth(
  currentMessages: readonly ClientMessage[],
  page: HistoryPage,
): {
  messages: ClientMessage[];
  nextCursor: string | null;
} {
  const incoming = page.items.map(messageViewToClient);
  const merged = mergeMessagesChronological(currentMessages, incoming);
  const withDurable = replaceTransientToolsFromHistory(merged, page.items);
  return {
    messages: dropSupersededStreamAssistants(withDurable, page.items),
    nextCursor: page.next_cursor,
  };
}
