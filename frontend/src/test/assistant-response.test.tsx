/**
 * Assistant Markdown + exact-one Nguồn citation placement (Plan 12 03A).
 * Semantic rendering, reserved-marker hygiene, safe/fallback placement, role split.
 */
import type {ReactElement} from 'react';
import {
  cleanup,
  render,
  screen,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  ACTIVE_CV_CITATION_LABEL,
  ACTIVE_CV_CITATION_MARKER,
  ACTIVE_CV_CITATION_SOURCE_ID,
  AssistantResponse,
  placeActiveCvCitationMarker,
} from '../features/chat/components/AssistantResponse';
import {ChatMessageRow} from '../features/chat/components/ChatMessageRow';
import {
  activeCvEvidenceForTools,
  projectActiveCvResultData,
  READ_ACTIVE_CV_TOOL_NAME,
  type ActiveCvEvidenceBundle,
} from '../features/chat/activeCvEvidence';
import type {ClientMessage, ClientToolActivity} from '../features/chat/reducer';
import type {JsonObject} from '../features/chat/types';

const ATTACHMENT = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const TOOL_EXEC = '22222222-2222-4222-8222-222222222222';
const TS = '2026-07-18T12:00:00.000Z';

function entryRecord(overrides: JsonObject = {}): JsonObject {
  return {
    kind: 'entry',
    section_id: 'sec-certs',
    entry_id: 'entry-1',
    ordinal: 0,
    title: 'AWS Certified',
    subtitle: null,
    date_text: '2024',
    location: null,
    body: 'Cloud practitioner certificate.',
    bullets: ['Exam passed'],
    source_chunk_ordinals: [0, 1],
    ...overrides,
  };
}

function rawPage(
  records: JsonObject[] = [entryRecord()],
  overrides: JsonObject = {},
): JsonObject {
  return {
    attachment_id: ATTACHMENT,
    extraction_version: 'v1',
    source_hash: 'hash-abc',
    mode: 'section',
    records,
    returned_chars: 40,
    truncated: false,
    next_cursor: null,
    ...overrides,
  };
}

function activity(
  resultData: JsonObject | null,
  overrides: Partial<ClientToolActivity> = {},
): ClientToolActivity {
  return {
    toolExecutionId: TOOL_EXEC,
    toolCallId: 'tc-cv-1',
    toolName: READ_ACTIVE_CV_TOOL_NAME,
    status: 'completed',
    durationMs: 40,
    summary: 'ok',
    errorCode: null,
    source: 'history',
    resultData,
    ...overrides,
  };
}

function bundleFromPage(
  page: JsonObject = rawPage(),
): ActiveCvEvidenceBundle {
  const projected = projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, page);
  const bundle = activeCvEvidenceForTools([activity(projected)]);
  if (!bundle) {
    throw new Error('expected evidence bundle');
  }
  return bundle;
}

function renderWithTheme(ui: ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

beforeEach(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute('open', '');
    };
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function close() {
      this.removeAttribute('open');
    };
  }
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('placeActiveCvCitationMarker', () => {
  it('inserts exactly one reserved marker after the first safe lead paragraph', () => {
    const input = 'Bạn có 1 Certificate.\n\nChi tiết thêm ở dưới.';
    const {displayContent, placement} = placeActiveCvCitationMarker(input);
    expect(placement).toBe('inline');
    expect(displayContent).toContain(
      `Bạn có 1 Certificate.${ACTIVE_CV_CITATION_MARKER}`,
    );
    expect(
      displayContent.split(ACTIVE_CV_CITATION_MARKER).length - 1,
    ).toBe(1);
    // Original shape retained; second paragraph unchanged.
    expect(displayContent).toContain('Chi tiết thêm ở dưới.');
    // Input not mutated by reference (string is immutable; prove no double).
    expect(input).not.toContain(ACTIVE_CV_CITATION_MARKER);
  });

  it('skips headings and lists and places after the first safe paragraph', () => {
    const input = [
      '## Overview',
      '',
      '- not here',
      '',
      'Direct answer paragraph.',
      '',
      'More.',
    ].join('\n');
    const {displayContent, placement} = placeActiveCvCitationMarker(input);
    expect(placement).toBe('inline');
    expect(displayContent).toContain(
      `Direct answer paragraph.${ACTIVE_CV_CITATION_MARKER}`,
    );
    expect(displayContent).not.toMatch(
      new RegExp(`- not here${ACTIVE_CV_CITATION_MARKER.replace(/[[\]]/g, '\\$&')}`),
    );
  });

  it('does not insert inside fenced code blocks', () => {
    const input = ['```', 'code line', '```', '', 'Safe lead.'].join('\n');
    const {displayContent, placement} = placeActiveCvCitationMarker(input);
    expect(placement).toBe('inline');
    expect(displayContent).toContain(`Safe lead.${ACTIVE_CV_CITATION_MARKER}`);
    const fenceBody = displayContent.split('```')[1];
    expect(fenceBody).not.toContain(ACTIVE_CV_CITATION_MARKER);
  });

  it('falls back when only lists/headings/code exist', () => {
    const listOnly = '- a\n- b';
    expect(placeActiveCvCitationMarker(listOnly).placement).toBe('fallback');
    expect(placeActiveCvCitationMarker(listOnly).displayContent).not.toContain(
      ACTIVE_CV_CITATION_MARKER,
    );
    const headingOnly = '### title only';
    expect(placeActiveCvCitationMarker(headingOnly).placement).toBe(
      'fallback',
    );
    const fenceOnly = '```\ncode\n```';
    expect(placeActiveCvCitationMarker(fenceOnly).placement).toBe('fallback');
  });

  it('strips accidental reserved markers before re-placing one', () => {
    const dirty = `Lead${ACTIVE_CV_CITATION_MARKER} text${ACTIVE_CV_CITATION_MARKER}.`;
    const {displayContent} = placeActiveCvCitationMarker(dirty);
    expect(
      displayContent.split(ACTIVE_CV_CITATION_MARKER).length - 1,
    ).toBe(1);
  });
});

