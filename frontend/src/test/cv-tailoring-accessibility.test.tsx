import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {TailoringEditor} from '../features/cv-tailoring/TailoringEditor';
import type {CvTailoringController} from '../features/cv-tailoring/state';
import editorSource from '../features/cv-tailoring/TailoringEditor.tsx?raw';
import sectionSource from '../features/cv-tailoring/TailoredSectionEditor.tsx?raw';
import previewSource from '../features/cv-tailoring/TailoringPdfPreview.tsx?raw';
import actionsSource from '../features/cv-tailoring/TailoringVersionActions.tsx?raw';
import sessionsSource from '../features/cv-tailoring/TailoringSessionsPanel.tsx?raw';
import deleteSource from '../features/cv-tailoring/TailoringSessionDeleteDialog.tsx?raw';
import stylesSource from '../features/cv-tailoring/cv-tailoring.css?inline';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const VERSION_ID = '22222222-2222-4222-8222-222222222222';
const NOW = '2026-07-26T00:00:00Z';

function controller(): CvTailoringController {
  const content = {
    header: {
      full_name: 'Synthetic Candidate',
      location: null,
      phone: null,
      email: null,
      github_url: null,
    },
    sections: [
      {
        id: 'summary',
        ordinal: 0,
        heading: 'Summary',
        kind: 'summary' as const,
        items: [],
      },
    ],
  };
  const session = {
    id: SESSION_ID,
    profile_id: '33333333-3333-4333-8333-333333333333',
    job_label: null,
    instruction: 'Synthetic instruction',
    template_version: 'latex-cv-v1' as const,
    state: 'ready' as const,
    currentness: 'current' as const,
    latest_version_number: 1,
    error_code: null,
    created_at: NOW,
    updated_at: NOW,
  };
  const version = {
    id: VERSION_ID,
    version_number: 1,
    parent_version_id: null,
    created_by: 'ai' as const,
    page_count: 1,
    page_warning: null,
    created_at: NOW,
  };
  return {
    state: {
      profileScopeKey: `${session.profile_id}:ready`,
      sessions: {phase: 'ready', data: {items: [session]}, error: null},
      selectedSessionId: SESSION_ID,
      selectedVersionId: VERSION_ID,
      detail: {
        phase: 'error',
        data: {
          session,
          versions: [version],
          selected_version: version,
          content,
          evidence: [],
          latest_run: {
            id: '44444444-4444-4444-8444-444444444444',
            state: 'completed',
            error_code: null,
            activities: [],
          },
          source_available: true,
          pdf_available: true,
        },
        error: {
          code: 'REQUEST_FAILED',
          summary:
            String.raw`C:\private\resume.tex \documentclass raw JD candidate@example.test`,
        },
      },
      draft: content,
      draftDirty: false,
      conflict: false,
      stream: {phase: 'idle', data: null, error: null},
    },
    loadSessions: vi.fn().mockResolvedValue(undefined),
    openSession: vi.fn().mockResolvedValue(true),
    createSession: vi.fn().mockResolvedValue(null),
    createAiVersion: vi.fn().mockResolvedValue(false),
    setDraft: vi.fn(),
    saveManualVersion: vi.fn().mockResolvedValue(false),
    selectVersion: vi.fn().mockResolvedValue(false),
    deleteSession: vi.fn().mockResolvedValue(false),
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('tailoring UI accessibility and static guards', () => {
  it('uses mobile content/preview tabs with labeled live state and safe errors', async () => {
    render(
      <Theme theme={neutralTheme}>
        <TailoringEditor
          controller={controller()}
          onBackToChat={vi.fn()}
          onEditProfile={vi.fn()}
          canCreateFresh={false}
          mobileLayout={true}
          artifactUrls={{
            source: (versionId) => `/test/versions/${versionId}/source`,
            pdf: (versionId) => `/test/versions/${versionId}/pdf`,
          }}
        />
      </Theme>,
    );

    const tabs = await screen.findByRole('tablist', {name: 'Chế độ xem CV'});
    expect(tabs).toBeInTheDocument();
    expect(screen.getByRole('tab', {name: 'Nội dung'})).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await userEvent.click(screen.getByRole('tab', {name: 'Xem trước'}));
    expect(screen.getByRole('tab', {name: 'Xem trước'})).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByTitle('Xem trước PDF CV')).toBeVisible();
    expect(
      screen.getByText('Không thể hoàn tất yêu cầu CV.').closest('[role="status"]'),
    ).toHaveAttribute('aria-live', 'polite');
    expect(screen.queryByText(/private|documentclass|raw JD|candidate@/i)).not.toBeInTheDocument();
  });

  it('contains no raw layout divs, utility classes, hard-coded colors, or pixel declarations', () => {
    const sources = [
      editorSource,
      sectionSource,
      previewSource,
      actionsSource,
      sessionsSource,
      deleteSource,
    ];
    for (const source of sources) {
      expect(source).not.toMatch(/<div\b/i);
      expect(source).not.toMatch(
        /className=["'`][^"'`]*(?:^|\s)(?:flex(?:-[\w-]+)?|grid(?:-[\w-]+)?|gap-[\w-]+|p[trblxy]?-[\w-]+|m[trblxy]?-[\w-]+|w-[\w-]+|h-[\w-]+|text-[\w-]+|bg-[\w-]+)(?:\s|["'`])/,
      );
    }
    expect(stylesSource).toMatch(
      /(?:prefers-reduced-motion: reduce|^$)/,
    );
  });
});