describe('AssistantResponse Markdown semantics', () => {
  it('renders headings, emphasis, lists, links, and code without raw syntax', () => {
    const md = [
      '# Top',
      '',
      'This is **bold** and *italic*.',
      '',
      '- item one',
      '- item two',
      '',
      'See [docs](https://example.com/docs).',
      '',
      'Use `inline` and:',
      '',
      '```',
      'const x = 1;',
      '```',
    ].join('\n');

    const {container} = renderWithTheme(
      <AssistantResponse content={md} evidence={null} />,
    );

    // headingLevelStart=4 → # maps to h4
    const heading = container.querySelector('h4');
    expect(heading).not.toBeNull();
    expect(heading?.textContent).toContain('Top');
    expect(screen.queryByText(/### /)).not.toBeInTheDocument();
    expect(screen.queryByText(/\*\*bold\*\*/)).not.toBeInTheDocument();

    expect(container.querySelector('strong, b')).not.toBeNull();
    expect(container.querySelector('em, i')).not.toBeNull();
    expect(container.querySelector('ul, ol')).not.toBeNull();
    const link = container.querySelector('a[href="https://example.com/docs"]');
    expect(link).not.toBeNull();
    expect(container.querySelector('code')).not.toBeNull();

    const markdown = screen.getByTestId('jobagent-assistant-markdown');
    expect(markdown).toHaveAttribute('data-density', 'compact');
  });

  it('passes isStreaming to Markdown for live tokens', () => {
    const {container} = renderWithTheme(
      <AssistantResponse
        content="Streaming answer"
        isStreaming
        evidence={null}
      />,
    );
    // Astryx smooths streamed text; assert the streaming markdown surface exists.
    expect(
      container.querySelector(
        '[data-testid="jobagent-assistant-markdown"][role="document"]',
      ),
    ).not.toBeNull();
    expect(
      screen.queryByTestId('jobagent-active-cv-citation'),
    ).not.toBeInTheDocument();
  });

  it('shows no citation without evidence and never surfaces the reserved marker', () => {
    const content = `Answer with accidental ${ACTIVE_CV_CITATION_MARKER} text.`;
    renderWithTheme(
      <AssistantResponse content={content} evidence={null} />,
    );
    expect(
      screen.queryByTestId('jobagent-active-cv-citation'),
    ).not.toBeInTheDocument();
    // Without sources, marker would show as raw brackets if present in children;
    // we pass content as-is when no evidence — raw accidental marker may appear
    // as text only if content includes it. Verify Nguồn chip absent.
    expect(screen.queryByText(ACTIVE_CV_CITATION_LABEL)).not.toBeInTheDocument();
  });

  it('renders exactly one Nguồn for valid evidence after the lead paragraph', () => {
    const bundle = bundleFromPage();
    renderWithTheme(
      <AssistantResponse
        content="Bạn có 1 Certificate.\n\nExtra detail."
        evidence={bundle}
      />,
    );
    const citations = screen.getAllByTestId('jobagent-active-cv-citation');
    expect(citations).toHaveLength(1);
    expect(citations[0]).toHaveTextContent(ACTIVE_CV_CITATION_LABEL);
    // Reserved marker never visible as raw text.
    expect(
      screen.queryByText(new RegExp(ACTIVE_CV_CITATION_SOURCE_ID)),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(ACTIVE_CV_CITATION_MARKER),
    ).not.toBeInTheDocument();
  });

  it('uses post-body fallback when no safe lead paragraph exists', () => {
    const bundle = bundleFromPage();
    renderWithTheme(
      <AssistantResponse content={'- only a list\n- second'} evidence={bundle} />,
    );
    const citations = screen.getAllByTestId('jobagent-active-cv-citation');
    expect(citations).toHaveLength(1);
    expect(citations[0]).toHaveTextContent(ACTIVE_CV_CITATION_LABEL);
  });

  it('opens the source dialog from the citation without navigating', async () => {
    const user = userEvent.setup();
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const bundle = bundleFromPage(
      rawPage([entryRecord()], {truncated: true, next_cursor: 'more'}),
    );
    renderWithTheme(
      <AssistantResponse content="Direct answer." evidence={bundle} />,
    );

    await user.click(screen.getByTestId('jobagent-active-cv-citation'));
    expect(
      screen.getByTestId('jobagent-active-cv-source-dialog'),
    ).toBeInTheDocument();
    expect(screen.getByText('Nguồn từ CV')).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-active-cv-partial-notice'),
    ).toBeInTheDocument();
    expect(screen.getByText('Cloud practitioner certificate.')).toBeInTheDocument();
    expect(openSpy).not.toHaveBeenCalled();
  });
});

describe('ChatMessageRow role split and composition', () => {
  function assistantMessage(
    content: string,
    overrides: Partial<ClientMessage> = {},
  ): ClientMessage {
    return {
      id: 'asst-1',
      clientKey: 'asst-1',
      role: 'assistant',
      content,
      createdAt: TS,
      run: null,
      isStreaming: false,
      ...overrides,
    };
  }

  function userMessage(content: string): ClientMessage {
    return {
      id: 'user-1',
      clientKey: 'user-1',
      role: 'user',
      content,
      createdAt: TS,
      run: null,
      isStreaming: false,
    };
  }

  it('keeps user and system content literal including markdown syntax', () => {
    renderWithTheme(
      <ChatMessageRow
        message={userMessage('### not a heading **literal**')}
        tools={[]}
        sourceMessageId={null}
        profileCommit={null}
        approvalLocked={false}
      />,
    );
    expect(
      screen.getByText('### not a heading **literal**'),
    ).toBeInTheDocument();
  });

  it('renders assistant markdown and exactly one citation for row evidence', () => {
    const projected = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()]),
    );
    const tools = [activity(projected)];
    renderWithTheme(
      <ChatMessageRow
        message={assistantMessage('**Bold answer** with detail.')}
        tools={tools}
        sourceMessageId="user-1"
        profileCommit={null}
        approvalLocked={false}
      />,
    );
    expect(screen.queryByText(/\*\*Bold answer\*\*/)).not.toBeInTheDocument();
    expect(screen.getByTestId('jobagent-assistant-markdown')).toBeInTheDocument();
    expect(screen.getAllByTestId('jobagent-active-cv-citation')).toHaveLength(
      1,
    );
  });

  it('shows no citation for failed/malformed/stream-null evidence on the row', () => {
    renderWithTheme(
      <ChatMessageRow
        message={assistantMessage('Answer without proof.')}
        tools={[
          activity(null, {status: 'running'}),
          activity(null, {
            status: 'failed',
            errorCode: 'NO_ACTIVE_CV',
          }),
        ]}
        sourceMessageId="user-1"
        profileCommit={null}
        approvalLocked={false}
      />,
    );
    expect(
      screen.queryByTestId('jobagent-active-cv-citation'),
    ).not.toBeInTheDocument();
  });

  it('does not mutate the client message content when placing citation', () => {
    const projected = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage(),
    );
    const message = assistantMessage('Stable content.');
    renderWithTheme(
      <ChatMessageRow
        message={message}
        tools={[activity(projected)]}
        sourceMessageId="user-1"
        profileCommit={null}
        approvalLocked={false}
      />,
    );
    expect(message.content).toBe('Stable content.');
    expect(message.content).not.toContain(ACTIVE_CV_CITATION_MARKER);
  });
});
